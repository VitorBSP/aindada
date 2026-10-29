"""Classificação com critérios de desempate configuráveis (ADR-0011).

Os critérios vêm do TOML da competição, na ordem do regulamento. Critérios de tabela (`points`,
`goal_difference`, `goals_for`, `wins`) valem para o campeonato inteiro; critérios de confronto direto
(`h2h_points`, `h2h_goal_difference`, `h2h_away_goals`) são recalculados só entre os clubes ainda empatados,
como uma mini-tabela. Cada critério divide o grupo empatado em subgrupos, e cada subgrupo continua a
partir do critério seguinte. `draw_lot` encerra a ordem (sorteio, campo neutro ou critério sem dados).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]

TABLE_KEYS = frozenset({"points", "goal_difference", "goals_for", "wins"})
HEAD_TO_HEAD_KEYS = frozenset({"h2h_points", "h2h_goal_difference", "h2h_away_goals"})
LOT_KEY = "draw_lot"
SUPPORTED_KEYS = TABLE_KEYS | HEAD_TO_HEAD_KEYS | {LOT_KEY}


def validate_tiebreak_order(order: Sequence[str]) -> tuple[str, ...]:
    unknown = [key for key in order if key not in SUPPORTED_KEYS]
    if unknown:
        raise ValueError(f"critérios de desempate sem implementação: {unknown}")
    if not order or order[0] != "points" or order[-1] != LOT_KEY:
        raise ValueError("a ordem começa por 'points' e termina em 'draw_lot'")
    return tuple(order)


@dataclass(frozen=True)
class HeadToHead:
    """Matrizes [i, j] dos jogos entre i e j: pontos de i, gols de i, gols sofridos por i, gols de i fora."""

    points: IntArray
    goals_for: IntArray
    goals_against: IntArray
    away_goals: IntArray


def empty_head_to_head(n_clubs: int) -> HeadToHead:
    def zeros() -> IntArray:
        return np.zeros((n_clubs, n_clubs), dtype=np.int64)

    return HeadToHead(zeros(), zeros(), zeros(), zeros())


def add_results(
    head_to_head: HeadToHead,
    home_index: IntArray,
    away_index: IntArray,
    home_goals: IntArray,
    away_goals: IntArray,
    points_win: int,
    points_draw: int,
) -> HeadToHead:
    points = head_to_head.points.copy()
    goals_for = head_to_head.goals_for.copy()
    goals_against = head_to_head.goals_against.copy()
    away = head_to_head.away_goals.copy()
    home_points = np.where(home_goals > away_goals, points_win, np.where(home_goals == away_goals, points_draw, 0))
    away_points = np.where(away_goals > home_goals, points_win, np.where(home_goals == away_goals, points_draw, 0))
    np.add.at(points, (home_index, away_index), home_points)
    np.add.at(points, (away_index, home_index), away_points)
    np.add.at(goals_for, (home_index, away_index), home_goals)
    np.add.at(goals_for, (away_index, home_index), away_goals)
    np.add.at(goals_against, (home_index, away_index), away_goals)
    np.add.at(goals_against, (away_index, home_index), home_goals)
    np.add.at(away, (away_index, home_index), away_goals)
    return HeadToHead(points, goals_for, goals_against, away)


def _key_values(key: str, group: IntArray, table: dict[str, IntArray], head_to_head: HeadToHead) -> IntArray:
    if key in TABLE_KEYS:
        return table[key][group]
    rows, columns = np.ix_(group, group)
    if key == "h2h_points":
        return head_to_head.points[rows, columns].sum(axis=1)
    if key == "h2h_goal_difference":
        return (head_to_head.goals_for[rows, columns] - head_to_head.goals_against[rows, columns]).sum(axis=1)
    return head_to_head.away_goals[rows, columns].sum(axis=1)


def resolve_order(
    order: Sequence[str],
    table: dict[str, IntArray],
    head_to_head: HeadToHead,
    lot: FloatArray,
    group: IntArray | None = None,
    start: int = 0,
) -> list[int]:
    """Índices dos clubes do melhor para o pior. `table` tem um valor por clube para cada critério de tabela."""
    members = np.arange(len(lot)) if group is None else group
    if len(members) <= 1:
        return [int(club) for club in members]
    key = order[start]
    if key == LOT_KEY:
        return [int(club) for club in members[np.argsort(-lot[members], kind="stable")]]
    values = _key_values(key, members, table, head_to_head)
    ranked: list[int] = []
    for value in sorted(set(values.tolist()), reverse=True):
        subgroup = members[values == value]
        ranked.extend(resolve_order(order, table, head_to_head, lot, subgroup, start + 1))
    return ranked
