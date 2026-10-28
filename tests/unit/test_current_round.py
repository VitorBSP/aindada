"""Rodada mostrada em `current-round.json` (ADR-0009, Decisão 3). Dados sintéticos (synthetic), temporada 2099."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from brasileirao.storage.current_round import (
    BaselineMismatchError,
    build_current_round,
    is_resolved,
    round_anchor,
)
from brasileirao.storage.schema import (
    CurrentRound,
    DataInfo,
    MatchPrediction,
    ModelInfo,
    PredictionSnapshot,
    RoundReview,
    RoundViewInfo,
    TeamPrediction,
)

SEASON = 2099
CLUBS = ("synthetic-a", "synthetic-b", "synthetic-c", "synthetic-d")
MODEL_VERSION = "synthetic-model"
DATA_VERSION = "synthetic-data"


def _match(
    match_id: str,
    round_number: int | None,
    day: str,
    status: str = "finished",
    kickoff_utc: str | None = None,
) -> MatchPrediction:
    finished = status == "finished"
    return MatchPrediction(
        match_id=match_id,
        round=round_number,
        match_date=day,
        home_id=CLUBS[0],
        away_id=CLUBS[1],
        status=status,
        home_goals=1 if finished else None,
        away_goals=0 if finished else None,
        kickoff_utc=kickoff_utc,
        source_match_id=f"source-{match_id}",
    )


def _season_matches(**overrides: MatchPrediction) -> list[MatchPrediction]:
    """Três rodadas sintéticas de dois jogos (sábado e domingo); `overrides` troca ou acrescenta jogos."""
    base = {
        "r1-1": _match("r1-1", 1, "2099-03-07"),
        "r1-2": _match("r1-2", 1, "2099-03-08"),
        "r2-1": _match("r2-1", 2, "2099-03-14"),
        "r2-2": _match("r2-2", 2, "2099-03-15"),
        "r3-1": _match("r3-1", 3, "2099-03-21", "scheduled", "2099-03-21T19:00:00Z"),
        "r3-2": _match("r3-2", 3, "2099-03-22", "scheduled", "2099-03-22T19:00:00Z"),
    }
    base.update({key.replace("_", "-"): value for key, value in overrides.items()})
    return list(base.values())


def _snapshot(matches: list[MatchPrediction], clubs: tuple[str, ...] = CLUBS) -> PredictionSnapshot:
    return PredictionSnapshot.model_construct(
        season=SEASON,
        generated_at="2099-03-21T09:30:00+00:00",
        is_synthetic=True,
        model=ModelInfo.model_construct(model_version=MODEL_VERSION),
        data=DataInfo.model_construct(version=DATA_VERSION),
        teams=[TeamPrediction.model_construct(club_id=club) for club in clubs],
        matches=matches,
    )


def _view(round_number: int, reference_date: str, title: float) -> RoundViewInfo:
    return RoundViewInfo(
        round_number=round_number,
        reference_date=date.fromisoformat(reference_date),
        partial=False,
        observed_matches=round_number * 2,
        teams={club: {"title": title, "top4": 0.5, "relegation": 0.1, "points": 10.0} for club in CLUBS},
    )


def _review(views: list[RoundViewInfo], data_version: str = DATA_VERSION) -> RoundReview:
    return RoundReview(
        schema_version="1.1",
        season=SEASON,
        generated_at="2099-03-21T09:20:00+00:00",
        model_version=MODEL_VERSION,
        data_version=data_version,
        data_until="2099-03-15",
        n_simulations=20000,
        seed=1,
        metrics=["title", "top4", "relegation"],
        clubs={},
        rounds=views,
    )


REVIEW = _review(
    [
        _view(0, "2099-03-06", 0.25),
        _view(1, "2099-03-13", 0.30),
        _view(2, "2099-03-15", 0.40),
    ]
)


def _current(matches: list[MatchPrediction], now: str, review: RoundReview | None = REVIEW) -> CurrentRound:
    return build_current_round(_snapshot(matches), review, datetime.fromisoformat(now))


def test_anchor_is_lower_median() -> None:
    days = [date(2099, 3, 14), date(2099, 3, 15), date(2099, 3, 16), date(2099, 4, 20)]
    assert round_anchor(days) == date(2099, 3, 15)


def test_preseason_has_no_round() -> None:
    assert _current(_season_matches(), "2099-03-06T20:00:00+00:00").round is None


def test_round_starting_today_is_in_progress() -> None:
    matches = _season_matches()
    current = _current(matches, "2099-03-21T09:17:00+00:00")
    assert (current.round.round_number, current.round.state) == (3, "in_progress")  # type: ignore[union-attr]


def test_day_is_taken_in_brasilia() -> None:
    current = _current(_season_matches(), "2099-03-21T02:00:00+00:00")
    assert (current.round.round_number, current.round.state) == (2, "finished")  # type: ignore[union-attr]


def test_round_turns_finished_when_all_results_are_in() -> None:
    matches = _season_matches(r3_1=_match("r3-1", 3, "2099-03-21"), r3_2=_match("r3-2", 3, "2099-03-22"))
    current = _current(matches, "2099-03-23T12:00:00+00:00")
    assert (current.round.round_number, current.round.state) == (3, "finished")  # type: ignore[union-attr]


def test_missing_score_keeps_round_open_within_stale_limit() -> None:
    matches = _season_matches(r3_1=_match("r3-1", 3, "2099-03-21"))
    current = _current(matches, "2099-03-24T18:00:00+00:00")
    assert current.round.state == "in_progress"  # type: ignore[union-attr]


def test_missing_score_after_stale_limit_closes_round() -> None:
    matches = _season_matches(r3_1=_match("r3-1", 3, "2099-03-21"))
    current = _current(matches, "2099-03-24T20:00:00+00:00")
    assert current.round.state == "finished"  # type: ignore[union-attr]


def test_stale_match_never_gets_score() -> None:
    matches = _season_matches(r3_1=_match("r3-1", 3, "2099-03-21"))
    stale = next(match for match in matches if match.match_id == "r3-2")
    assert (stale.home_goals, stale.away_goals, is_resolved(stale, datetime(2099, 3, 25, tzinfo=UTC))) == (
        None,
        None,
        True,
    )


def test_match_without_kickoff_waits_until_end_of_day() -> None:
    pending = _match("r3-9", 3, "2099-03-22", "scheduled")
    assert not is_resolved(pending, datetime(2099, 3, 24, 22, 0, tzinfo=UTC))


def test_postponed_match_is_resolved() -> None:
    assert is_resolved(_match("r3-9", 3, "2099-03-22", "postponed"), datetime(2099, 3, 22, tzinfo=UTC))


def test_rescheduled_match_does_not_hold_round_open() -> None:
    matches = _season_matches(r2_3=_match("r2-3", 2, "2099-04-20", "scheduled"))
    current = _current(matches, "2099-03-17T12:00:00+00:00")
    assert (current.round.round_number, current.round.state) == (2, "finished")  # type: ignore[union-attr]


def test_rescheduled_match_is_listed_apart() -> None:
    matches = _season_matches(r2_3=_match("r2-3", 2, "2099-04-20", "scheduled"))
    current = _current(matches, "2099-03-17T12:00:00+00:00")
    assert current.round.rescheduled_match_ids == ["r2-3"]  # type: ignore[union-attr]


def test_delayed_match_of_other_round_enters_interval() -> None:
    matches = _season_matches(r1_3=_match("r1-3", 1, "2099-03-22", "scheduled", "2099-03-22T21:30:00Z"))
    current = _current(matches, "2099-03-21T12:00:00+00:00")
    assert current.round.match_ids == ["r3-1", "r3-2", "r1-3"]  # type: ignore[union-attr]


def test_delayed_match_is_not_rescheduled_of_shown_round() -> None:
    matches = _season_matches(r1_3=_match("r1-3", 1, "2099-03-22", "scheduled", "2099-03-22T21:30:00Z"))
    current = _current(matches, "2099-03-21T12:00:00+00:00")
    assert current.round.rescheduled_match_ids == []  # type: ignore[union-attr]


def test_matches_without_kickoff_go_last_in_their_day() -> None:
    matches = _season_matches(
        r3_3=_match("r3-3", 3, "2099-03-21", "scheduled"),
        r3_4=_match("r3-4", 3, "2099-03-21", "scheduled", "2099-03-21T22:00:00Z"),
    )
    current = _current(matches, "2099-03-21T12:00:00+00:00")
    assert current.round.match_ids == ["r3-1", "r3-4", "r3-3", "r3-2"]  # type: ignore[union-attr]


def test_dates_cover_window_only() -> None:
    matches = _season_matches(r3_3=_match("r3-3", 3, "2099-05-02", "scheduled"))
    round_info = _current(matches, "2099-03-21T12:00:00+00:00").round
    assert (round_info.starts_on, round_info.ends_on) == ("2099-03-21", "2099-03-22")  # type: ignore[union-attr]


def test_baseline_is_last_view_before_start() -> None:
    baseline = _current(_season_matches(), "2099-03-21T12:00:00+00:00").round.baseline  # type: ignore[union-attr]
    assert baseline.reference_date == "2099-03-15"  # type: ignore[union-attr]


def test_baseline_teams_equal_cited_view() -> None:
    baseline = _current(_season_matches(), "2099-03-21T12:00:00+00:00").round.baseline  # type: ignore[union-attr]
    expected = {club: {"title": 0.4, "top4": 0.5, "relegation": 0.1} for club in CLUBS}
    assert baseline.teams == expected  # type: ignore[union-attr]


def test_baseline_carries_review_simulations() -> None:
    baseline = _current(_season_matches(), "2099-03-21T12:00:00+00:00").round.baseline  # type: ignore[union-attr]
    assert (baseline.n_simulations, baseline.model_version, baseline.reconstructed) == (  # type: ignore[union-attr]
        20000,
        MODEL_VERSION,
        True,
    )


def test_round_one_without_earlier_view_has_no_baseline() -> None:
    review = _review([_view(1, "2099-03-07", 0.3)])
    current = _current(_season_matches(), "2099-03-07T12:00:00+00:00", review)
    assert current.round.baseline is None  # type: ignore[union-attr]


def test_round_one_without_review_has_no_baseline() -> None:
    current = _current(_season_matches(), "2099-03-07T12:00:00+00:00", None)
    assert current.round.baseline is None  # type: ignore[union-attr]


def test_review_from_other_data_has_no_baseline() -> None:
    review = _review(REVIEW.rounds, data_version="other-data")
    current = _current(_season_matches(), "2099-03-21T12:00:00+00:00", review)
    assert current.round.baseline is None  # type: ignore[union-attr]


def test_baseline_with_other_clubs_fails() -> None:
    snapshot = _snapshot(_season_matches(), clubs=CLUBS[:3])
    with pytest.raises(BaselineMismatchError):
        build_current_round(snapshot, REVIEW, datetime(2099, 3, 21, 12, tzinfo=UTC))


def test_versions_follow_snapshot() -> None:
    current = _current(_season_matches(), "2099-03-21T12:00:00+00:00")
    assert (current.updated_at, current.model_version, current.data_version) == (
        "2099-03-21T09:30:00+00:00",
        MODEL_VERSION,
        DATA_VERSION,
    )


def test_legacy_match_without_kickoff_fields_is_readable() -> None:
    legacy = {
        "match_id": "synthetic-legacy",
        "round": 1,
        "match_date": "2099-03-07",
        "home_id": CLUBS[0],
        "away_id": CLUBS[1],
        "status": "scheduled",
    }
    match = MatchPrediction.model_validate(legacy)
    assert (match.kickoff_utc, match.source_match_id) == (None, None)
