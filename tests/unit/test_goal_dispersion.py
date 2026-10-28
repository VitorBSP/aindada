"""Dispersão dos gols (Conway-Maxwell-Poisson com média preservada). Todos os dados aqui são synthetic."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import poisson

from brasileirao.pipeline import load_model_config
from brasileirao.prediction.goals_model import GoalsModel, goal_pmf, score_matrix
from brasileirao.simulation.engine import _sample_scores
from brasileirao.validation.backtest import (
    goal_distribution_summary,
    observed_score_probabilities,
    total_goals_probabilities,
)
from brasileirao.validation.report import select_goal_dispersion

GOALS = np.arange(11)


def _synthetic_goal_frame(home_goals: np.ndarray, away_goals: np.ndarray) -> pd.DataFrame:
    """Placares synthetic com as colunas mínimas do treino (sem variáveis: feature_set intercept_only)."""
    return pd.DataFrame({"season": 2090, "home_goals": home_goals, "away_goals": away_goals, "source": "synthetic"})


def test_unit_dispersion_reproduces_poisson() -> None:
    assert np.allclose(goal_pmf(np.array([1.3]), 10, 1.0), poisson.pmf(GOALS, 1.3))


def test_dispersion_preserves_expected_goals() -> None:
    pmf = goal_pmf(np.array([0.7, 1.3, 2.4]), 10, 1.2)
    assert np.allclose(pmf @ GOALS, [0.7, 1.3, 2.4], atol=1e-4)


def test_dispersion_above_one_gives_variance_below_mean() -> None:
    pmf = goal_pmf(np.array([1.4]), 10, 1.3)[0]
    mean = pmf @ GOALS
    assert pmf @ GOALS**2 - mean**2 < mean


def test_dispersion_below_one_gives_variance_above_mean() -> None:
    pmf = goal_pmf(np.array([1.4]), 10, 0.8)[0]
    mean = pmf @ GOALS
    assert pmf @ GOALS**2 - mean**2 > mean


def test_dispersed_score_matrix_sums_to_one() -> None:
    matrix = score_matrix(np.array([1.4, 0.9]), np.array([1.1, 1.6]), 0.02, 10, goal_dispersion=1.15)
    assert np.allclose(matrix.sum(axis=(-2, -1)), 1.0)


def test_fitted_dispersion_detects_underdispersed_goals() -> None:
    generator = np.random.default_rng(11)
    frame = _synthetic_goal_frame(generator.binomial(4, 0.35, 3000), generator.binomial(4, 0.25, 3000))
    model = GoalsModel.fit(frame, "intercept_only", dixon_coles=False, goal_dispersion=True)
    assert model.goal_dispersion > 1.2


def test_fitted_dispersion_is_close_to_one_for_poisson_goals() -> None:
    generator = np.random.default_rng(12)
    frame = _synthetic_goal_frame(generator.poisson(1.4, 4000), generator.poisson(1.0, 4000))
    model = GoalsModel.fit(frame, "intercept_only", dixon_coles=False, goal_dispersion=True)
    assert model.goal_dispersion == pytest.approx(1.0, abs=0.08)


def test_fit_without_goal_dispersion_keeps_poisson() -> None:
    frame = _synthetic_goal_frame(np.array([0, 1, 2, 3]), np.array([1, 0, 1, 2]))
    assert GoalsModel.fit(frame, "intercept_only").goal_dispersion == 1.0


def test_sampled_goals_follow_dispersion() -> None:
    rates = np.full((20_000, 1), 1.4)
    poisson_home, _ = _sample_scores(rates, rates, 0.0, 10, 0.0, np.random.default_rng(5))
    dispersed_home, _ = _sample_scores(rates, rates, 0.0, 10, 0.0, np.random.default_rng(5), goal_dispersion=1.3)
    assert dispersed_home.var() < poisson_home.var()


def test_total_goals_probabilities_sum_to_one() -> None:
    matrices = score_matrix(np.array([1.4, 0.9]), np.array([1.1, 1.6]), 0.0, 10)
    assert np.allclose(total_goals_probabilities(matrices).sum(axis=1), 1.0)


def test_observed_score_probability_reads_the_matrix_cell() -> None:
    matrices = score_matrix(np.array([1.4]), np.array([1.1]), 0.0, 10)
    observed_score, _ = observed_score_probabilities(matrices, _synthetic_goal_frame(np.array([2]), np.array([1])))
    assert observed_score[0] == pytest.approx(matrices[0, 2, 1])


def test_goal_distribution_summary_counts_observed_over_lines() -> None:
    matrices = score_matrix(np.array([1.4, 1.4]), np.array([1.1, 1.1]), 0.0, 10)
    summary = goal_distribution_summary(matrices, _synthetic_goal_frame(np.array([2, 0]), np.array([1, 0])))
    assert summary["over"]["2.5"]["observed"] == pytest.approx(0.5)


def _match(log_loss: float, score_log_loss: float) -> dict[str, float]:
    return {"log_loss": log_loss, "score_log_loss": score_log_loss}


def _season(position_log_loss: float) -> dict[str, float]:
    return {"position_log_loss": position_log_loss}


def test_dispersion_selected_when_score_improves_and_outcomes_do_not_worsen() -> None:
    match = {"sem_dispersao": _match(1.0130, 2.7252), "dispersao_gols": _match(1.0128, 2.7230)}
    season = {"sem_dispersao": _season(2.2614), "dispersao_gols": _season(2.2620)}
    assert select_goal_dispersion(match, season)


def test_dispersion_rejected_when_outcome_log_loss_worsens() -> None:
    match = {"sem_dispersao": _match(1.0130, 2.7252), "dispersao_gols": _match(1.0131, 2.7200)}
    season = {"sem_dispersao": _season(2.2614), "dispersao_gols": _season(2.2600)}
    assert not select_goal_dispersion(match, season)


def test_dispersion_rejected_when_score_gain_is_within_tolerance() -> None:
    match = {"sem_dispersao": _match(1.0130, 2.7252), "dispersao_gols": _match(1.0129, 2.7248)}
    season = {"sem_dispersao": _season(2.2614), "dispersao_gols": _season(2.2600)}
    assert not select_goal_dispersion(match, season)


def test_dispersion_rejected_when_position_log_loss_worsens() -> None:
    match = {"sem_dispersao": _match(1.0130, 2.7252), "dispersao_gols": _match(1.0128, 2.7230)}
    season = {"sem_dispersao": _season(2.2614), "dispersao_gols": _season(2.2640)}
    assert not select_goal_dispersion(match, season)


def test_model_config_reads_goal_dispersion(tmp_path: Path) -> None:
    payload = {
        "feature_set": "elo_only",
        "rating_params": {"elo": {}, "attack_defense": {}, "form": {}},
        "goal_dispersion": True,
    }
    (tmp_path / "model_config.json").write_text(json.dumps(payload), encoding="utf-8")
    assert load_model_config(tmp_path).goal_dispersion


def test_model_config_without_goal_dispersion_defaults_to_poisson(tmp_path: Path) -> None:
    payload = {"feature_set": "elo_only", "rating_params": {"elo": {}, "attack_defense": {}, "form": {}}}
    (tmp_path / "model_config.json").write_text(json.dumps(payload), encoding="utf-8")
    assert not load_model_config(tmp_path).goal_dispersion
