"""Art. 15: critérios de desempate."""

from __future__ import annotations

import numpy as np

from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.competition_rules.standings import accumulate_table, rank_clubs, rank_table


def _rank(
    points, wins, goal_difference, goals_for, h2h_points=None, h2h_goal_difference=None, red=None, yellow=None, lot=None
) -> list[int]:
    size = len(points)
    zeros = np.zeros(size, dtype=np.int64)
    return rank_clubs(
        np.array(points),
        np.array(wins),
        np.array(goal_difference),
        np.array(goals_for),
        np.array(h2h_points) if h2h_points is not None else np.zeros((size, size), dtype=np.int64),
        np.array(h2h_goal_difference) if h2h_goal_difference is not None else np.zeros((size, size), dtype=np.int64),
        np.array(red) if red is not None else zeros,
        np.array(yellow) if yellow is not None else zeros,
        np.array(lot, dtype=float) if lot is not None else np.zeros(size),
    )


def test_points_decide_first() -> None:
    assert _rank([10, 12], [3, 3], [0, 0], [5, 5]) == [1, 0]


def test_wins_break_points_tie() -> None:
    assert _rank([10, 10], [2, 3], [5, 0], [9, 5]) == [1, 0]


def test_goal_difference_breaks_wins_tie() -> None:
    assert _rank([10, 10], [3, 3], [1, 4], [9, 5]) == [1, 0]


def test_goals_for_breaks_goal_difference_tie() -> None:
    assert _rank([10, 10], [3, 3], [2, 2], [5, 8]) == [1, 0]


def test_head_to_head_points_between_two_clubs() -> None:
    assert _rank([10, 10], [3, 3], [2, 2], [5, 5], h2h_points=[[0, 1], [4, 0]]) == [1, 0]


def test_head_to_head_goal_difference_after_points() -> None:
    order = _rank([10, 10], [3, 3], [2, 2], [5, 5], h2h_points=[[0, 3], [3, 0]], h2h_goal_difference=[[0, -1], [1, 0]])
    assert order == [1, 0]


def test_head_to_head_ignored_with_three_tied_clubs() -> None:
    """§ 2º: com mais de dois empatados, vai direto aos cartões."""
    h2h = [[0, 6, 6], [0, 0, 0], [0, 0, 0]]
    order = _rank([10, 10, 10], [3, 3, 3], [2, 2, 2], [5, 5, 5], h2h_points=h2h, red=[2, 0, 1])
    assert order == [1, 2, 0]


def test_fewer_red_cards_break_tie() -> None:
    assert _rank([10, 10], [3, 3], [2, 2], [5, 5], red=[3, 1]) == [1, 0]


def test_fewer_yellow_cards_after_red_cards() -> None:
    assert _rank([10, 10], [3, 3], [2, 2], [5, 5], yellow=[40, 30]) == [1, 0]


def test_draw_lot_is_last_resort() -> None:
    assert _rank([10, 10], [3, 3], [2, 2], [5, 5], lot=[0.1, 0.9]) == [1, 0]


def test_accumulate_table_counts_points(rules_2026: SeasonRules) -> None:
    stats = accumulate_table(["a", "b", "c"], [0, 1, 2], [1, 2, 0], [2, 1, 0], [0, 1, 0], rules_2026)
    assert stats.points.tolist() == [4, 1, 2]


def test_rank_table_returns_club_ids(rules_2026: SeasonRules) -> None:
    stats = accumulate_table(["a", "b"], [0], [1], [0], [3], rules_2026)
    assert rank_table(stats, rules_2026) == ["b", "a"]
