"""Ligas europeias (ADR-0011). Todos os dados são sintéticos (synthetic), exceto os regulamentos versionados."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from brasileirao.config import RatingParams
from brasileirao.leagues.forecast import prepare, zone_clinch
from brasileirao.leagues.ingest import CompositionError, conference
from brasileirao.leagues.ranking import add_results, empty_head_to_head, resolve_order, validate_tiebreak_order
from brasileirao.leagues.rules import Zone, load_league_rules
from brasileirao.leagues.sources import SourceFormatError, parse_football_data, parse_openfootball
from brasileirao.pipeline import ModelConfig

PREMIER = ("points", "goal_difference", "goals_for", "h2h_points", "h2h_away_goals", "draw_lot")
LALIGA = ("points", "h2h_points", "h2h_goal_difference", "goal_difference", "goals_for", "draw_lot")


def _table(points: list[int], goal_difference: list[int], goals_for: list[int]) -> dict[str, np.ndarray]:
    return {
        "points": np.array(points),
        "goal_difference": np.array(goal_difference),
        "goals_for": np.array(goals_for),
        "wins": np.zeros(len(points), dtype=np.int64),
    }


def _h2h(results: list[tuple[int, int, int, int]], n_clubs: int = 3):
    """(mandante, visitante, gols do mandante, gols do visitante), synthetic."""
    home, away, home_goals, away_goals = (np.array(column, dtype=np.int64) for column in zip(*results, strict=True))
    return add_results(empty_head_to_head(n_clubs), home, away, home_goals, away_goals, 3, 1)


def test_premier_league_goal_difference_beats_head_to_head() -> None:
    table = _table([10, 10, 5], [5, 3, 0], [9, 9, 2])
    head_to_head = _h2h([(1, 0, 3, 0), (0, 1, 0, 1)])
    assert resolve_order(PREMIER, table, head_to_head, np.zeros(3))[:2] == [0, 1]


def test_laliga_head_to_head_beats_goal_difference() -> None:
    table = _table([10, 10, 5], [5, 3, 0], [9, 9, 2])
    head_to_head = _h2h([(1, 0, 3, 0), (0, 1, 0, 1)])
    assert resolve_order(LALIGA, table, head_to_head, np.zeros(3))[:2] == [1, 0]


def test_premier_league_away_goals_in_head_to_head() -> None:
    table = _table([10, 10, 5], [3, 3, 0], [9, 9, 2])
    head_to_head = _h2h([(0, 1, 1, 2), (1, 0, 0, 1)])
    assert resolve_order(PREMIER, table, head_to_head, np.zeros(3))[:2] == [1, 0]


def test_laliga_mini_league_among_three_clubs() -> None:
    table = _table([10, 10, 10], [9, 0, -9], [9, 5, 1])
    head_to_head = _h2h([(2, 0, 1, 0), (0, 2, 0, 0), (0, 1, 2, 0), (1, 0, 0, 0), (1, 2, 1, 1), (2, 1, 0, 0)])
    assert resolve_order(LALIGA, table, head_to_head, np.zeros(3)) == [2, 0, 1]


def test_full_tie_goes_to_draw_lot() -> None:
    table = _table([10, 10], [0, 0], [3, 3])
    head_to_head = _h2h([(0, 1, 1, 1), (1, 0, 1, 1)], n_clubs=2)
    assert resolve_order(PREMIER, table, head_to_head, np.array([0.1, 0.9])) == [1, 0]


def test_tiebreak_order_must_end_with_lot() -> None:
    with pytest.raises(ValueError, match="draw_lot"):
        validate_tiebreak_order(["points", "goal_difference"])


def test_versioned_rules_load_for_both_leagues() -> None:
    relegation = [load_league_rules(code, 2026).relegation_count for code in ("premier-league", "la-liga")]
    assert relegation == [3, 3]


OPENFOOTBALL_NEW = """= England | Premier League 2040/41 (synthetic)

