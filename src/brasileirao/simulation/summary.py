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
IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]


@dataclass
class ContinentalProbabilities:
    """Probabilidades por cenário: arrays (n_cenários, n_clubes)."""

    scenario_ids: list[str]
    libertadores_groups: FloatArray
    libertadores_prelim: FloatArray
    sudamericana: FloatArray
    sudamericana_all_scenarios: FloatArray
    sudamericana_any_scenario: FloatArray

    @property
    def libertadores_total(self) -> FloatArray:
        total: FloatArray = self.libertadores_groups + self.libertadores_prelim
        return total


@dataclass(frozen=True)
class SudamericanaRace:
    """Corrida pela Sul-Americana sem pesos para os cenários externos.

    `all_scenarios` e `any_scenario` são probabilidades de fato (por simulação, a vaga vale em todos
    ou em pelo menos um cenário). `midpoint` é o centro da faixa por cenário, usado só para ordenar.
    `rank_best`/`rank_worst` são a melhor e a pior posição do clube na ordenação de cada cenário.
    """

    all_scenarios: float
    any_scenario: float
    midpoint: float
    rank: int
    rank_best: int
    rank_worst: int


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
    sudamericana_race: SudamericanaRace | None = None


def position_distribution(result: SimulationResult) -> FloatArray:
    """Matriz (n_clubes, n_posições) com P(clube termina na posição)."""
    n_clubs = len(result.club_ids)
    counts = np.zeros((n_clubs, n_clubs), dtype=np.float64)
    for club in range(n_clubs):
        counts[club] = np.bincount(result.positions[:, club], minlength=n_clubs)
    distribution: FloatArray = counts / result.n_simulations
    return distribution


def _external_clubs(scenarios: list[ExternalScenario], club_ids: tuple[str, ...]) -> list[str]:
    """Clubes da liga citados em algum cenário externo (campeões e vice possíveis)."""
    in_league = set(club_ids)
    referenced = {
        club_id
        for scenario in scenarios
        for club_id in (
            scenario.outcome.libertadores_champion,
            scenario.outcome.sudamericana_champion,
            scenario.outcome.cup_champion,
            scenario.outcome.cup_runner_up,
        )
        if club_id is not None and club_id in in_league
    }
    return sorted(referenced)


def _slots_by_position(
    special_positions: IntArray,
    special_clubs: list[str],
    club_ids: tuple[str, ...],
    rules: SeasonRules,
    scenarios: list[ExternalScenario],
) -> tuple[BoolArray, BoolArray, BoolArray]:
    """Vagas por posição final para cada arranjo de posições dos clubes citados nos cenários.

    `allocate_slots` só distingue os clubes citados nos cenários; os demais entram apenas pela
    posição. Assim, basta uma classificação canônica por arranjo (posições dos citados), com os
    demais clubes em ordem fixa nas posições livres. Shape de cada saída: (n_arranjos, n_cenários, n_posições).
    """
    n_clubs = len(club_ids)
    shape = (len(special_positions), len(scenarios), n_clubs)
    groups, prelim, sudamericana = np.zeros(shape, bool), np.zeros(shape, bool), np.zeros(shape, bool)
    special = set(special_clubs)
    others = [club_id for club_id in club_ids if club_id not in special]
    for arrangement, positions in enumerate(special_positions):
        order: list[str] = [""] * n_clubs
        for club_id, position in zip(special_clubs, positions, strict=True):
            order[int(position)] = club_id
        filler = iter(others)
        order = [club_id or next(filler) for club_id in order]
        position_of = {club_id: position for position, club_id in enumerate(order)}
        for scenario_position, scenario in enumerate(scenarios):
            allocation = allocate_slots(order, rules, scenario.outcome)
            for club_id, phase in allocation.libertadores.items():
                target = groups if phase == Phase.GROUPS else prelim
                target[arrangement, scenario_position, position_of[club_id]] = True
            for club_id in allocation.sudamericana:
                sudamericana[arrangement, scenario_position, position_of[club_id]] = True
    return groups, prelim, sudamericana


