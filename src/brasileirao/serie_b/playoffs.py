"""Fase de playoffs da Série B (Art. 13): ida na casa do pior colocado, volta na casa do melhor.

Vence quem somar mais pontos nos dois jogos; empate em pontos: saldo de gols e depois a melhor posição
na classificação final. Os ratings ficam fixos na data de referência, como na simulação da tabela.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from brasileirao.prediction.goals_model import GoalsModel, score_matrix
from brasileirao.ratings.history import RatingState, match_features

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class PairRates:
    """Gols esperados de cada par mandante (linha) x visitante (coluna), na ordem de `club_ids`."""

    home: FloatArray
    away: FloatArray


def pair_rates(state: RatingState, model: GoalsModel, club_ids: tuple[str, ...]) -> PairRates:
    n_clubs = len(club_ids)
    rows = [match_features(state, state.ratings[home], state.ratings[away]) for home in club_ids for away in club_ids]
    home_rate, away_rate = model.expected_goals(pd.DataFrame(rows))
    return PairRates(home=home_rate.reshape(n_clubs, n_clubs), away=away_rate.reshape(n_clubs, n_clubs))


def sample_legs(
    home_index: IntArray, away_index: IntArray, rates: PairRates, model: GoalsModel, generator: np.random.Generator
) -> tuple[IntArray, IntArray]:
    """Um placar por simulação. Os uniformes são sorteados de uma vez, na ordem das simulações."""
    max_goals = model.max_goals
    draws = generator.random(len(home_index))
    home_goals = np.zeros(len(home_index), dtype=np.int64)
    away_goals = np.zeros(len(home_index), dtype=np.int64)
    pair_codes = home_index * rates.home.shape[0] + away_index
    for pair_code in np.unique(pair_codes):
        selected = np.flatnonzero(pair_codes == pair_code)
        home, away = divmod(int(pair_code), rates.home.shape[0])
        probabilities = score_matrix(
            np.array([rates.home[home, away]]),
            np.array([rates.away[home, away]]),
            model.rho,
            max_goals,
            model.draw_inflation,
            model.goal_dispersion,
        ).reshape(-1)
        cumulative = np.cumsum(probabilities)
        flat = np.minimum(
            np.searchsorted(cumulative / cumulative[-1], draws[selected], side="right"), len(cumulative) - 1
        )
        home_goals[selected] = flat // (max_goals + 1)
        away_goals[selected] = flat % (max_goals + 1)
    return home_goals, away_goals


def _points(goals_for: IntArray, goals_against: IntArray) -> IntArray:
    return np.where(goals_for > goals_against, 3, np.where(goals_for == goals_against, 1, 0))


@dataclass(frozen=True)
class PlayoffResult:
    """`winners[s, g]`: índice do clube que sobe pelo grupo `g` na simulação `s`."""

    better: IntArray
    worse: IntArray
    winners: IntArray


def simulate_playoffs(
    final_order: IntArray,
    groups: tuple[tuple[int, int], ...],
    rates: PairRates,
    model: GoalsModel,
    generator: np.random.Generator,
) -> PlayoffResult:
    n_simulations = final_order.shape[0]
    better = np.empty((n_simulations, len(groups)), dtype=np.int64)
    worse = np.empty_like(better)
    winners = np.empty_like(better)
    for group, (better_position, worse_position) in enumerate(groups):
        better_club = final_order[:, better_position - 1]
        worse_club = final_order[:, worse_position - 1]
        first_home, first_away = sample_legs(worse_club, better_club, rates, model, generator)
        second_home, second_away = sample_legs(better_club, worse_club, rates, model, generator)
        better_points = _points(first_away, first_home) + _points(second_home, second_away)
        worse_points = _points(first_home, first_away) + _points(second_away, second_home)
        better_goal_difference = (first_away + second_home) - (first_home + second_away)
        worse_advances = (worse_points > better_points) | (
            (worse_points == better_points) & (better_goal_difference < 0)
        )
        better[:, group], worse[:, group] = better_club, worse_club
        winners[:, group] = np.where(worse_advances, worse_club, better_club)
    return PlayoffResult(better=better, worse=worse, winners=winners)
