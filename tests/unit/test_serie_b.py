"""Série B (ADR-0010). Todos os dados são sintéticos (synthetic), exceto o regulamento versionado."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from brasileirao.config import RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.pipeline import ModelConfig, load_model_config
from brasileirao.prediction.goals_model import GoalsModel
from brasileirao.serie_b.forecast import build_forecast, clinched_flags
from brasileirao.serie_b.gate import check_artifact, check_forecast
from brasileirao.serie_b.ingest import (
    CompositionError,
    check_against_standings,
    imputed_rounds,
    wikipedia_with_schedule,
)
from brasileirao.serie_b.playoffs import PairRates, simulate_playoffs
from brasileirao.serie_b.rules import load_serie_b_rules
from brasileirao.serie_b.sources import (
    SourceFormatError,
    parse_openfootball,
    parse_portuguese_day,
    parse_wikipedia_matrix,
    parse_wikipedia_standings,
)
from brasileirao.validation.report import rating_params_to_dict

TODAY = date(2100, 1, 1)

OPENFOOTBALL_SYNTHETIC = """= Brasileiro Série B 2040 (synthetic)

# Date       Fri Dec 7 2040 - Sat Jan 12 2041 (36d)

▪ Matchday 1
  Fri Dec 7 2040
    19:00  Alfa AA                 v Beta BB                  2-1 (1-0)
  Sat Dec 8
           Gama GG                 v Delta DD                 3-0    [awarded]

▪ Matchday 2
  Sat Jan 12
    16:00  Beta BB                 v Gama GG
