"""Placares mais prováveis e P(3+ gols) a partir da matriz de placares. Matrizes synthetic."""

from __future__ import annotations

import numpy as np
import pytest

from brasileirao.prediction.goals_model import score_matrix, top_scores, total_goals_at_least
from brasileirao.storage.schema import MatchPrediction

SYNTHETIC_MATRICES = score_matrix(np.array([1.45, 2.3, 0.8]), np.array([1.05, 0.7, 1.6]), 0.02, 10, 0.0, 1.17)


def test_three_plus_goals_is_complement_of_zero_one_two() -> None:
    goals = np.add.outer(np.arange(11), np.arange(11))
    zero_to_two = np.array([matrix[goals <= 2].sum() for matrix in SYNTHETIC_MATRICES])
    assert np.allclose(total_goals_at_least(SYNTHETIC_MATRICES, 3), 1.0 - zero_to_two)


def test_three_plus_goals_is_a_probability() -> None:
    probabilities = total_goals_at_least(SYNTHETIC_MATRICES, 3)
    assert np.all((probabilities > 0.0) & (probabilities < 1.0))


def test_top_scores_are_in_decreasing_order() -> None:
    probabilities = [probability for _, _, probability in top_scores(SYNTHETIC_MATRICES[0])]
    assert probabilities == sorted(probabilities, reverse=True)


def test_top_scores_returns_three_distinct_scores() -> None:
    scores = {(home, away) for home, away, _ in top_scores(SYNTHETIC_MATRICES[1])}
    assert len(scores) == 3


def test_top_score_matches_argmax() -> None:
    home, away, _ = top_scores(SYNTHETIC_MATRICES[2])[0]
    assert (home, away) == divmod(int(np.argmax(SYNTHETIC_MATRICES[2])), 11)


def test_top_score_probabilities_read_the_matrix() -> None:
    home, away, probability = top_scores(SYNTHETIC_MATRICES[0])[1]
    assert probability == pytest.approx(SYNTHETIC_MATRICES[0][home, away])


def test_top_scores_sum_does_not_exceed_one() -> None:
    assert sum(probability for _, _, probability in top_scores(SYNTHETIC_MATRICES[0])) < 1.0


def test_tied_scores_keep_matrix_order() -> None:
    tied = np.zeros((3, 3))
    tied[0, 1] = tied[1, 0] = tied[1, 1] = 0.3
    tied[2, 2] = 0.1
    assert [(home, away) for home, away, _ in top_scores(tied)] == [(0, 1), (1, 0), (1, 1)]


def test_old_match_prediction_without_new_fields_is_valid() -> None:
    payload = {
        "match_id": "synthetic-1",
        "round": 1,
        "match_date": "2032-05-01",
        "home_id": "sint-a",
        "away_id": "sint-b",
        "status": "scheduled",
        "most_likely_score": "1-0",
    }
    assert MatchPrediction.model_validate(payload).top_scores is None
