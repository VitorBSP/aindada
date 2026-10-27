from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from brasileirao.config import AttackDefenseParams, EloParams, RatingParams
from brasileirao.ratings.attack_defense import attack_defense_update
from brasileirao.ratings.elo import elo_delta, expected_home_score, goal_difference_multiplier
from brasileirao.ratings.history import RatingEngine, build_state_as_of, season_clubs_from_fixtures


def test_equal_ratings_expected_score_reflects_home_advantage() -> None:
    assert expected_home_score(1500.0, 1500.0, 0.0) == pytest.approx(0.5)


def test_home_advantage_raises_expected_score() -> None:
    assert expected_home_score(1500.0, 1500.0, 70.0) > 0.5


def test_goal_difference_multiplier_for_three_goals() -> None:
    assert goal_difference_multiplier(3.0) == pytest.approx(14 / 8)


def test_elo_is_zero_sum_for_expected_draw() -> None:
    params = EloParams(k_factor=20.0, home_advantage=0.0)
    assert elo_delta(1500.0, 1500.0, 1.0, 1.0, params) == pytest.approx(0.0)


def test_upset_win_gains_more_than_expected_win() -> None:
    params = EloParams(k_factor=20.0, home_advantage=0.0)
    assert elo_delta(1400.0, 1600.0, 1.0, 0.0, params) > elo_delta(1600.0, 1400.0, 1.0, 0.0, params)


def test_scoring_above_expectation_raises_attack() -> None:
    update = attack_defense_update(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 4.0, 0.0, AttackDefenseParams())
    assert update.home_attack > 0.0


def test_conceding_above_expectation_lowers_defense() -> None:
    update = attack_defense_update(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 4.0, 0.0, AttackDefenseParams())
    assert update.away_defense < 0.0


def _same_date_matches(order: list[int]) -> pd.DataFrame:
    rows = [
        {
            "match_id": "m1",
            "season": 2030,
            "match_date": pd.Timestamp("2030-05-01"),
            "home_id": "a",
            "away_id": "b",
            "home_goals": 3,
            "away_goals": 0,
            "status": "finished",
        },
        {
            "match_id": "m2",
            "season": 2030,
            "match_date": pd.Timestamp("2030-05-01"),
            "home_id": "c",
            "away_id": "d",
            "home_goals": 0,
            "away_goals": 2,
            "status": "finished",
        },
        {
            "match_id": "m3",
            "season": 2030,
            "match_date": pd.Timestamp("2030-05-08"),
            "home_id": "a",
            "away_id": "c",
            "home_goals": 1,
            "away_goals": 1,
            "status": "finished",
        },
    ]
    return pd.DataFrame([rows[index] for index in order])


def test_simultaneous_matches_independent_of_processing_order() -> None:
    results = []
    for order in ([0, 1, 2], [1, 0, 2]):
        matches = _same_date_matches(order)
        engine = RatingEngine(RatingParams())
        engine.run(matches, season_clubs_from_fixtures(matches))
        results.append({club: rating.elo for club, rating in engine.state.ratings.items()})
    assert results[0] == results[1]


def test_state_as_of_ignores_matches_after_reference_date(synthetic_matches: pd.DataFrame) -> None:
    cutoff = date(2032, 6, 1)
    _, features = build_state_as_of(synthetic_matches, cutoff, 2032, RatingParams())
    assert features["match_date"].max() <= pd.Timestamp(cutoff)


def test_promoted_clubs_start_from_relegated_average(synthetic_matches: pd.DataFrame) -> None:
    engine, _ = build_state_as_of(synthetic_matches, date(2031, 3, 1), 2031, RatingParams())
    promoted = {"sintetico-21", "sintetico-22"}
    assert engine.state.ratings["sintetico-21"].elo == engine.state.ratings["sintetico-22"].elo and promoted
