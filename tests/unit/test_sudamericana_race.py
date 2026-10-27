"""Corrida pela Sul-Americana e agregação por arranjo de posições. Dados SINTÉTICOS (synthetic)."""

from __future__ import annotations

import itertools
from datetime import date

import numpy as np
import pandas as pd
import pytest

from brasileirao.competition_rules.qualification import allocate_slots
from brasileirao.competition_rules.scenarios import ExternalScenario, enumerate_external_scenarios
from brasileirao.competition_rules.season_rules import Phase, SeasonRules
from brasileirao.config import RatingParams
from brasileirao.prediction.goals_model import GoalsModel
from brasileirao.ratings.history import build_state_as_of
from brasileirao.simulation import engine as engine_module
from brasileirao.simulation.engine import SeasonSimulator, SimulationResult
from brasileirao.simulation.summary import (
    ContinentalProbabilities,
    TeamSummary,
    build_team_summaries,
    continental_probabilities,
)

REFERENCE_DATE = date(2032, 10, 25)
N_SIMULATIONS = 600


@pytest.fixture(scope="module")
def simulator(synthetic_matches: pd.DataFrame, synthetic_rules: SeasonRules) -> SeasonSimulator:
    params = RatingParams()
    engine, features = build_state_as_of(synthetic_matches, REFERENCE_DATE, 2032, params)
    model = GoalsModel.fit(features[features["season"] < 2032], "elo_attack_defense")
    season_matches = synthetic_matches[synthetic_matches["season"] == 2032]
    return SeasonSimulator(season_matches, REFERENCE_DATE, engine.state, model, params, synthetic_rules)


@pytest.fixture(scope="module")
def result(simulator: SeasonSimulator) -> SimulationResult:
    return simulator.run(N_SIMULATIONS, seed=17)


@pytest.fixture(scope="module")
def scenarios(synthetic_rules: SeasonRules) -> list[ExternalScenario]:
    return enumerate_external_scenarios(synthetic_rules)


@pytest.fixture(scope="module")
def continental(
    result: SimulationResult, synthetic_rules: SeasonRules, scenarios: list[ExternalScenario]
) -> ContinentalProbabilities:
    return continental_probabilities(result, synthetic_rules, scenarios)


@pytest.fixture(scope="module")
def summaries(
    result: SimulationResult, synthetic_rules: SeasonRules, scenarios: list[ExternalScenario]
) -> list[TeamSummary]:
    built, _ = build_team_summaries(result, synthetic_rules, scenarios)
    return built


def _allocation_per_order(
    result: SimulationResult, rules: SeasonRules, scenarios: list[ExternalScenario]
) -> tuple[np.ndarray, np.ndarray]:
    """Referência direta: `allocate_slots` em cada classificação simulada."""
    shape = (len(scenarios), len(result.club_ids))
    groups, sudamericana = np.zeros(shape), np.zeros(shape)
    for order in result.final_order:
        ordered_clubs = [result.club_ids[club] for club in order]
        for scenario_position, scenario in enumerate(scenarios):
            allocation = allocate_slots(ordered_clubs, rules, scenario.outcome)
            for club_id, phase in allocation.libertadores.items():
                if phase == Phase.GROUPS:
                    groups[scenario_position, result.club_ids.index(club_id)] += 1
            for club_id in allocation.sudamericana:
                sudamericana[scenario_position, result.club_ids.index(club_id)] += 1
    return groups / result.n_simulations, sudamericana / result.n_simulations


def test_positional_aggregation_matches_direct_sudamericana(
    result: SimulationResult,
    synthetic_rules: SeasonRules,
    scenarios: list[ExternalScenario],
    continental: ContinentalProbabilities,
) -> None:
    _, direct = _allocation_per_order(result, synthetic_rules, scenarios)
    assert np.array_equal(continental.sudamericana, direct)


def test_positional_aggregation_matches_direct_libertadores_groups(
    result: SimulationResult,
    synthetic_rules: SeasonRules,
    scenarios: list[ExternalScenario],
    continental: ContinentalProbabilities,
) -> None:
    direct, _ = _allocation_per_order(result, synthetic_rules, scenarios)
    assert np.array_equal(continental.libertadores_groups, direct)


def test_all_scenarios_probability_is_below_range(continental: ContinentalProbabilities) -> None:
    assert np.all(continental.sudamericana_all_scenarios <= continental.sudamericana.min(axis=0) + 1e-12)


def test_any_scenario_probability_is_above_range(continental: ContinentalProbabilities) -> None:
    assert np.all(continental.sudamericana_any_scenario >= continental.sudamericana.max(axis=0) - 1e-12)


def test_race_ranks_are_a_permutation(summaries: list[TeamSummary]) -> None:
    ranks = sorted(summary.sudamericana_race.rank for summary in summaries if summary.sudamericana_race)
    assert ranks == list(range(1, 21))


def test_race_rank_follows_range_midpoint(summaries: list[TeamSummary]) -> None:
    races = sorted(
        (summary.sudamericana_race for summary in summaries if summary.sudamericana_race), key=lambda race: race.rank
    )
    assert all(first.midpoint >= second.midpoint for first, second in itertools.pairwise(races))


def test_race_midpoint_is_center_of_range(summaries: list[TeamSummary]) -> None:
    summary = summaries[0]
    assert summary.sudamericana_race is not None
    assert summary.sudamericana_race.midpoint == pytest.approx(
        (summary.sudamericana["min"] + summary.sudamericana["max"]) / 2
    )


def test_race_scenario_ranks_are_ordered(summaries: list[TeamSummary]) -> None:
    races = [summary.sudamericana_race for summary in summaries if summary.sudamericana_race]
    assert all(race.rank_best <= race.rank_worst for race in races)


def test_chunked_score_sampling_reproduces_seed(
    simulator: SeasonSimulator, result: SimulationResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(engine_module, "SAMPLING_CHUNK_ROWS", 7)
    chunked = simulator.run(N_SIMULATIONS, seed=17)
    assert np.array_equal(chunked.simulated_home_goals, result.simulated_home_goals)
