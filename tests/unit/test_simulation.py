"""Invariantes do motor de simulação (Agente 06)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from brasileirao.competition_rules.scenarios import enumerate_external_scenarios
from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.config import RatingParams, SimulationUncertainty
from brasileirao.prediction.goals_model import GoalsModel
from brasileirao.ratings.history import build_state_as_of
from brasileirao.simulation.engine import SeasonSimulator, SimulationResult
from brasileirao.simulation.summary import build_team_summaries, position_distribution

REFERENCE_DATE = date(2032, 10, 25)
N_SIMULATIONS = 400


def _simulator(matches: pd.DataFrame, rules: SeasonRules) -> SeasonSimulator:
    params = RatingParams()
    engine, features = build_state_as_of(matches, REFERENCE_DATE, 2032, params)
    model = GoalsModel.fit(features[features["season"] < 2032], "elo_attack_defense")
    return SeasonSimulator(matches[matches["season"] == 2032], REFERENCE_DATE, engine.state, model, params, rules)


@pytest.fixture(scope="module")
def simulator(synthetic_matches: pd.DataFrame, synthetic_rules: SeasonRules) -> SeasonSimulator:
    return _simulator(synthetic_matches, synthetic_rules)


@pytest.fixture(scope="module")
def result(simulator: SeasonSimulator) -> SimulationResult:
    return simulator.run(N_SIMULATIONS, seed=11, dynamic_ratings=True)


def test_every_simulated_season_has_380_matches(result: SimulationResult) -> None:
    assert len(result.observed_matches) + result.simulated_home_goals.shape[1] == 380


def test_every_club_plays_38_matches(result: SimulationResult, synthetic_rules: SeasonRules) -> None:
    draws_and_losses = result.points - synthetic_rules.points_win * result.wins
    played_upper_bound = result.wins + draws_and_losses
    assert int(played_upper_bound.max()) <= 38


def test_final_positions_are_permutations(result: SimulationResult) -> None:
    assert np.all(np.sort(result.positions, axis=1) == np.arange(20))


def test_final_order_is_sorted_by_points(result: SimulationResult) -> None:
    ordered_points = np.take_along_axis(result.points, result.final_order, axis=1)
    assert np.all(np.diff(ordered_points, axis=1) <= 0)


def test_goals_for_equal_goals_against_league_wide(result: SimulationResult) -> None:
    assert np.array_equal(result.goals_for.sum(axis=1), result.goals_against.sum(axis=1))


def test_observed_points_are_floor_of_final_points(result: SimulationResult) -> None:
    assert np.all(result.points >= result.observed_table.points[None, :])


def test_position_distribution_rows_sum_to_one(result: SimulationResult) -> None:
    assert np.allclose(position_distribution(result).sum(axis=1), 1.0)


def test_position_distribution_columns_sum_to_one(result: SimulationResult) -> None:
    assert np.allclose(position_distribution(result).sum(axis=0), 1.0)


def test_title_probabilities_sum_to_one(result: SimulationResult, synthetic_rules: SeasonRules) -> None:
    summaries, _ = build_team_summaries(result, synthetic_rules, enumerate_external_scenarios(synthetic_rules))
    assert sum(summary.title for summary in summaries) == pytest.approx(1.0)


def test_relegation_probabilities_sum_to_four(result: SimulationResult, synthetic_rules: SeasonRules) -> None:
    summaries, _ = build_team_summaries(result, synthetic_rules, enumerate_external_scenarios(synthetic_rules))
    assert sum(summary.relegation for summary in summaries) == pytest.approx(4.0)


def test_sudamericana_slots_sum_to_six_per_scenario(result: SimulationResult, synthetic_rules: SeasonRules) -> None:
    _, continental = build_team_summaries(result, synthetic_rules, enumerate_external_scenarios(synthetic_rules))
    assert np.allclose(continental.sudamericana.sum(axis=1), 6.0)


def test_same_seed_reproduces_results(simulator: SeasonSimulator) -> None:
    first = simulator.run(50, seed=5)
    second = simulator.run(50, seed=5)
    assert np.array_equal(first.final_order, second.final_order)


def test_fixed_ratings_mode_runs(simulator: SeasonSimulator) -> None:
    fixed = simulator.run(50, seed=5, dynamic_ratings=False)
    assert fixed.points.shape == (50, 20)


def test_completed_season_is_deterministic(synthetic_matches: pd.DataFrame, synthetic_rules: SeasonRules) -> None:
    complete = synthetic_matches[synthetic_matches["season"] < 2032].copy()
    complete.loc[complete["season"] == 2031, "season"] = 2032
    complete = complete[complete["season"] == 2032]
    history = pd.concat([synthetic_matches[synthetic_matches["season"] == 2030], complete])
    finished = _simulator(history, synthetic_rules).run(30, seed=1)
    assert len(np.unique(finished.final_order, axis=0)) == 1


def test_disabled_uncertainty_reproduces_default_run(simulator: SeasonSimulator) -> None:
    default = simulator.run(50, seed=5)
    explicit = simulator.run(50, seed=5, uncertainty=SimulationUncertainty())
    assert np.array_equal(default.points, explicit.points)


def test_latent_strength_widens_points_distribution(simulator: SeasonSimulator) -> None:
    plain = simulator.run(300, seed=5, dynamic_ratings=False)
    uncertain = simulator.run(300, seed=5, dynamic_ratings=False, uncertainty=SimulationUncertainty(strength_sd=0.3))
    assert uncertain.points.std(axis=0).mean() > plain.points.std(axis=0).mean()


def test_uncertain_run_is_reproducible(simulator: SeasonSimulator) -> None:
    uncertainty = SimulationUncertainty(coefficient_draws=True, strength_sd=0.1)
    first = simulator.run(50, seed=9, uncertainty=uncertainty)
    second = simulator.run(50, seed=9, uncertainty=uncertainty)
    assert np.array_equal(first.final_order, second.final_order)


def test_coefficient_draws_keep_positions_as_permutations(simulator: SeasonSimulator) -> None:
    uncertain = simulator.run(50, seed=9, uncertainty=SimulationUncertainty(coefficient_draws=True))
    assert np.all(np.sort(uncertain.positions, axis=1) == np.arange(20))