"""

WIKI_SYNTHETIC = """Texto sintético (synthetic).
{{#invoke:sports results|main
|update = 27 de outubro
|team1=ALF |team2=BET |team3=GAM
|name_ALF={{Futebol Alfa}}
|name_BET=[[Beta Clube|Beta]]
|name_GAM={{Futebol Gama}}
|match_ALF_BET=1–0
|match_ALF_GAM=[[Clássico sintético|2–2]]
|match_BET_ALF=
|match_BET_GAM=0-3
|match_GAM_ALF=1–1<ref>nota</ref>
|match_GAM_BET=
}}
|name_XYZ={{Futebol Fora}}
"""


@pytest.fixture(scope="module")
def openfootball_rows() -> list:
    return parse_openfootball(OPENFOOTBALL_SYNTHETIC, 2040)


def test_openfootball_reads_every_fixture(openfootball_rows: list) -> None:
    assert len(openfootball_rows) == 3


def test_openfootball_crosses_the_year(openfootball_rows: list) -> None:
    assert openfootball_rows[2].match_date == date(2041, 1, 12)


def test_openfootball_marks_awarded_result(openfootball_rows: list) -> None:
    assert openfootball_rows[1].awarded and openfootball_rows[1].home_goals == 3


def test_openfootball_keeps_missing_score_as_unknown(openfootball_rows: list) -> None:
    assert openfootball_rows[2].home_goals is None


def test_openfootball_rejects_unknown_lines() -> None:
    with pytest.raises(SourceFormatError):
        parse_openfootball(OPENFOOTBALL_SYNTHETIC + "  linha estranha\n", 2040)


def test_wikipedia_matrix_reads_scores_through_markup() -> None:
    matrix = parse_wikipedia_matrix(WIKI_SYNTHETIC, 2040)
    scores = {(r.home_name, r.away_name): (r.home_goals, r.away_goals) for r in matrix.results}
    assert (
        scores[("Alfa", "Gama")] == (2, 2) and scores[("Gama", "Alfa")] == (1, 1) and scores[("Beta", "Gama")] == (0, 3)
    )


def test_wikipedia_matrix_keeps_empty_cells_unplayed() -> None:
    matrix = parse_wikipedia_matrix(WIKI_SYNTHETIC, 2040)
    assert sum(result.home_goals is None for result in matrix.results) == 2


def test_wikipedia_matrix_ignores_text_after_the_module() -> None:
    matrix = parse_wikipedia_matrix(WIKI_SYNTHETIC, 2040)
    assert {result.home_name for result in matrix.results} == {"Alfa", "Beta", "Gama"}


def test_wikipedia_matrix_rejects_illegible_score() -> None:
    with pytest.raises(SourceFormatError):
        parse_wikipedia_matrix(WIKI_SYNTHETIC.replace("0-3", "W.O."), 2040)


def test_wikipedia_matrix_rejects_missing_pair() -> None:
    with pytest.raises(SourceFormatError):
        parse_wikipedia_matrix(WIKI_SYNTHETIC.replace("|match_GAM_BET=\n", ""), 2040)


def test_wikipedia_update_becomes_cutoff_date() -> None:
    assert parse_wikipedia_matrix(WIKI_SYNTHETIC, 2040).cutoff_date() == date(2040, 10, 27)


def test_complete_season_has_no_cutoff() -> None:
    assert parse_portuguese_day("complete", 2040) is None


def test_imputed_rounds_never_repeat_a_club_in_a_round() -> None:
    clubs = [f"c{index}" for index in range(8)]
    pairs = [(home, away) for home in clubs for away in clubs if home != away]
    slots = imputed_rounds(pairs)
    seen = {(slot, club) for slot, pair in zip(slots, pairs, strict=True) for club in pair}
    assert len(seen) == 2 * len(pairs)


def test_schedule_join_counts_score_mismatches() -> None:
    registry = ClubRegistry(
        clubs={},
        alias_index={
            "Alfa": "alfa",
            "Beta": "beta",
            "Gama": "gama",
            "Alfa AA": "alfa",
            "Beta BB": "beta",
            "Gama GG": "gama",
        },
    )
    complete = WIKI_SYNTHETIC.replace("|match_BET_ALF=", "|match_BET_ALF=2–1").replace(
        "|match_GAM_BET=", "|match_GAM_BET=0–0"
    )
    matrix = parse_wikipedia_matrix(complete, 2040)
    schedule_text = "# Date       Fri Mar 2 2040 - x\n▪ Matchday 1\n  Fri Mar 2 2040\n" + "".join(
        f"    {home} v {away} {score}\n"
        for home, away, score in (
            ("Alfa AA", "Beta BB", "1-0"),
            ("Alfa AA", "Gama GG", "9-9"),
            ("Beta BB", "Alfa AA", ""),
            ("Beta BB", "Gama GG", ""),
            ("Gama GG", "Alfa AA", ""),
            ("Gama GG", "Beta BB", ""),
        )
    )
    _, conference = wikipedia_with_schedule(matrix, parse_openfootball(schedule_text, 2040), registry, "wiki@synthetic")
    assert (conference.compared, conference.score_mismatches) == (2, 1)


def test_rules_2026_promote_four_clubs() -> None:
    assert load_serie_b_rules(2026).promotion_count == 4


def _goalless_model() -> GoalsModel:
    return GoalsModel(feature_set="base_rate", max_goals=4)


def test_playoff_tie_goes_to_better_placed_club() -> None:
    final_order = np.tile(np.arange(6), (50, 1))
    rates = PairRates(home=np.full((6, 6), 1e-9), away=np.full((6, 6), 1e-9))
    result = simulate_playoffs(final_order, ((3, 6), (4, 5)), rates, _goalless_model(), np.random.default_rng(1))
    assert (result.winners == np.array([2, 3])).all()


def test_playoff_stronger_lower_seed_can_advance() -> None:
    final_order = np.tile(np.arange(6), (200, 1))
    home = np.full((6, 6), 0.2)
    away = np.full((6, 6), 0.2)
    home[5, 2], away[2, 5] = 3.0, 3.0
    result = simulate_playoffs(
        final_order, ((3, 6),), PairRates(home=home, away=away), _goalless_model(), np.random.default_rng(2)
    )
    assert (result.winners[:, 0] == 5).mean() > 0.9


def test_clinched_flags_detect_certain_relegation() -> None:
    rules = load_serie_b_rules(2026)
    points = np.array([80] * 16 + [10, 10, 10, 10], dtype=np.int64)
    flags = clinched_flags(points, np.full(20, 3, dtype=np.int64), rules)
    assert flags[19].relegated and not flags[0].relegated


def test_clinched_flags_do_not_promote_when_rivals_can_catch_up() -> None:
    rules = load_serie_b_rules(2026)
    points = np.array([70, 68, 67] + [40] * 17, dtype=np.int64)
    flags = clinched_flags(points, np.full(20, 1, dtype=np.int64), rules)
    assert not flags[0].promoted_direct and flags[0].top6


@pytest.fixture(scope="module")
def synthetic_forecast_inputs(synthetic_matches: pd.DataFrame, synthetic_registry: ClubRegistry) -> tuple:
    rules = replace(load_serie_b_rules(2026), season=2032)
    finished = synthetic_matches[(synthetic_matches["season"] == 2032) & (synthetic_matches["status"] == "finished")]
    reference_date = finished["match_date"].max().date()
    sources = {
        "reference_date": reference_date.isoformat(),
        "sources": [
            {
                "tag": "synthetic@1",
                "source_name": "synthetic",
                "version": "1",
                "origin": "tests/fixtures",
                "retrieved_at": (reference_date + timedelta(days=1)).isoformat(),
                "license_status": "verified_open",
                "license_name": "synthetic",
                "allowed_uses": ["public_display_derived"],
                "attribution": "dados sintéticos",
            }
        ],
    }
    config = ModelConfig("elo_attack_defense", RatingParams(), False)
    forecast = build_forecast(synthetic_matches, sources, rules, synthetic_registry, config, 400, 11)
    return forecast, sources


def test_forecast_passes_gate(synthetic_forecast_inputs: tuple) -> None:
    forecast, sources = synthetic_forecast_inputs
    assert check_forecast(forecast, sources, TODAY) == []


def test_gate_flags_promotion_sum(synthetic_forecast_inputs: tuple) -> None:
    forecast, sources = synthetic_forecast_inputs
    broken = forecast.model_copy(
        update={"teams": [forecast.teams[0].model_copy(update={"title": 0.5}), *forecast.teams[1:]]}
    )
    assert any("title" in finding for finding in check_forecast(broken, sources, TODAY))


def test_gate_flags_unattributed_source(synthetic_forecast_inputs: tuple) -> None:
    forecast, sources = synthetic_forecast_inputs
    unattributed = {**sources, "sources": [{**sources["sources"][0], "attribution": ""}]}
    assert any("atribuição" in finding for finding in check_forecast(forecast, unattributed, TODAY))


def test_forecast_promotion_is_direct_plus_playoff(synthetic_forecast_inputs: tuple) -> None:
    forecast, _ = synthetic_forecast_inputs
    assert sum(team.promotion for team in forecast.teams) == pytest.approx(4.0)


STANDINGS_SYNTHETIC = """{{#invoke:Sports table|main|style=WDL
|update=27 de outubro
|name_ALF={{Futebol Alfa|estado=antes}}
|name_BET={{Futebol Beta|estado=antes}}
|name_GAM={{Futebol Gama|estado=antes}}
|win_ALF=1 |draw_ALF=2 |loss_ALF=0|gf_ALF=4 |ga_ALF=3
|win_BET=0 |draw_BET=0 |loss_BET=2|gf_BET=0 |ga_BET=4
|win_GAM=1 |draw_GAM=2 |loss_GAM=0|gf_GAM=6 |ga_GAM=3
}}
"""


def _synthetic_current_records() -> list[dict[str, object]]:
    matrix = parse_wikipedia_matrix(WIKI_SYNTHETIC, 2040)
    registry = ClubRegistry(clubs={}, alias_index={"Alfa": "alfa", "Beta": "beta", "Gama": "gama"})
    records: list[dict[str, object]] = []
    for result in matrix.results:
        finished = result.home_goals is not None
        records.append(
            {
                "home_id": registry.resolve(result.home_name),
                "away_id": registry.resolve(result.away_name),
                "home_goals": result.home_goals,
                "away_goals": result.away_goals,
                "status": "finished" if finished else "scheduled",
            }
        )
    return records


def _standings_check(standings_text: str) -> None:
    registry = ClubRegistry(clubs={}, alias_index={"Alfa": "alfa", "Beta": "beta", "Gama": "gama"})
    check_against_standings(
        _synthetic_current_records(),
        parse_wikipedia_standings(standings_text, 2040),
        parse_wikipedia_matrix(WIKI_SYNTHETIC, 2040),
        registry,
    )


def test_matrix_matching_standings_passes() -> None:
    _standings_check(STANDINGS_SYNTHETIC)


def test_vandalized_score_fails_standings_check() -> None:
    with pytest.raises(CompositionError):
        _standings_check(STANDINGS_SYNTHETIC.replace("|gf_GAM=6", "|gf_GAM=7"))


def test_point_deduction_fails_standings_check() -> None:
    with pytest.raises(CompositionError):
        _standings_check(STANDINGS_SYNTHETIC.replace("|win_ALF=1", "|adjust_points_ALF=+3 |win_ALF=1"))


def test_out_of_sync_update_fails_standings_check() -> None:
    with pytest.raises(CompositionError):
        _standings_check(STANDINGS_SYNTHETIC.replace("27 de outubro", "28 de outubro"))


def test_playoff_each_club_hosts_one_leg() -> None:
    final_order = np.tile(np.arange(6), (200, 1))
    home = np.full((6, 6), 1e-9)
    home[5, 2] = 3.0
    rates = PairRates(home=home, away=np.full((6, 6), 1e-9))
    result = simulate_playoffs(final_order, ((3, 6),), rates, _goalless_model(), np.random.default_rng(3))
    assert (result.winners[:, 0] == 5).mean() > 0.9


def test_clinched_flags_detect_direct_promotion() -> None:
    points = np.array([90, 89] + [40] * 18, dtype=np.int64)
    flags = clinched_flags(points, np.full(20, 3, dtype=np.int64), load_serie_b_rules(2026))
    assert flags[0].promoted_direct and flags[1].promoted_direct


def test_clinched_flags_detect_safety_and_exclusion() -> None:
    points = np.array([90] * 6 + [50] * 10 + [10] * 4, dtype=np.int64)
    flags = clinched_flags(points, np.full(20, 3, dtype=np.int64), load_serie_b_rules(2026))
    assert flags[6].safe and flags[6].out_of_top6 and not flags[6].relegated


def test_gate_rejects_future_reference_date(synthetic_forecast_inputs: tuple) -> None:
    forecast, sources = synthetic_forecast_inputs
    assert any("no futuro" in finding for finding in check_forecast(forecast, sources, date(2000, 1, 1)))


def test_gate_rejects_reference_after_collection(synthetic_forecast_inputs: tuple) -> None:
    forecast, sources = synthetic_forecast_inputs
    late = {
        **sources,
        "sources": [{**sources["sources"][0], "version": "2032-r1", "retrieved_at": "2032-01-01T12:00:00+00:00"}],
    }
    assert any("posterior à coleta" in finding for finding in check_forecast(forecast, late, TODAY))


def test_gate_rejects_forged_promotion_flag(synthetic_forecast_inputs: tuple) -> None:
    forecast, sources = synthetic_forecast_inputs
    team = min(forecast.teams, key=lambda item: item.promotion_direct)
    forged = team.model_copy(update={"clinched": team.clinched.model_copy(update={"promoted_direct": True})})
    broken = forecast.model_copy(update={"teams": [forged if item is team else item for item in forecast.teams]})
    assert any("subiu pela aritmética" in finding for finding in check_forecast(broken, sources, TODAY))


def test_standalone_gate_rejects_json_outside_schema(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "forecast.json").write_text('{"schema_version": "0.9"}', encoding="utf-8")
    assert any("fora do esquema" in finding for finding in check_artifact(tmp_path, None, TODAY))


def test_serie_b_model_config_is_read_from_its_own_file(tmp_path: Path) -> None:
    params = RatingParams()
    payload = {
        "feature_set": "elo_attack_defense",
        "rating_params": rating_params_to_dict(params),
        "dynamic_ratings_in_simulation": False,
        "goal_dispersion": True,
        "simulation_uncertainty": {"coefficient_draws": False, "strength_sd": 0.0},
    }
    (tmp_path / "serie_b_model_config.json").write_text(json.dumps(payload), encoding="utf-8")
    assert load_model_config(tmp_path, "serie_b_model_config.json").goal_dispersion is True


def test_gate_rejects_backtest_from_another_model(synthetic_forecast_inputs: tuple) -> None:
    forecast, sources = synthetic_forecast_inputs
    mismatched = forecast.model_copy(update={"backtest": {"model_version": "serie-b-0.0.1"}})
    assert any("backtest de" in finding for finding in check_forecast(mismatched, sources, TODAY))
