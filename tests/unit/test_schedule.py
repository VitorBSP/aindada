"""Dificuldade da tabela e pontos esperados por mando. Dados SINTÉTICOS (synthetic), nunca reais."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from brasileirao.prediction.goals_model import GoalsModel
from brasileirao.prediction.schedule import (
    AWAY,
    HOME,
    ClubSchedule,
    average_team_points_by_opponent,
    build_schedules,
    schedule_scale,
)
from brasileirao.ratings.history import ClubRating, RatingState
from brasileirao.simulation.engine import split_season_matches
from tests.fixtures.synthetic import SYNTHETIC_SOURCE

SYNTHETIC_ELO = {"sint-a": 1650.0, "sint-b": 1350.0, "sint-c": 1600.0, "sint-d": 1400.0}


def _synthetic_model() -> GoalsModel:
    return GoalsModel(
        feature_set="elo_only",
        home_features=("elo_diff",),
        away_features=("elo_diff",),
        home_intercept=float(np.log(1.45)),
        home_coefficients=[0.25],
        away_intercept=float(np.log(1.05)),
        away_coefficients=[-0.25],
    )


def _synthetic_state() -> RatingState:
    ratings = {club: ClubRating(elo=elo, attack=0.0, defense=0.0, form=0.0) for club, elo in SYNTHETIC_ELO.items()}
    return RatingState(ratings=ratings, base=0.1, home_effect=0.3, season_clubs=frozenset(ratings))


def _fixture(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "match_id": f"syn-{index}",
                "season": 2032,
                "round": index + 1,
                "match_date": pd.Timestamp(match_date),
                "home_id": home,
                "away_id": away,
                "home_goals": None,
                "away_goals": None,
                "status": "scheduled",
                "source": SYNTHETIC_SOURCE,
            }
            for index, (match_date, home, away) in enumerate(rows)
        ]
    )


SYNTHETIC_REMAINING = _fixture(
    [
        ("2032-11-01", "sint-a", "sint-c"),
        ("2032-11-01", "sint-b", "sint-d"),
        ("2032-11-08", "sint-c", "sint-b"),
        ("2032-11-08", "sint-d", "sint-a"),
        ("2032-11-15", "sint-b", "sint-c"),
    ]
)


@pytest.fixture(scope="module")
def schedules() -> dict[str, ClubSchedule]:
    built, _ = build_schedules(SYNTHETIC_REMAINING, _synthetic_state(), _synthetic_model(), list(SYNTHETIC_ELO))
    return {schedule.club_id: schedule for schedule in built}


def test_expected_points_split_by_venue(schedules: dict[str, ClubSchedule]) -> None:
    club = schedules["sint-b"]
    assert club.expected_points == pytest.approx(club.expected_points_home + club.expected_points_away)


def test_match_expected_points_follow_outcome_probabilities(schedules: dict[str, ClubSchedule]) -> None:
    match = schedules["sint-a"].matches[0]
    assert match.expected_points == pytest.approx(3 * match.p_win + match.p_draw)


def test_match_counts_by_venue(schedules: dict[str, ClubSchedule]) -> None:
    club = schedules["sint-b"]
    assert (club.remaining_matches, club.home_matches, club.away_matches) == (3, 2, 1)


def test_difficulty_stays_within_scale(schedules: dict[str, ClubSchedule]) -> None:
    values = [match.difficulty for schedule in schedules.values() for match in schedule.matches]
    assert min(values) >= 0.0 and max(values) <= 100.0


def test_club_difficulty_is_mean_of_match_difficulties(schedules: dict[str, ClubSchedule]) -> None:
    club = schedules["sint-b"]
    assert club.difficulty == pytest.approx(np.mean([match.difficulty for match in club.matches]))


def test_league_average_schedule_scores_fifty() -> None:
    home_points, away_points = average_team_points_by_opponent(
        _synthetic_state(), _synthetic_model(), list(SYNTHETIC_ELO)
    )
    scale = schedule_scale(home_points, away_points)
    full_schedule = [scale.difficulty(points) for points in [*home_points.values(), *away_points.values()]]
    assert np.mean(full_schedule) == pytest.approx(50.0)


def test_away_match_is_harder_than_home_match_against_same_opponent() -> None:
    home_points, away_points = average_team_points_by_opponent(
        _synthetic_state(), _synthetic_model(), list(SYNTHETIC_ELO)
    )
    scale = schedule_scale(home_points, away_points)
    assert scale.difficulty(away_points["sint-c"]) > scale.difficulty(home_points["sint-c"])


def test_stronger_opponent_is_harder() -> None:
    home_points, _away_points = average_team_points_by_opponent(
        _synthetic_state(), _synthetic_model(), list(SYNTHETIC_ELO)
    )
    assert home_points["sint-a"] < home_points["sint-b"]


def test_difficulty_ignores_own_strength() -> None:
    same_fixture = _fixture([("2032-11-01", "sint-a", "sint-d"), ("2032-11-01", "sint-b", "sint-d")])
    built, _ = build_schedules(same_fixture, _synthetic_state(), _synthetic_model(), list(SYNTHETIC_ELO))
    by_club = {schedule.club_id: schedule for schedule in built}
    assert by_club["sint-a"].difficulty == pytest.approx(by_club["sint-b"].difficulty)


def test_own_strength_changes_expected_points() -> None:
    same_fixture = _fixture([("2032-11-01", "sint-a", "sint-d"), ("2032-11-01", "sint-b", "sint-d")])
    built, _ = build_schedules(same_fixture, _synthetic_state(), _synthetic_model(), list(SYNTHETIC_ELO))
    by_club = {schedule.club_id: schedule for schedule in built}
    assert by_club["sint-a"].expected_points > by_club["sint-b"].expected_points


def test_opponent_strength_ignores_venue(schedules: dict[str, ClubSchedule]) -> None:
    strengths = {
        match.opponent_id: match.opponent_strength
        for schedule in schedules.values()
        for match in schedule.matches
        if match.opponent_id == "sint-c"
    }
    venues = {
        match.venue for schedule in schedules.values() for match in schedule.matches if match.opponent_id == "sint-c"
    }
    assert venues == {HOME, AWAY} and len(set(strengths.values())) == 1


def test_rank_one_is_hardest_schedule(schedules: dict[str, ClubSchedule]) -> None:
    hardest = max(schedules.values(), key=lambda schedule: schedule.difficulty or 0.0)
    assert hardest.difficulty_rank == 1


def test_club_without_away_matches_has_no_away_difficulty() -> None:
    home_only = _fixture([("2032-11-01", "sint-a", "sint-d")])
    built, _ = build_schedules(home_only, _synthetic_state(), _synthetic_model(), list(SYNTHETIC_ELO))
    by_club = {schedule.club_id: schedule for schedule in built}
    assert by_club["sint-a"].difficulty_away is None and by_club["sint-a"].difficulty_away_rank is None


def test_postponed_match_without_date_change_stays_remaining() -> None:
    season = _fixture([("2032-07-30", "sint-a", "sint-b"), ("2032-11-01", "sint-c", "sint-d")])
    season.loc[0, "status"] = "postponed"
    _, remaining = split_season_matches(season, date(2032, 10, 25))
    built, _ = build_schedules(remaining, _synthetic_state(), _synthetic_model(), list(SYNTHETIC_ELO))
    assert {schedule.club_id: schedule.remaining_matches for schedule in built}["sint-a"] == 1
