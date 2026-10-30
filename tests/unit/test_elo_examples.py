"""Exemplos do Elo ("Como calculamos"). Todos os dados são sintéticos (synthetic)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from brasileirao.config import EloParams, RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.europe import gate as europe_gate
from brasileirao.europe.ratings import GlobalElo, GlobalEloParams
from brasileirao.leagues import gate as leagues_gate
from brasileirao.pipeline import ModelConfig
from brasileirao.ratings.examples import (
    BRAZIL_TIEBREAK,
    EXAMPLES_FILE_NAME,
    CompetitionInfo,
    ExampleMismatchError,
    champions_examples,
    check_examples_file,
    copy_examples,
    display_names,
    examples_document,
    league_examples,
    regressed_elo,
    trace_global_ratings,
    trace_league_ratings,
    write_examples,
)
from brasileirao.ratings.history import build_state_as_of
from brasileirao.serie_b.forecast import build_forecast
from brasileirao.serie_b.gate import check_artifact
from brasileirao.serie_b.rules import load_serie_b_rules

PARAMS = RatingParams(elo=EloParams(k_factor=20.0, home_advantage=60.0, season_regression=0.3))
PAIR = ("sintetico-12", "sintetico-21")


def _info(season: int, reference_date: date, competition_id: str = "serie-a") -> CompetitionInfo:
    return CompetitionInfo(competition_id, "Sintético", season, reference_date, "synthetic-data", "synthetic-model")


def _reference(matches: pd.DataFrame, season: int) -> date:
    finished = matches[(matches["season"] == season) & (matches["status"] == "finished")]
    return finished["match_date"].max().date()


def _head_to_head(matches: pd.DataFrame, pair: tuple[str, str], season: int, until: date) -> pd.DataFrame:
    meetings = matches[
        (matches["season"] == season)
        & (matches["status"] == "finished")
        & (matches["match_date"].dt.date <= until)
        & (
            ((matches["home_id"] == pair[0]) & (matches["away_id"] == pair[1]))
            | ((matches["home_id"] == pair[1]) & (matches["away_id"] == pair[0]))
        )
    ]
    return meetings.sort_values(["match_date", "match_id"])


@pytest.fixture(scope="module")
def competition(synthetic_matches: pd.DataFrame, synthetic_registry: ClubRegistry) -> dict[str, Any]:
    info = _info(2032, _reference(synthetic_matches, 2032))
    return league_examples(info, synthetic_matches, PARAMS, display_names(synthetic_registry), BRAZIL_TIEBREAK, PAIR)


def _club(competition: dict[str, Any], club: str) -> dict[str, Any]:
    return next(example for example in competition["examples"] if example["club_id"] == club)


def _all_season_rows(competition: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for example in competition["examples"] for row in example["ledger"]["seasons"]]


def test_traced_engine_ends_in_the_same_state_as_the_engine(synthetic_matches: pd.DataFrame) -> None:
    reference_date = _reference(synthetic_matches, 2032)
    engine, _ = build_state_as_of(synthetic_matches, reference_date, 2032, PARAMS)
    trace = trace_league_ratings(synthetic_matches, reference_date, 2032, PARAMS)
    assert trace.final_elo == {club: rating.elo for club, rating in engine.state.ratings.items()}


def test_example_is_the_latest_head_to_head(competition: dict[str, Any], synthetic_matches: pd.DataFrame) -> None:
    meetings = _head_to_head(synthetic_matches, PAIR, 2032, _reference(synthetic_matches, 2032))
    assert competition["match"]["match_id"] == meetings.iloc[-1]["match_id"]


def test_head_to_head_falls_back_to_the_previous_season(synthetic_matches: pd.DataFrame) -> None:
    first_day = synthetic_matches[synthetic_matches["season"] == 2032]["match_date"].min().date()
    pair = next(
        (home, away)
        for home, away in zip(
            synthetic_matches.loc[synthetic_matches["season"] == 2031, "home_id"],
            synthetic_matches.loc[synthetic_matches["season"] == 2031, "away_id"],
            strict=True,
        )
        if _head_to_head(synthetic_matches, (home, away), 2032, first_day).empty
    )
    early = league_examples(_info(2032, first_day), synthetic_matches, PARAMS, {}, BRAZIL_TIEBREAK, pair)
    assert early["match"]["season"] == 2031


def test_pair_that_never_met_is_refused(synthetic_matches: pd.DataFrame) -> None:
    info = _info(2032, _reference(synthetic_matches, 2032))
    with pytest.raises(KeyError):
        league_examples(info, synthetic_matches, PARAMS, {}, BRAZIL_TIEBREAK, ("sintetico-01", "sintetico-21"))


def test_examples_are_the_two_sides_of_the_match(competition: dict[str, Any]) -> None:
    sides = [(example["side"], example["club_id"]) for example in competition["examples"]]
    assert sides == [
        ("home", competition["match"]["home"]["club_id"]),
        ("away", competition["match"]["away"]["club_id"]),
    ]


def test_example_delta_equals_the_engine_change(competition: dict[str, Any], synthetic_matches: pd.DataFrame) -> None:
    match = competition["match"]
    match_date = date.fromisoformat(match["date"])
    before, _ = build_state_as_of(synthetic_matches, match_date - timedelta(days=1), 2032, PARAMS)
    after, _ = build_state_as_of(synthetic_matches, match_date, 2032, PARAMS)
    home_id = match["home"]["club_id"]
    engine_change = after.state.ratings[home_id].elo - before.state.ratings[home_id].elo
    assert match["delta_home"] == pytest.approx(engine_change, abs=1e-12)


def test_example_delta_is_the_published_formula(competition: dict[str, Any]) -> None:
    match = competition["match"]
    formula = match["k_factor"] * match["goal_difference_multiplier"] * (match["result_home"] - match["expected_home"])
    assert match["delta_home"] == pytest.approx(formula, abs=1e-12)


def test_example_elo_after_is_before_plus_delta(competition: dict[str, Any]) -> None:
    match = competition["match"]
    assert match["home"]["elo_after"] == match["home"]["elo_before"] + match["delta_home"]


def test_every_season_entry_plus_net_is_the_end(competition: dict[str, Any]) -> None:
    rows = _all_season_rows(competition)
    assert rows and all(row["entry_elo"] + row["net"] == row["end_elo"] for row in rows)


def test_season_net_is_the_sum_of_the_match_deltas(
    competition: dict[str, Any], synthetic_matches: pd.DataFrame
) -> None:
    trace = trace_league_ratings(synthetic_matches, _reference(synthetic_matches, 2032), 2032, PARAMS)
    club = "sintetico-12"
    row = next(row for row in _club(competition, club)["ledger"]["seasons"] if row["season"] == 2031)
    changes = [
        (match.home_elo_after - match.home_elo_before)
        if match.home_id == club
        else match.away_elo_after - match.away_elo_before
        for match in trace.matches
        if match.season == 2031 and club in (match.home_id, match.away_id)
    ]
    assert row["net"] == pytest.approx(sum(changes), abs=1e-9)


def test_entry_plus_net_until_is_the_elo_before_the_match(competition: dict[str, Any]) -> None:
    currents = [example["ledger"]["current"] for example in competition["examples"]]
    assert all(current["entry"]["after"] + current["net_until"] == current["elo_before_match"] for current in currents)


def test_elo_before_match_is_the_one_in_the_match_block(competition: dict[str, Any]) -> None:
    found = [example["ledger"]["current"]["elo_before_match"] for example in competition["examples"]]
    assert found == [competition["match"]["home"]["elo_before"], competition["match"]["away"]["elo_before"]]


def test_matches_until_stop_on_the_eve(competition: dict[str, Any], synthetic_matches: pd.DataFrame) -> None:
    club = "sintetico-12"
    match_date = pd.Timestamp(competition["match"]["date"])
    played = synthetic_matches[
        (synthetic_matches["season"] == 2032)
        & (synthetic_matches["match_date"] < match_date)
        & ((synthetic_matches["home_id"] == club) | (synthetic_matches["away_id"] == club))
    ]
    listed = [item["match_id"] for item in _club(competition, club)["ledger"]["current"]["matches_until"]]
    assert listed == played.sort_values(["match_date", "match_id"])["match_id"].tolist()


def test_matches_until_deltas_chain_to_each_elo_after(competition: dict[str, Any]) -> None:
    current = _club(competition, "sintetico-12")["ledger"]["current"]
    running = current["entry"]["after"]
    gaps = []
    for item in current["matches_until"]:
        running += item["delta"]
        gaps.append(abs(running - item["elo_after"]))
    assert max(gaps) < 1e-9


def test_entry_formula_gives_the_first_pre_match_elo(
    competition: dict[str, Any], synthetic_matches: pd.DataFrame
) -> None:
    entry = _club(competition, "sintetico-12")["ledger"]["current"]["entry"]
    _, features = build_state_as_of(synthetic_matches, _reference(synthetic_matches, 2032), 2032, PARAMS)
    first = features[
        (features["season"] == 2032)
        & ((features["home_id"] == "sintetico-12") | (features["away_id"] == "sintetico-12"))
    ].iloc[0]
    first_elo = first["elo_home"] if first["home_id"] == "sintetico-12" else first["elo_away"]
    published = entry["recentered_to"] + (entry["before"] - entry["reference_mean"]) * (1 - entry["regression"])
    assert published == pytest.approx(first_elo, abs=1e-9)


def test_previous_season_end_is_the_entry_before_regression(competition: dict[str, Any]) -> None:
    example = _club(competition, "sintetico-12")
    assert example["previous_season"]["elo_end"] == example["ledger"]["current"]["entry"]["before"]


def test_previous_season_points_follow_the_results(
    competition: dict[str, Any], synthetic_matches: pd.DataFrame
) -> None:
    season = synthetic_matches[synthetic_matches["season"] == 2031]
    home = season[season["home_id"] == "sintetico-12"]
    away = season[season["away_id"] == "sintetico-12"]
    points = (
        3 * (home["home_goals"] > home["away_goals"]).sum()
        + (home["home_goals"] == home["away_goals"]).sum()
        + 3 * (away["away_goals"] > away["home_goals"]).sum()
        + (away["home_goals"] == away["away_goals"]).sum()
    )
    assert _club(competition, "sintetico-12")["previous_season"]["points"] == points


def test_newcomer_season_enters_with_the_mean_of_the_clubs_that_left(
    competition: dict[str, Any], synthetic_matches: pd.DataFrame
) -> None:
    engine, _ = build_state_as_of(synthetic_matches, date(2030, 12, 31), 2030, PARAMS)
    leavers_mean = (engine.state.ratings["sintetico-01"].elo + engine.state.ratings["sintetico-02"].elo) / 2
    row = next(row for row in _club(competition, "sintetico-21")["ledger"]["seasons"] if row["season"] == 2031)
    assert row["newcomer_rule"]["base"] == pytest.approx(leavers_mean, abs=1e-9)


def test_weights_start_at_the_last_newcomer_entry(competition: dict[str, Any]) -> None:
    assert _club(competition, "sintetico-21")["ledger"]["weights"]["starting_point"]["season"] == 2031


def test_weights_current_season_has_weight_one(competition: dict[str, Any]) -> None:
    rows = _club(competition, "sintetico-12")["ledger"]["weights"]["seasons"]
    assert (rows[0]["season"], rows[0]["weight"]) == (2032, 1.0)


def test_weights_close_the_gap_in_a_league(competition: dict[str, Any]) -> None:
    weights = _club(competition, "sintetico-12")["ledger"]["weights"]
    assert weights["approx_total"] == pytest.approx(weights["exact"], abs=1e-6)


def test_competition_records_reference_date_and_versions(
    competition: dict[str, Any], synthetic_matches: pd.DataFrame
) -> None:
    assert (competition["reference_date"], competition["data_version"]) == (
        _reference(synthetic_matches, 2032).isoformat(),
        "synthetic-data",
    )


def _european_matches() -> pd.DataFrame:
    """Duas temporadas sintéticas: liga ENG (a1 a a4), liga SCO (b1 a b3) e jogos de copa entre os países."""
    rows = []
    for season, start in ((2030, date(2030, 8, 1)), (2031, date(2031, 8, 1))):
        fixtures = [
            ("ENG", "a1", "a2", 2, 0),
            ("ENG", "a3", "a4", 1, 1),
            ("SCO", "b1", "b2", 3, 1),
            ("SCO", "b3", "b1", 0, 0),
            ("CL", "a1", "b1", 1, 0),
            ("ENG", "a2", "a3", 0, 2),
            ("SCO", "b2", "b3", 1, 2),
            ("CL", "b2", "a4", 2, 2),
            ("ENG", "a4", "a1", 0, 3),
            ("ENG", "a1", "a3", 1, 1),
        ]
        for index, (competition, home, away, home_goals, away_goals) in enumerate(fixtures):
            rows.append(
                {
                    "match_id": f"syn-{season}-{index:02d}",
                    "season": season,
                    "competition": competition,
                    "round": index + 1,
                    "match_date": pd.Timestamp(start + timedelta(days=7 * index)),
                    "home_id": home,
                    "away_id": away,
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                    "neutral": False,
                    "status": "finished",
                }
            )
    return pd.DataFrame(rows)


COUNTRIES = {"a1": "ENG", "a2": "ENG", "a3": "ENG", "a4": "ENG", "b1": "SCO", "b2": "SCO", "b3": "SCO"}
GLOBAL_PARAMS = GlobalEloParams(k_factor=30.0, home_advantage=100.0, season_regression=0.2)


@pytest.fixture(scope="module")
def champions_cup() -> dict[str, Any]:
    info = _info(2031, date(2031, 12, 31), "champions-league")
    return champions_examples(info, _european_matches(), GLOBAL_PARAMS, COUNTRIES, {}, ("a1", "b1"))


def test_global_trace_ends_in_the_same_state_as_the_engine() -> None:
    matches = _european_matches()
    engine = GlobalElo(GLOBAL_PARAMS, COUNTRIES)
    engine.run(matches)
    trace = trace_global_ratings(matches, date(2031, 12, 31), 2031, GLOBAL_PARAMS, COUNTRIES)
    assert trace.final_elo == engine.state.ratings


def test_champions_head_to_head_must_be_a_champions_match() -> None:
    info = _info(2031, date(2031, 12, 31), "champions-league")
    with pytest.raises(KeyError):
        champions_examples(info, _european_matches(), GLOBAL_PARAMS, COUNTRIES, {}, ("a1", "a3"))


def test_champions_example_is_a_cross_country_cup_match(champions_cup: dict[str, Any]) -> None:
    assert (champions_cup["match"]["competition"], champions_cup["match"]["match_id"]) == ("CL", "syn-2031-04")


def test_global_example_delta_equals_the_engine_change(champions_cup: dict[str, Any]) -> None:
    matches = _european_matches()
    match = champions_cup["match"]
    before = GlobalElo(GLOBAL_PARAMS, COUNTRIES)
    before.run(matches[matches["match_date"] < pd.Timestamp(match["date"])])
    after = GlobalElo(GLOBAL_PARAMS, COUNTRIES)
    after.run(matches[matches["match_date"] <= pd.Timestamp(match["date"])])
    away_id = match["away"]["club_id"]
    engine_change = after.state.ratings[away_id] - before.state.ratings[away_id]
    assert -match["delta_home"] == pytest.approx(engine_change, abs=1e-12)


def test_global_ledger_lists_domestic_matches_with_their_competition(champions_cup: dict[str, Any]) -> None:
    current = _club(champions_cup, "a1")["ledger"]["current"]
    assert [item["competition"] for item in current["matches_until"]] == ["ENG"]


def test_global_entry_plus_net_until_is_the_elo_before_the_match(champions_cup: dict[str, Any]) -> None:
    currents = [example["ledger"]["current"] for example in champions_cup["examples"]]
    assert all(current["entry"]["after"] + current["net_until"] == current["elo_before_match"] for current in currents)


def test_global_season_rows_close_exactly(champions_cup: dict[str, Any]) -> None:
    rows = _all_season_rows(champions_cup)
    assert rows and all(row["entry_elo"] + row["net"] == row["end_elo"] for row in rows)


def test_global_entry_regresses_to_the_country_mean(champions_cup: dict[str, Any]) -> None:
    entry = _club(champions_cup, "a1")["ledger"]["current"]["entry"]
    assert entry["reference_mean_kind"] == "country"


def test_global_season_start_mean_is_the_country_mean() -> None:
    trace = trace_global_ratings(_european_matches(), date(2031, 12, 31), 2031, GLOBAL_PARAMS, COUNTRIES)
    start = trace.season_starts[2031]
    english = [start.ratings_before[club] for club in ("a1", "a2", "a3", "a4")]
    assert start.reference_mean["a1"] == pytest.approx(sum(english) / 4, abs=1e-9)


def test_global_regression_formula_reproduces_the_engine() -> None:
    trace = trace_global_ratings(_european_matches(), date(2031, 12, 31), 2031, GLOBAL_PARAMS, COUNTRIES)
    start = trace.season_starts[2031]
    assert regressed_elo(start, "b2") == pytest.approx(start.elo_after["b2"], abs=1e-9)


def test_global_first_season_is_a_newcomer_entry(champions_cup: dict[str, Any]) -> None:
    row = _club(champions_cup, "b1")["ledger"]["seasons"][0]
    assert row["newcomer_rule"]["rule"] == "initial_rating"


def test_global_example_has_no_league_position(champions_cup: dict[str, Any]) -> None:
    assert _club(champions_cup, "a1")["previous_season"]["position"] is None


def test_mismatch_skips_the_file_instead_of_publishing(tmp_path: Path) -> None:
    path = tmp_path / EXAMPLES_FILE_NAME
    path.write_text("{}", encoding="utf-8")

    def broken() -> dict[str, Any]:
        raise ExampleMismatchError("synthetic")

    write_examples(path, broken)
    assert not path.exists()


def test_copy_examples_removes_stale_target(tmp_path: Path) -> None:
    (tmp_path / "source").mkdir()
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / EXAMPLES_FILE_NAME).write_text("{}", encoding="utf-8")
    copy_examples(tmp_path / "source", tmp_path / "target")
    assert not (tmp_path / "target" / EXAMPLES_FILE_NAME).exists()


def _write_document(path: Path, competition_id: str, reference_date: str) -> None:
    competition = {"id": competition_id, "reference_date": reference_date, "examples": []}
    path.write_text(json.dumps(examples_document(competition)), encoding="utf-8")


def test_examples_check_accepts_matching_file(tmp_path: Path) -> None:
    path = tmp_path / EXAMPLES_FILE_NAME
    _write_document(path, "serie-b", "2032-08-10")
    assert check_examples_file(path, "serie-b", "2032-08-10") == []


def test_examples_check_rejects_other_competition(tmp_path: Path) -> None:
    path = tmp_path / EXAMPLES_FILE_NAME
    _write_document(path, "la-liga", "2032-08-10")
    assert check_examples_file(path, "serie-b", "2032-08-10") != []


def test_examples_check_rejects_other_reference_date(tmp_path: Path) -> None:
    path = tmp_path / EXAMPLES_FILE_NAME
    _write_document(path, "serie-b", "2032-08-03")
    assert check_examples_file(path, "serie-b", "2032-08-10") != []


def _site(tmp_path: Path) -> Path:
    for name in ("index.html", "app.js", "styles.css"):
        (tmp_path / name).write_text("synthetic", encoding="utf-8")
    (tmp_path / "data").mkdir()
    return tmp_path


def test_serie_b_gate_accepts_elo_examples(
    tmp_path: Path, synthetic_matches: pd.DataFrame, synthetic_registry: ClubRegistry
) -> None:
    rules = replace(load_serie_b_rules(2026), season=2032)
    reference_date = _reference(synthetic_matches, 2032)
    sources = {"reference_date": reference_date.isoformat(), "sources": []}
    config = ModelConfig("elo_attack_defense", RatingParams(), False)
    forecast = build_forecast(synthetic_matches, sources, rules, synthetic_registry, config, 200, 11)
    site = _site(tmp_path)
    (site / "data" / "forecast.json").write_text(forecast.model_dump_json(), encoding="utf-8")
    _write_document(site / "data" / EXAMPLES_FILE_NAME, "serie-b", forecast.reference_date)
    assert check_artifact(site, None, reference_date + timedelta(days=1)) == []


def _stub_forecast(**fields: object) -> SimpleNamespace:
    return SimpleNamespace(reference_date="2032-08-10", **fields)


def test_league_gate_accepts_elo_examples(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        leagues_gate.LeagueForecast,
        "model_validate_json",
        classmethod(lambda cls, _: _stub_forecast(competition="la-liga")),
    )
    monkeypatch.setattr(leagues_gate, "check_forecast_core", lambda forecast, today: [])
    site = _site(tmp_path)
    (site / "data" / "forecast.json").write_text("{}", encoding="utf-8")
    _write_document(site / "data" / EXAMPLES_FILE_NAME, "la-liga", "2032-08-10")
    assert leagues_gate.check_artifact(site, None, date(2032, 8, 11), "la-liga") == []


def test_league_gate_still_rejects_other_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        leagues_gate.LeagueForecast,
        "model_validate_json",
        classmethod(lambda cls, _: _stub_forecast(competition="la-liga")),
    )
    monkeypatch.setattr(leagues_gate, "check_forecast_core", lambda forecast, today: [])
    site = _site(tmp_path)
    (site / "data" / "forecast.json").write_text("{}", encoding="utf-8")
    (site / "data" / "matches.json").write_text("{}", encoding="utf-8")
    assert leagues_gate.check_artifact(site, None, date(2032, 8, 11), "la-liga") == [
        "arquivos inesperados em data/: ['matches.json']"
    ]


def test_champions_gate_accepts_elo_examples(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        europe_gate.ChampionsForecast, "model_validate_json", classmethod(lambda cls, _: _stub_forecast())
    )
    monkeypatch.setattr(europe_gate, "check_forecast_core", lambda forecast, today: [])
    site = _site(tmp_path)
    (site / "data" / "forecast.json").write_text("{}", encoding="utf-8")
    _write_document(site / "data" / EXAMPLES_FILE_NAME, "champions-league", "2032-08-10")
    assert europe_gate.check_artifact(site, None, date(2032, 8, 11)) == []


def test_champions_gate_rejects_examples_of_another_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        europe_gate.ChampionsForecast, "model_validate_json", classmethod(lambda cls, _: _stub_forecast())
    )
    monkeypatch.setattr(europe_gate, "check_forecast_core", lambda forecast, today: [])
    site = _site(tmp_path)
    (site / "data" / "forecast.json").write_text("{}", encoding="utf-8")
    _write_document(site / "data" / EXAMPLES_FILE_NAME, "champions-league", "2032-08-03")
    assert len(europe_gate.check_artifact(site, None, date(2032, 8, 11))) == 1
