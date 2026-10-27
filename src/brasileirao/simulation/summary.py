"""Agregação das simulações em probabilidades por clube e por cenário externo."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from brasileirao.competition_rules.qualification import allocate_slots
from brasileirao.competition_rules.scenarios import ExternalScenario
from brasileirao.competition_rules.season_rules import Phase, SeasonRules
from brasileirao.simulation.engine import SimulationResult

FloatArray = npt.NDArray[np.float64]


@dataclass
class ContinentalProbabilities:
    """Probabilidades por cenário: arrays (n_cenários, n_clubes)."""

    scenario_ids: list[str]
    libertadores_groups: FloatArray
    libertadores_prelim: FloatArray
    sudamericana: FloatArray

    @property
    def libertadores_total(self) -> FloatArray:
        total: FloatArray = self.libertadores_groups + self.libertadores_prelim
        return total


@dataclass
class TeamSummary:
    club_id: str
    expected_points: float
    points_interval_90: tuple[float, float]
    median_points: float
    expected_goals_for: float
    expected_goals_against: float
    position_probabilities: list[float]
    expected_position: float
    title: float
    runner_up: float
    top4: float
    relegation: float
    libertadores_groups: dict[str, float] = field(default_factory=dict)
    libertadores_prelim: dict[str, float] = field(default_factory=dict)
    libertadores_total: dict[str, float] = field(default_factory=dict)
    sudamericana: dict[str, float] = field(default_factory=dict)


def position_distribution(result: SimulationResult) -> FloatArray:
    """Matriz (n_clubes, n_posições) com P(clube termina na posição)."""
    n_clubs = len(result.club_ids)
    counts = np.zeros((n_clubs, n_clubs), dtype=np.float64)
    for club in range(n_clubs):
        counts[club] = np.bincount(result.positions[:, club], minlength=n_clubs)
    distribution: FloatArray = counts / result.n_simulations
    return distribution


def continental_probabilities(
    result: SimulationResult, rules: SeasonRules, scenarios: list[ExternalScenario]
) -> ContinentalProbabilities:
    n_clubs = len(result.club_ids)
    shape = (len(scenarios), n_clubs)
    groups_counts = np.zeros(shape)
    prelim_counts = np.zeros(shape)
    sudamericana_counts = np.zeros(shape)
    club_index = {club: index for index, club in enumerate(result.club_ids)}
    unique_orders, order_frequency = np.unique(result.final_order, axis=0, return_counts=True)
    for order, frequency in zip(unique_orders, order_frequency, strict=True):
        ordered_clubs = [result.club_ids[club] for club in order]
        for scenario_position, scenario in enumerate(scenarios):
            allocation = allocate_slots(ordered_clubs, rules, scenario.outcome)
            for club_id, phase in allocation.libertadores.items():
                if phase == Phase.GROUPS:
                    groups_counts[scenario_position, club_index[club_id]] += frequency
                else:
                    prelim_counts[scenario_position, club_index[club_id]] += frequency
            for club_id in allocation.sudamericana:
                sudamericana_counts[scenario_position, club_index[club_id]] += frequency
    n_simulations = result.n_simulations
    return ContinentalProbabilities(
        scenario_ids=[scenario.scenario_id for scenario in scenarios],
        libertadores_groups=groups_counts / n_simulations,
        libertadores_prelim=prelim_counts / n_simulations,
        sudamericana=sudamericana_counts / n_simulations,
    )


def _range_and_scenarios(values: FloatArray, scenario_ids: list[str]) -> dict[str, float]:
    summary = {"min": float(values.min()), "max": float(values.max())}
    summary.update({scenario_id: float(value) for scenario_id, value in zip(scenario_ids, values, strict=True)})
    return summary


def build_team_summaries(
    result: SimulationResult, rules: SeasonRules, scenarios: list[ExternalScenario]
) -> tuple[list[TeamSummary], ContinentalProbabilities]:
    distribution = position_distribution(result)
    continental = continental_probabilities(result, rules, scenarios)
    n_clubs = len(result.club_ids)
    relegation_start = n_clubs - rules.relegation_count
    summaries: list[TeamSummary] = []
    for club, club_id in enumerate(result.club_ids):
        club_points = result.points[:, club]
        summaries.append(
            TeamSummary(
                club_id=club_id,
                expected_points=float(club_points.mean()),
                points_interval_90=(float(np.percentile(club_points, 5)), float(np.percentile(club_points, 95))),
                median_points=float(np.median(club_points)),
                expected_goals_for=float(result.goals_for[:, club].mean()),
                expected_goals_against=float(result.goals_against[:, club].mean()),
                position_probabilities=[float(value) for value in distribution[club]],
                expected_position=float(result.positions[:, club].mean() + 1),
                title=float(distribution[club, 0]),
                runner_up=float(distribution[club, 1]),
                top4=float(distribution[club, :4].sum()),
                relegation=float(distribution[club, relegation_start:].sum()),
                libertadores_groups=_range_and_scenarios(
                    continental.libertadores_groups[:, club], continental.scenario_ids
                ),
                libertadores_prelim=_range_and_scenarios(
                    continental.libertadores_prelim[:, club], continental.scenario_ids
                ),
                libertadores_total=_range_and_scenarios(
                    continental.libertadores_total[:, club], continental.scenario_ids
                ),
                sudamericana=_range_and_scenarios(continental.sudamericana[:, club], continental.scenario_ids),
            )
        )
    return summaries, continental
