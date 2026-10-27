from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from brasileirao.config import RatingParams
from brasileirao.prediction.goals_model import GoalsModel, outcome_probabilities, score_matrix
from brasileirao.prediction.metrics import (
    brier_score,
    calibration_table,
    log_loss,
    outcome_index,
    ranked_probability_score,
)
from brasileirao.validation.backtest import compute_features


@pytest.fixture(scope="module")
def synthetic_features(synthetic_matches: pd.DataFrame) -> pd.DataFrame:
    return compute_features(synthetic_matches, RatingParams())


def test_score_matrix_sums_to_one() -> None:
    matrix = score_matrix(np.array([1.4]), np.array([1.1]), 0.0, 10)
    assert matrix.sum() == pytest.approx(1.0)


def test_dixon_coles_negative_rho_raises_draws() -> None:
    base = outcome_probabilities(score_matrix(np.array([1.3]), np.array([1.0]), 0.0, 10))
    adjusted = outcome_probabilities(score_matrix(np.array([1.3]), np.array([1.0]), -0.1, 10))
    assert adjusted[0, 1] > base[0, 1]


def test_stronger_home_rate_favours_home_win() -> None:
    probabilities = outcome_probabilities(score_matrix(np.array([2.5]), np.array([0.6]), 0.0, 10))
    assert probabilities[0, 0] > 0.7


def test_fitted_model_outcomes_are_probabilities(synthetic_features: pd.DataFrame) -> None:
    model = GoalsModel.fit(synthetic_features, "full")
    assert np.allclose(model.outcome_probabilities(synthetic_features).sum(axis=1), 1.0)


def test_elo_coefficient_positive_for_home_goals(synthetic_features: pd.DataFrame) -> None:
    model = GoalsModel.fit(synthetic_features, "elo_only")
    assert model.home_coefficients[0] > 0


def test_outcome_index_encodes_draw() -> None:
    assert outcome_index(np.array([1]), np.array([1])).tolist() == [1]


def test_perfect_forecast_has_zero_brier() -> None:
    assert brier_score(np.array([[1.0, 0.0, 0.0]]), np.array([0])) == pytest.approx(0.0)


def test_uniform_forecast_log_loss() -> None:
    assert log_loss(np.full((1, 3), 1 / 3), np.array([2])) == pytest.approx(np.log(3))


def test_rps_penalises_distant_miss_more() -> None:
    near = ranked_probability_score(np.array([[0.0, 1.0, 0.0]]), np.array([0]))
    far = ranked_probability_score(np.array([[0.0, 0.0, 1.0]]), np.array([0]))
    assert far > near


def test_calibration_table_counts_all_predictions() -> None:
    table = calibration_table(np.array([0.05, 0.5, 0.95]), np.array([0.0, 1.0, 1.0]))
    assert sum(row["n"] for row in table) == 3


def test_draw_inflation_raises_draw_probability() -> None:
    base = outcome_probabilities(score_matrix(np.array([1.3]), np.array([1.0]), 0.0, 10))
    inflated = outcome_probabilities(score_matrix(np.array([1.3]), np.array([1.0]), 0.0, 10, draw_inflation=0.1))
    assert inflated[0, 1] > base[0, 1]


def test_inflated_score_matrix_sums_to_one() -> None:
    matrix = score_matrix(np.array([1.4, 0.9]), np.array([1.1, 1.6]), 0.0, 10, draw_inflation=0.2)
    assert np.allclose(matrix.sum(axis=(-2, -1)), 1.0)


def test_fit_without_draw_inflation_keeps_it_zero(synthetic_features: pd.DataFrame) -> None:
    model = GoalsModel.fit(synthetic_features, "elo_attack_defense")
    assert model.draw_inflation == 0.0


def test_fitted_draw_inflation_moves_draw_rate_towards_observed(synthetic_features: pd.DataFrame) -> None:
    plain = GoalsModel.fit(synthetic_features, "elo_attack_defense", dixon_coles=False)
    inflated = GoalsModel.fit(synthetic_features, "elo_attack_defense", dixon_coles=False, draw_inflation=True)
    observed = float((synthetic_features["home_goals"] == synthetic_features["away_goals"]).mean())
    plain_gap = abs(plain.outcome_probabilities(synthetic_features)[:, 1].mean() - observed)
    inflated_gap = abs(inflated.outcome_probabilities(synthetic_features)[:, 1].mean() - observed)
    assert inflated_gap <= plain_gap


def test_coefficient_covariance_is_positive_definite(synthetic_features: pd.DataFrame) -> None:
    model = GoalsModel.fit(synthetic_features, "elo_attack_defense")
    assert np.all(np.linalg.eigvalsh(np.asarray(model.home_covariance)) > 0)


def test_parameter_draws_centre_on_point_estimate(synthetic_features: pd.DataFrame) -> None:
    model = GoalsModel.fit(synthetic_features, "elo_attack_defense")
    home_draws, _ = model.sample_parameters(20_000, np.random.default_rng(3))
    point = np.array([model.home_intercept, *model.home_coefficients])
    standard_error = np.sqrt(np.diag(np.asarray(model.home_covariance)))
    assert np.all(np.abs(home_draws.mean(axis=0) - point) < 0.05 * standard_error + 1e-9)


def test_expected_goals_by_draw_matches_point_estimate(synthetic_features: pd.DataFrame) -> None:
    model = GoalsModel.fit(synthetic_features, "elo_attack_defense")
    rows = synthetic_features.head(6)
    home_point = np.tile([model.home_intercept, *model.home_coefficients], (2, 1))
    away_point = np.tile([model.away_intercept, *model.away_coefficients], (2, 1))
    stacked = pd.concat([rows, rows], ignore_index=True)
    home_rate, _ = model.expected_goals_by_draw(stacked, home_point, away_point)
    assert np.allclose(home_rate.reshape(-1), np.tile(model.expected_goals(rows)[0], 2))
