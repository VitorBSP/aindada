"""Campos `top_scores` e `p_three_plus_goals` no snapshot, com dados SINTÉTICOS (nunca apresentados como reais)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.config import RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.pipeline import ModelConfig, build_snapshot
from brasileirao.storage.schema import DataInfo, MatchPrediction

DATA_INFO = DataInfo(
    source="synthetic-fixture",
    version="synthetic",
    license_status="synthetic",
    retrieved_at="2032-10-01T00:00:00",
    warnings=["dados sintéticos de teste"],
)


@pytest.fixture(scope="module")
def remaining(
    synthetic_matches: pd.DataFrame, synthetic_rules: SeasonRules, synthetic_registry: ClubRegistry
) -> list[MatchPrediction]:
    snapshot = build_snapshot(
        synthetic_matches,
        2032,
        date(2032, 10, 25),
        200,
        3,
        synthetic_rules,
        synthetic_registry,
        ModelConfig("elo_attack_defense", RatingParams(), True, goal_dispersion=True),
        DATA_INFO,
    )
    return [match for match in snapshot.matches if match.status != "finished"]


def test_every_remaining_match_has_three_top_scores(remaining: list[MatchPrediction]) -> None:
    assert remaining and all(match.top_scores is not None and len(match.top_scores) == 3 for match in remaining)


def test_most_likely_score_is_first_top_score(remaining: list[MatchPrediction]) -> None:
    labels = [
        (match.most_likely_score, f"{match.top_scores[0].home_goals}-{match.top_scores[0].away_goals}")
        for match in remaining
        if match.top_scores
    ]
    assert all(most_likely == first for most_likely, first in labels)


def test_top_score_probabilities_are_decreasing(remaining: list[MatchPrediction]) -> None:
    orders = [[score.probability for score in match.top_scores or []] for match in remaining]
    assert all(order == sorted(order, reverse=True) for order in orders)


def test_top_scores_fit_inside_unit_probability(remaining: list[MatchPrediction]) -> None:
    assert all(0 < sum(score.probability for score in match.top_scores or []) < 1 for match in remaining)


def test_three_plus_goals_is_a_probability(remaining: list[MatchPrediction]) -> None:
    assert all(match.p_three_plus_goals is not None and 0 < match.p_three_plus_goals < 1 for match in remaining)


def test_finished_matches_have_no_score_distribution(
    synthetic_matches: pd.DataFrame, synthetic_rules: SeasonRules, synthetic_registry: ClubRegistry
) -> None:
    snapshot = build_snapshot(
        synthetic_matches,
        2032,
        date(2032, 10, 25),
        50,
        3,
        synthetic_rules,
        synthetic_registry,
        ModelConfig("elo_attack_defense", RatingParams(), True),
        DATA_INFO,
    )
    finished = [match for match in snapshot.matches if match.status == "finished"]
    assert all(match.top_scores is None and match.p_three_plus_goals is None for match in finished)
