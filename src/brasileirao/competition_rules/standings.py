"""Tabela de classificação e critérios de desempate (Art. 15)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from brasileirao.competition_rules.season_rules import SeasonRules

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class TableStats:
    """Estatísticas acumuladas por clube, na ordem de `club_ids`."""

    club_ids: tuple[str, ...]
    points: IntArray
    wins: IntArray
    draws: IntArray
    losses: IntArray
    goals_for: IntArray
    goals_against: IntArray
    red_cards: IntArray
    yellow_cards: IntArray
    head_to_head_points: IntArray
    head_to_head_goal_difference: IntArray

    @property
    def goal_difference(self) -> IntArray:
        return self.goals_for - self.goals_against

    @property
    def played(self) -> IntArray:
        return self.wins + self.draws + self.losses


def accumulate_table(
    club_ids: Sequence[str],
    home_index: Sequence[int],
    away_index: Sequence[int],
    home_goals: Sequence[int],
    away_goals: Sequence[int],
    rules: SeasonRules,
    red_cards: Sequence[int] | None = None,
    yellow_cards: Sequence[int] | None = None,
) -> TableStats:
    n_clubs = len(club_ids)
    points = np.zeros(n_clubs, dtype=np.int64)
    wins = np.zeros(n_clubs, dtype=np.int64)
    draws = np.zeros(n_clubs, dtype=np.int64)
    losses = np.zeros(n_clubs, dtype=np.int64)
    goals_for = np.zeros(n_clubs, dtype=np.int64)
    goals_against = np.zeros(n_clubs, dtype=np.int64)
    h2h_points = np.zeros((n_clubs, n_clubs), dtype=np.int64)
    h2h_goal_difference = np.zeros((n_clubs, n_clubs), dtype=np.int64)
    for home, away, scored_home, scored_away in zip(home_index, away_index, home_goals, away_goals, strict=True):
        goals_for[home] += scored_home
        goals_against[home] += scored_away
        goals_for[away] += scored_away
        goals_against[away] += scored_home
        h2h_goal_difference[home, away] += scored_home - scored_away
        h2h_goal_difference[away, home] += scored_away - scored_home
        if scored_home > scored_away:
            points[home] += rules.points_win
            wins[home] += 1
            losses[away] += 1
            h2h_points[home, away] += rules.points_win
        elif scored_home < scored_away:
            points[away] += rules.points_win
            wins[away] += 1
            losses[home] += 1
            h2h_points[away, home] += rules.points_win
        else:
            points[home] += rules.points_draw
            points[away] += rules.points_draw
            draws[home] += 1
            draws[away] += 1
            h2h_points[home, away] += rules.points_draw
            h2h_points[away, home] += rules.points_draw
    return TableStats(
        club_ids=tuple(club_ids),
        points=points,
        wins=wins,
        draws=draws,
        losses=losses,
        goals_for=goals_for,
        goals_against=goals_against,
        red_cards=np.asarray(red_cards if red_cards is not None else np.zeros(n_clubs), dtype=np.int64),
        yellow_cards=np.asarray(yellow_cards if yellow_cards is not None else np.zeros(n_clubs), dtype=np.int64),
        head_to_head_points=h2h_points,
        head_to_head_goal_difference=h2h_goal_difference,
    )


def _resolve_tie_group(
    group: list[int],
    points: IntArray,
    h2h_points: IntArray,
    h2h_goal_difference: IntArray,
    red_cards: IntArray,
    yellow_cards: IntArray,
    lot: FloatArray,
    head_to_head_max_clubs: int,
) -> list[int]:
    del points
    if len(group) == 2 and head_to_head_max_clubs >= 2:
        first, second = group
        first_key = (h2h_points[first, second], h2h_goal_difference[first, second])
        second_key = (h2h_points[second, first], h2h_goal_difference[second, first])
        if first_key != second_key:
            return [first, second] if first_key > second_key else [second, first]
    return sorted(group, key=lambda club: (red_cards[club], yellow_cards[club], -lot[club]))


def rank_clubs(
    points: IntArray,
    wins: IntArray,
    goal_difference: IntArray,
    goals_for: IntArray,
    h2h_points: IntArray,
    h2h_goal_difference: IntArray,
    red_cards: IntArray,
    yellow_cards: IntArray,
    lot: FloatArray,
    head_to_head_max_clubs: int = 2,
) -> list[int]:
    """Ordem final (índices dos clubes, do 1º ao último) segundo o Art. 15.

    `lot` substitui o sorteio: maior valor vence. Confronto direto só se aplica quando
    exatamente dois clubes seguem empatados após pontos, vitórias, saldo e gols pró.
    """
    primary_order = sorted(
        range(len(points)),
        key=lambda club: (-points[club], -wins[club], -goal_difference[club], -goals_for[club]),
    )
    final_order: list[int] = []
    position = 0
    while position < len(primary_order):
        club = primary_order[position]
        primary_key = (points[club], wins[club], goal_difference[club], goals_for[club])
        group = [club]
        position += 1
        while position < len(primary_order):
            candidate = primary_order[position]
            candidate_key = (points[candidate], wins[candidate], goal_difference[candidate], goals_for[candidate])
            if candidate_key != primary_key:
                break
            group.append(candidate)
            position += 1
        if len(group) == 1:
            final_order.extend(group)
        else:
            final_order.extend(
                _resolve_tie_group(
                    group,
                    points,
                    h2h_points,
                    h2h_goal_difference,
                    red_cards,
                    yellow_cards,
                    lot,
                    head_to_head_max_clubs,
                )
            )
    return final_order


def rank_table(stats: TableStats, rules: SeasonRules, lot: FloatArray | None = None) -> list[str]:
    draw_lot = lot if lot is not None else np.zeros(len(stats.club_ids))
    order = rank_clubs(
        stats.points,
        stats.wins,
        stats.goal_difference,
        stats.goals_for,
        stats.head_to_head_points,
        stats.head_to_head_goal_difference,
        stats.red_cards,
        stats.yellow_cards,
        draw_lot,
        rules.head_to_head_max_clubs,
    )
    return [stats.club_ids[club] for club in order]