def continental_probabilities(
    result: SimulationResult, rules: SeasonRules, scenarios: list[ExternalScenario]
) -> ContinentalProbabilities:
    """P(vaga | cenário) por clube e as probabilidades de Sul-Americana que não dependem de cenário."""
    n_clubs = len(result.club_ids)
    special_clubs = _external_clubs(scenarios, result.club_ids)
    special_index = [result.club_ids.index(club_id) for club_id in special_clubs]
    if special_index:
        special_positions, arrangement_of = np.unique(result.positions[:, special_index], axis=0, return_inverse=True)
        arrangement_of = arrangement_of.reshape(-1)
    else:
        special_positions = np.zeros((1, 0), dtype=np.int64)
        arrangement_of = np.zeros(result.n_simulations, dtype=np.int64)
    groups, prelim, sudamericana = _slots_by_position(
        special_positions, special_clubs, result.club_ids, rules, scenarios
    )
    shape = (len(scenarios), n_clubs)
    groups_probability, prelim_probability = np.zeros(shape), np.zeros(shape)
    sudamericana_probability = np.zeros(shape)
    guaranteed, possible = np.zeros(n_clubs), np.zeros(n_clubs)
    for club in range(n_clubs):
        club_positions = result.positions[:, club]
        club_sudamericana = sudamericana[arrangement_of, :, club_positions]
        groups_probability[:, club] = groups[arrangement_of, :, club_positions].mean(axis=0)
        prelim_probability[:, club] = prelim[arrangement_of, :, club_positions].mean(axis=0)
        sudamericana_probability[:, club] = club_sudamericana.mean(axis=0)
        guaranteed[club] = club_sudamericana.all(axis=1).mean()
        possible[club] = club_sudamericana.any(axis=1).mean()
    return ContinentalProbabilities(
        scenario_ids=[scenario.scenario_id for scenario in scenarios],
        libertadores_groups=groups_probability,
        libertadores_prelim=prelim_probability,
        sudamericana=sudamericana_probability,
        sudamericana_all_scenarios=guaranteed,
        sudamericana_any_scenario=possible,
    )


def _range_and_scenarios(values: FloatArray, scenario_ids: list[str]) -> dict[str, float]:
    summary = {"min": float(values.min()), "max": float(values.max())}
    summary.update({scenario_id: float(value) for scenario_id, value in zip(scenario_ids, values, strict=True)})
    return summary


def _competition_ranks(values: FloatArray) -> IntArray:
    """Posição 1 = maior valor; empates dividem a melhor posição (1 + nº de valores estritamente maiores)."""
    ranks: IntArray = 1 + (values[None, :] > values[:, None]).sum(axis=1)
    return ranks


def sudamericana_race(
    continental: ContinentalProbabilities, club_ids: tuple[str, ...], expected_position: FloatArray
) -> list[SudamericanaRace]:
    """Classificação da corrida pela Sul-Americana, estável e sem atribuir probabilidade aos cenários.

    Ordem: centro da faixa (mín.+máx.)/2, depois máximo, depois chance em todos os cenários,
    depois posição esperada e `club_id`. O centro da faixa não depende de quantas vezes cada
    combinação de campeões aparece na enumeração (ao contrário de uma média entre cenários).
    """
    by_scenario = continental.sudamericana
    low, high = by_scenario.min(axis=0), by_scenario.max(axis=0)
    midpoint = (low + high) / 2
    order = sorted(
        range(len(club_ids)),
        key=lambda club: (
            -round(float(midpoint[club]), 12),
            -round(float(high[club]), 12),
            -round(float(continental.sudamericana_all_scenarios[club]), 12),
            float(expected_position[club]),
            club_ids[club],
        ),
    )
    rank = {club: position for position, club in enumerate(order, start=1)}
    scenario_ranks = np.stack([_competition_ranks(np.round(values, 12)) for values in by_scenario])
    return [
        SudamericanaRace(
            all_scenarios=float(continental.sudamericana_all_scenarios[club]),
            any_scenario=float(continental.sudamericana_any_scenario[club]),
            midpoint=float(midpoint[club]),
            rank=rank[club],
            rank_best=int(scenario_ranks[:, club].min()),
            rank_worst=int(scenario_ranks[:, club].max()),
        )
        for club in range(len(club_ids))
    ]


def build_team_summaries(
    result: SimulationResult, rules: SeasonRules, scenarios: list[ExternalScenario]
) -> tuple[list[TeamSummary], ContinentalProbabilities]:
    distribution = position_distribution(result)
    continental = continental_probabilities(result, rules, scenarios)
    n_clubs = len(result.club_ids)
    relegation_start = n_clubs - rules.relegation_count
    race = sudamericana_race(continental, result.club_ids, result.positions.mean(axis=0) + 1)
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
                sudamericana_race=race[club],
            )
        )
    return summaries, continental
