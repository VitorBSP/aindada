"""Ligas europeias (ADR-0011). Todos os dados são sintéticos (synthetic), exceto os regulamentos versionados."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from brasileirao.config import RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.leagues.forecast import build_forecast, prepare, zone_clinch
from brasileirao.leagues.gate import check_artifact, check_history
from brasileirao.leagues.history import build_history, round_end_dates
from brasileirao.leagues.ingest import CompositionError, conference
from brasileirao.leagues.ranking import add_results, empty_head_to_head, resolve_order, validate_tiebreak_order
from brasileirao.leagues.rules import Zone, load_league_rules
from brasileirao.leagues.schema import CompetitionHistory, LeagueForecast
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


# ---------------------------------------------------------------- histórico rodada a rodada (data/history.json)

TODAY = date(2033, 1, 1)
HISTORY_SIMULATIONS = 120


@pytest.fixture(scope="module")
def history_inputs(
    synthetic_matches: pd.DataFrame, synthetic_registry: ClubRegistry
) -> tuple[LeagueForecast, CompetitionHistory, pd.DataFrame]:
    rules = replace(load_league_rules("premier-league", 2026), season=2032)
    finished = synthetic_matches[(synthetic_matches["season"] == 2032) & (synthetic_matches["status"] == "finished")]
    # Um dia depois do último jogo: a edição ainda é a da última rodada e não pode duplicá-la na história.
    reference = finished["match_date"].max().date() + timedelta(days=1)
    sources = {
        "reference_date": reference.isoformat(),
        "sources": [
            {
                "tag": "synthetic@1",
                "source_name": "synthetic",
                "version": "1",
                "origin": "tests/fixtures",
                "retrieved_at": reference.isoformat(),
            }
        ],
    }
    config = ModelConfig("elo_only", RatingParams(), False)
    forecast = build_forecast(synthetic_matches, sources, rules, synthetic_registry, config, 200, 7, 2030)
    history = build_history(synthetic_matches, forecast, rules, config, 2030, HISTORY_SIMULATIONS)
    return forecast, history, synthetic_matches


def _findings(forecast: LeagueForecast, history: CompetitionHistory, **changes: object) -> list[str]:
    return check_history(
        history.model_copy(update=changes),
        forecast.competition,
        forecast.reference_date,
        {team.club_id for team in forecast.teams},
        {zone.zone_id: zone.last - zone.first + 1 for zone in forecast.zones},
        forecast.model_version,
        forecast.data_version,
        TODAY,
    )


def test_round_end_dates_use_the_last_finished_day_of_each_round(synthetic_matches: pd.DataFrame) -> None:
    ended = round_end_dates(synthetic_matches, 2032, date(2032, 12, 31))
    assert (ended[0][0], len(ended)) == (1, 30)


def test_round_end_dates_ignore_rounds_after_the_cutoff(synthetic_matches: pd.DataFrame) -> None:
    first_round_day = round_end_dates(synthetic_matches, 2032, date(2032, 12, 31))[0][1]
    assert round_end_dates(synthetic_matches, 2032, first_round_day) == [(1, first_round_day)]


def test_history_passes_its_gate(history_inputs: tuple) -> None:
    forecast, history, _ = history_inputs
    assert _findings(forecast, history) == []


def test_history_has_one_point_per_finished_round(history_inputs: tuple) -> None:
    _, history, _ = history_inputs
    assert [point.round for point in history.points] == list(range(1, 31))


def test_history_last_point_is_the_published_forecast(history_inputs: tuple) -> None:
    forecast, history, _ = history_inputs
    leader = forecast.teams[0]
    last = history.points[-1]
    assert (last.reference_date, last.teams[leader.club_id].zones["title"], last.n_simulations) == (
        forecast.reference_date,
        round(leader.zones["title"], 4),
        forecast.n_simulations,
    )


def test_history_earlier_points_are_reconstructions(history_inputs: tuple) -> None:
    _, history, _ = history_inputs
    assert (history.history_mode, all(point.reconstructed for point in history.points[:-1])) == ("reconstructed", True)


def test_history_published_edition_is_not_a_reconstruction(history_inputs: tuple) -> None:
    _, history, _ = history_inputs
    assert history.points[-1].reconstructed is False


def test_history_observed_matches_never_decrease(history_inputs: tuple) -> None:
    _, history, _ = history_inputs
    observed = [point.observed_matches for point in history.points]
    assert observed == sorted(observed)


def test_history_is_reproducible_with_the_seed(history_inputs: tuple) -> None:
    forecast, history, matches = history_inputs
    rules = replace(load_league_rules("premier-league", 2026), season=2032)
    again = build_history(
        matches, forecast, rules, ModelConfig("elo_only", RatingParams(), False), 2030, HISTORY_SIMULATIONS
    )
    assert again.points[3].teams == history.points[3].teams


def test_history_uses_only_games_up_to_each_date(history_inputs: tuple) -> None:
    _, history, _ = history_inputs
    assert history.points[0].observed_matches < history.points[-1].observed_matches


def test_gate_rejects_unsorted_history_dates(history_inputs: tuple) -> None:
    forecast, history, _ = history_inputs
    assert any("fora de ordem" in item for item in _findings(forecast, history, points=history.points[::-1]))


def test_gate_rejects_history_that_ends_before_the_edition(history_inputs: tuple) -> None:
    forecast, history, _ = history_inputs
    assert any("termina em" in item for item in _findings(forecast, history, points=history.points[:-1]))


def test_gate_rejects_history_from_another_competition(history_inputs: tuple) -> None:
    forecast, history, _ = history_inputs
    assert any("publicado em" in item for item in _findings(forecast, history, competition="la-liga"))


def test_gate_rejects_history_with_another_model_version(history_inputs: tuple) -> None:
    forecast, history, _ = history_inputs
    assert any("modelo ou dados" in item for item in _findings(forecast, history, model_version="outro"))


def test_gate_rejects_earlier_point_without_the_reconstruction_mark(history_inputs: tuple) -> None:
    forecast, history, _ = history_inputs
    points = [history.points[0].model_copy(update={"reconstructed": False}), *history.points[1:]]
    assert any("reconstructed" in item for item in _findings(forecast, history, points=points))


def test_gate_rejects_history_mode_that_does_not_match_the_points(history_inputs: tuple) -> None:
    forecast, history, _ = history_inputs
    assert any("history_mode" in item for item in _findings(forecast, history, history_mode="recorded"))


def test_gate_rejects_zone_probabilities_that_do_not_add_up(history_inputs: tuple) -> None:
    forecast, history, _ = history_inputs
    point = history.points[2]
    club_id = next(iter(point.teams))
    team = point.teams[club_id].model_copy(update={"zones": {**point.teams[club_id].zones, "title": 0.9}})
    broken = point.model_copy(update={"teams": {**point.teams, club_id: team}})
    points = [*history.points[:2], broken, *history.points[3:]]
    assert any("soma da zona title" in item for item in _findings(forecast, history, points=points))


def test_gate_rejects_duplicate_positions(history_inputs: tuple) -> None:
    forecast, history, _ = history_inputs
    point = history.points[2]
    first, second = list(point.teams)[:2]
    clone = point.teams[first].model_copy(update={"position": point.teams[second].position})
    broken = point.model_copy(update={"teams": {**point.teams, first: clone}})
    points = [*history.points[:2], broken, *history.points[3:]]
    assert any("posições" in item for item in _findings(forecast, history, points=points))


def test_gate_rejects_empty_history(history_inputs: tuple) -> None:
    forecast, history, _ = history_inputs
    assert any("nenhum ponto" in item for item in _findings(forecast, history, points=[]))


def _site(tmp_path: Path, forecast: LeagueForecast, history: CompetitionHistory | None) -> Path:
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    for name in ("index.html", "app.js", "styles.css"):
        (site / name).write_text("x", encoding="utf-8")
    (site / "data" / "forecast.json").write_text(forecast.model_dump_json(), encoding="utf-8")
    if history is not None:
        (site / "data" / "history.json").write_text(history.model_dump_json(), encoding="utf-8")
    return site


def test_artifact_with_history_passes_the_gate(history_inputs: tuple, tmp_path: Path) -> None:
    forecast, history, _ = history_inputs
    assert check_artifact(_site(tmp_path, forecast, history), None, TODAY, forecast.competition) == []


def test_artifact_without_history_still_passes_the_gate(history_inputs: tuple, tmp_path: Path) -> None:
    forecast, _, _ = history_inputs
    assert check_artifact(_site(tmp_path, forecast, None), None, TODAY, forecast.competition) == []


def test_artifact_with_unreadable_history_is_rejected(history_inputs: tuple, tmp_path: Path) -> None:
    forecast, _, _ = history_inputs
    site = _site(tmp_path, forecast, None)
    (site / "data" / "history.json").write_text("{}", encoding="utf-8")
    assert any(
        "history.json fora do esquema" in item for item in check_artifact(site, None, TODAY, forecast.competition)
    )
