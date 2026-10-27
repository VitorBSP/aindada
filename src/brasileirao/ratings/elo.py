"""Elo dinâmico com vantagem de mando e multiplicador de saldo de gols.

As funções aceitam escalares ou arrays NumPy, de modo que o histórico real e a
simulação vetorizada usam exatamente a mesma regra de atualização.
"""

from __future__ import annotations

from typing import TypeVar, cast

import numpy as np
import numpy.typing as npt

from brasileirao.config import EloParams

ArrayLike = TypeVar("ArrayLike", float, npt.NDArray[np.float64])


def expected_home_score(home_rating: ArrayLike, away_rating: ArrayLike, home_advantage: float) -> ArrayLike:
    rating_gap = home_rating + home_advantage - away_rating
    expected: ArrayLike = 1.0 / (1.0 + np.power(10.0, -rating_gap / 400.0))
    return expected


def goal_difference_multiplier(goal_difference: ArrayLike) -> ArrayLike:
    absolute_difference = np.abs(goal_difference)
    multiplier = np.where(
        absolute_difference <= 1,
        1.0,
        np.where(absolute_difference == 2, 1.5, (11.0 + absolute_difference) / 8.0),
    )
    return cast(ArrayLike, multiplier)


def match_score(home_goals: ArrayLike, away_goals: ArrayLike) -> ArrayLike:
    score = np.where(home_goals > away_goals, 1.0, np.where(home_goals == away_goals, 0.5, 0.0))
    return cast(ArrayLike, score)


def elo_delta(
    home_rating: ArrayLike,
    away_rating: ArrayLike,
    home_goals: ArrayLike,
    away_goals: ArrayLike,
    params: EloParams,
) -> ArrayLike:
    """Variação do rating do mandante (o visitante recebe o negativo)."""
    expected = expected_home_score(home_rating, away_rating, params.home_advantage)
    actual = match_score(home_goals, away_goals)
    multiplier = goal_difference_multiplier(home_goals - away_goals)
    delta: ArrayLike = params.k_factor * multiplier * (actual - expected)
    return delta
