"""Ratings dinâmicos de ataque e defesa (Poisson online).

log(gols esperados do mandante)  = base + mando + ataque_mandante - defesa_visitante
log(gols esperados do visitante) = base + ataque_visitante - defesa_mandante

Após cada partida, ataque e defesa recebem um passo de gradiente da log-verossimilhança de
Poisson, o que ajusta automaticamente pela força do adversário.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

import numpy as np
import numpy.typing as npt

from brasileirao.config import AttackDefenseParams

ArrayLike = TypeVar("ArrayLike", float, npt.NDArray[np.float64])


def expected_log_goals(
    base: float, home_effect: float, attack: ArrayLike, opponent_defense: ArrayLike, at_home: bool
) -> ArrayLike:
    log_rate: ArrayLike = base + (home_effect if at_home else 0.0) + attack - opponent_defense
    return log_rate


@dataclass(frozen=True)
class AttackDefenseUpdate(Generic[ArrayLike]):
    home_attack: ArrayLike
    home_defense: ArrayLike
    away_attack: ArrayLike
    away_defense: ArrayLike
    home_error: ArrayLike
    away_error: ArrayLike


def attack_defense_update(
    base: float,
    home_effect: float,
    home_attack: ArrayLike,
    home_defense: ArrayLike,
    away_attack: ArrayLike,
    away_defense: ArrayLike,
    home_goals: ArrayLike,
    away_goals: ArrayLike,
    params: AttackDefenseParams,
) -> AttackDefenseUpdate[ArrayLike]:
    expected_home = np.exp(expected_log_goals(base, home_effect, home_attack, away_defense, True))
    expected_away = np.exp(expected_log_goals(base, home_effect, away_attack, home_defense, False))
    home_error: ArrayLike = home_goals - expected_home
    away_error: ArrayLike = away_goals - expected_away
    rate = params.learning_rate
    return AttackDefenseUpdate(
        home_attack=home_attack + rate * home_error,
        home_defense=home_defense - rate * away_error,
        away_attack=away_attack + rate * away_error,
        away_defense=away_defense - rate * home_error,
        home_error=home_error,
        away_error=away_error,
    )