▪ Regular Season - 1
Fri Dec 28 2040
  19:00   Alfa FC  2-1 (1-0)  Beta FC
                  (Fulano 10', 70';
                   Beltrano 80')
Sat Jan 4
  15:00   Gama FC  0-0  Delta FC
  15:00   Beta FC v Gama FC
"""

OPENFOOTBALL_OLD = """▪ Matchday 1
Sat Aug 13 2040
  15:00  Alfa FC              2-2 (2-2)  Beta FC
         Gama FC              0-1  Delta FC
"""


def test_openfootball_new_format_skips_scorers_and_crosses_year() -> None:
    rows = parse_openfootball(OPENFOOTBALL_NEW, 2040)
    assert [(row.match_date, row.home_goals) for row in rows] == [
        (date(2040, 12, 28), 2),
        (date(2041, 1, 4), 0),
        (date(2041, 1, 4), None),
    ]


def test_openfootball_old_format() -> None:
    rows = parse_openfootball(OPENFOOTBALL_OLD, 2040)
    assert [(row.home_name, row.away_goals, row.away_name) for row in rows] == [
        ("Alfa FC", 2, "Beta FC"),
        ("Gama FC", 1, "Delta FC"),
    ]


def test_openfootball_rejects_unknown_line() -> None:
    with pytest.raises(SourceFormatError):
        parse_openfootball(OPENFOOTBALL_OLD + "  isto não é um jogo\n", 2040)


def _api_match(status: str, home: int | None = None, away: int | None = None) -> dict[str, object]:
    return {
        "id": 1,
        "utcDate": "2040-10-01T19:00:00Z",
        "status": status,
        "matchday": 7,
        "homeTeam": {"name": "Alfa FC"},
        "awayTeam": {"name": "Beta FC"},
        "score": {"fullTime": {"home": home, "away": away}},
    }


def test_api_in_play_never_exposes_partial_score() -> None:
    rows = parse_football_data({"matches": [_api_match("IN_PLAY", 1, 0)]}, 2040, "Europe/London")
    assert (rows[0].status.value, rows[0].home_goals) == ("scheduled", None)


def test_api_awarded_result_fails() -> None:
    with pytest.raises(SourceFormatError):
        parse_football_data({"matches": [_api_match("AWARDED", 3, 0)]}, 2040, "Europe/London")


def test_api_local_date_uses_league_timezone() -> None:
    match = {**_api_match("FINISHED", 1, 0), "utcDate": "2040-10-01T23:30:00Z"}
    assert parse_football_data({"matches": [match]}, 2040, "Europe/Madrid")[0].match_date == date(2040, 10, 2)


def _record(match_id: str, match_date: date, home_goals: int) -> dict[str, object]:
    return {
        "match_id": match_id,
        "season": 2040,
        "match_date": match_date,
        "home_goals": home_goals,
        "away_goals": 0,
        "status": "finished",
    }


def test_conference_counts_score_mismatch() -> None:
    history = [_record("a", date(2040, 1, 1), 1), _record("b", date(2040, 1, 2), 2)]
    api_rows = [_record("a", date(2040, 1, 1), 1), _record("b", date(2040, 1, 2), 3)]
    assert conference(history, api_rows, 2040).score_mismatches == 1


def test_composition_error_is_a_value_error() -> None:
    assert issubclass(CompositionError, ValueError)


def test_zone_clinch_detects_relegation_and_safety() -> None:
    points = np.array([60] * 17 + [5, 5, 5], dtype=np.int64)
    states = zone_clinch(points, np.full(20, 3, dtype=np.int64), 3, Zone("relegation", "Rebaixamento", 18, 20, "down"))
    assert (states[19], states[0]) == ("in", "out")


def test_zone_clinch_stays_open_when_rivals_can_catch_up() -> None:
    points = np.array([70, 68] + [30] * 18, dtype=np.int64)
    states = zone_clinch(points, np.full(20, 1, dtype=np.int64), 3, Zone("title", "Título", 1, 1, "title"))
    assert states[0] is None


def test_current_table_ignores_head_to_head_mid_season(synthetic_matches: pd.DataFrame) -> None:
    rules = replace(load_league_rules("la-liga", 2026), season=2032)
    reference = synthetic_matches.loc[
        (synthetic_matches["season"] == 2032) & (synthetic_matches["status"] == "finished"), "match_date"
    ].max()
    _, _, simulator = prepare(
        synthetic_matches, rules, reference.date(), ModelConfig("elo_only", RatingParams(), False), 2030
    )
    table = simulator.observed_table
    expected = sorted(
        simulator.club_ids,
        key=lambda club: (
            -table.points[simulator.club_index[club]],
            -table.goal_difference[simulator.club_index[club]],
            -table.goals_for[simulator.club_index[club]],
            club,
        ),
    )
    assert simulator.observed_order(season_complete=False) == expected
