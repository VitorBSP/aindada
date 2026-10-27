"""Métricas probabilísticas para 1X2 e gols."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]

EPSILON = 1e-12


def outcome_index(home_goals: IntArray, away_goals: IntArray) -> IntArray:
    """0 = mandante, 1 = empate, 2 = visitante."""
    index: IntArray = np.where(home_goals > away_goals, 0, np.where(home_goals == away_goals, 1, 2))
    return index


def log_loss(probabilities: FloatArray, outcomes: IntArray) -> float:
    chosen = probabilities[np.arange(len(outcomes)), outcomes]
    return float(-np.mean(np.log(np.clip(chosen, EPSILON, 1.0))))


def brier_score(probabilities: FloatArray, outcomes: IntArray) -> float:
    one_hot = np.eye(probabilities.shape[1])[outcomes]
    return float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1)))


def ranked_probability_score(probabilities: FloatArray, outcomes: IntArray) -> float:
    one_hot = np.eye(probabilities.shape[1])[outcomes]
    cumulative_gap = np.cumsum(probabilities, axis=1) - np.cumsum(one_hot, axis=1)
    return float(np.mean(np.sum(cumulative_gap[:, :-1] ** 2, axis=1) / (probabilities.shape[1] - 1)))


def poisson_deviance(observed: FloatArray, expected: FloatArray) -> float:
    safe_expected = np.clip(expected, EPSILON, None)
    ratio_term = np.where(observed > 0, observed * np.log(np.clip(observed, EPSILON, None) / safe_expected), 0.0)
    return float(np.mean(2.0 * (ratio_term - (observed - safe_expected))))


def binary_brier(probabilities: FloatArray, outcomes: FloatArray) -> float:
    return float(np.mean((probabilities - outcomes) ** 2))


def calibration_table(probabilities: FloatArray, outcomes: FloatArray, n_bins: int = 10) -> list[dict[str, float]]:
    """Calibração de previsões binárias (prob. prevista vs. frequência observada por faixa)."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_index = np.clip(np.digitize(probabilities, edges[1:-1]), 0, n_bins - 1)
    table: list[dict[str, float]] = []
    for bin_number in range(n_bins):
        in_bin = bin_index == bin_number
        if not in_bin.any():
            continue
        table.append(
            {
                "bin_low": float(edges[bin_number]),
                "bin_high": float(edges[bin_number + 1]),
                "n": float(in_bin.sum()),
                "mean_predicted": float(probabilities[in_bin].mean()),
                "observed_rate": float(outcomes[in_bin].mean()),
            }
        )
    return table


def expected_calibration_error(table: list[dict[str, float]]) -> float:
    total = sum(row["n"] for row in table)
    if total == 0:
        return 0.0
    return float(sum(row["n"] * abs(row["mean_predicted"] - row["observed_rate"]) for row in table) / total)
