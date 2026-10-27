"""Revisão rodada a rodada: visões históricas e atribuição das mudanças de probabilidade a cada jogo.

A visão da rodada r é o estado na véspera do primeiro jogo da rodada r + 1 (a rodada 0 é a
pré-temporada). A variação entre duas visões é decomposta de forma exata em:

- efeito dos resultados: os jogos do intervalo entram na tabela, com a força dos clubes da visão
  anterior (simulação intermediária);
- reavaliação de força: a diferença entre a visão nova e a intermediária, que só muda os ratings
  (mesma semente e mesmos jogos restantes, logo números aleatórios comuns).

O efeito dos resultados é atribuído a cada jogo por P(X | resultado real) − P(X), medido nas
simulações da visão anterior, nas quais o jogo ainda estava em aberto. O que sobra é a interação
entre jogos e o ruído de Monte Carlo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import numpy.typing as npt
import pandas as pd

from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.competition_rules.standings import rank_table
from brasileirao.contracts import MatchStatus
from brasileirao.frame_values import as_int, as_timestamp
from brasileirao.simulation.engine import SimulationResult

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
ClubMetrics = dict[str, dict[str, float]]

METRICS = ("title", "top4", "relegation")
OUTCOMES = ("home", "draw", "away")


@dataclass(frozen=True)
class RoundCutoff:
    round_number: int
    reference_date: date
    partial: bool


@dataclass(frozen=True)
class MatchImpact:
    match_id: str
    round: int
    match_date: str
    home_id: str
    away_id: str
    home_goals: int
    away_goals: int
    outcome: str
    pre_match: dict[str, float]
    impacts: ClubMetrics
    stakes: ClubMetrics

    @property
    def total_impact(self) -> float:
        return float(sum(abs(value) for values in self.impacts.values() for value in values.values()))

    @property
    def outcome_probability(self) -> float:
        return self.pre_match[self.outcome]


@dataclass(frozen=True)
class Mover:
    club_id: str
    delta: float


@dataclass(frozen=True)
class RoundSummary:
    risers: dict[str, list[Mover]]
    fallers: dict[str, list[Mover]]
    total_movement: dict[str, float]
    results_movement: dict[str, float]
    strength_movement: dict[str, float]
    residual_movement: dict[str, float]
    expected_noise_movement: dict[str, float]
    decisive_match_id: str | None = None
    surprise_match_id: str | None = None


@dataclass(frozen=True)
class RoundView:
    round_number: int
    reference_date: date
    partial: bool
    observed_matches: int
    teams: ClubMetrics
    matches: list[MatchImpact] = field(default_factory=list)
    changes: ClubMetrics = field(default_factory=dict)
    results_effect: ClubMetrics = field(default_factory=dict)
    strength_effect: ClubMetrics = field(default_factory=dict)
    residual: ClubMetrics = field(default_factory=dict)
    summary: RoundSummary | None = None


def round_cutoffs(season_matches: pd.DataFrame, data_until: date) -> list[RoundCutoff]:
    """Véspera do início de cada rodada seguinte, de 0 (pré-temporada) até a última rodada observada.

    Se a rodada seguinte ainda não começou na data dos dados, a última visão é `data_until`,
    marcada como parcial.
    """
    first_dates = {
        as_int(round_number): as_timestamp(first).date()
        for round_number, first in season_matches.groupby("round")["match_date"].min().items()
    }
    first_round = min(first_dates)
    previous = first_dates[first_round] - timedelta(days=1)
    cutoffs = [RoundCutoff(0, previous, False)]
    for round_number in sorted(first_dates):
        if first_dates[round_number] > data_until:
            break
        next_start = first_dates.get(round_number + 1)
        cutoff = next_start - timedelta(days=1) if next_start is not None else data_until
        partial = cutoff > data_until
        cutoff = min(cutoff, data_until)
        if cutoff <= previous:
            continue
        cutoffs.append(RoundCutoff(round_number, cutoff, partial))
        previous = cutoff
        if partial:
            break
    return cutoffs


def played_between(season_matches: pd.DataFrame, after: date, until: date) -> pd.DataFrame:
    is_finished = season_matches["status"] == MatchStatus.FINISHED.value
    match_days = season_matches["match_date"].dt.date
    in_window: pd.Series[bool] = is_finished & (match_days > after) & (match_days <= until)
    return season_matches.loc[in_window].sort_values(["match_date", "match_id"])


def metric_indicators(result: SimulationResult, rules: SeasonRules) -> dict[str, BoolArray]:
    """Indicadores (n_simulações, n_clubes) de cada métrica."""
    n_clubs = len(result.club_ids)
    return {
        "title": result.positions == 0,
        "top4": result.positions < 4,
        "relegation": result.positions >= n_clubs - rules.relegation_count,
    }


def team_metrics(result: SimulationResult, rules: SeasonRules) -> ClubMetrics:
    """Probabilidades simuladas e a tabela real na data (posição, pontos, jogos e saldo)."""
    indicators = metric_indicators(result, rules)
    expected_points = result.points.mean(axis=0)
    expected_position = result.positions.mean(axis=0) + 1
    table = result.observed_table
    position_of = {club: position for position, club in enumerate(rank_table(table, rules), start=1)}
    return {
        club: {
            **{metric: float(indicators[metric][:, index].mean()) for metric in METRICS},
            "expected_points": float(expected_points[index]),
            "expected_position": float(expected_position[index]),
            "position": float(position_of[club]),
            "points": float(table.points[index]),
            "played": float(table.played[index]),
            "goal_difference": float(table.goal_difference[index]),
        }
        for index, club in enumerate(result.club_ids)
    }


def outcome_codes(home_goals: npt.NDArray[np.integer], away_goals: npt.NDArray[np.integer]) -> npt.NDArray[np.int64]:
    """0 = mandante, 1 = empate, 2 = visitante."""
    codes: npt.NDArray[np.int64] = np.where(home_goals > away_goals, 0, np.where(home_goals == away_goals, 1, 2))
    return codes


def match_impacts(result: SimulationResult, rules: SeasonRules, played_matches: pd.DataFrame) -> list[MatchImpact]:
    """Impacto do resultado real de cada jogo, medido nas simulações em que ele estava em aberto.

    `stakes` é o que estava em jogo: a maior diferença de P(X) entre os três resultados possíveis.
    """
    indicators = metric_indicators(result, rules)
    baseline = {metric: values.mean(axis=0) for metric, values in indicators.items()}
    column_of = {str(match_id): column for column, match_id in enumerate(result.remaining_matches["match_id"])}
    impacts: list[MatchImpact] = []
    for match in played_matches.itertuples(index=False):
        column = column_of.get(str(match.match_id))
        if column is None:
            continue
        simulated = outcome_codes(result.simulated_home_goals[:, column], result.simulated_away_goals[:, column])
        home_goals, away_goals = as_int(match.home_goals), as_int(match.away_goals)
        actual = 0 if home_goals > away_goals else (1 if home_goals == away_goals else 2)
        frequencies = np.bincount(simulated, minlength=3) / result.n_simulations
        conditional = {
            metric: np.stack(
                [
                    values[simulated == outcome].mean(axis=0) if np.any(simulated == outcome) else baseline[metric]
                    for outcome in range(3)
                ]
            )
            for metric, values in indicators.items()
        }
        impacts.append(
            MatchImpact(
                match_id=str(match.match_id),
                round=as_int(match.round),
                match_date=as_timestamp(match.match_date).date().isoformat(),
                home_id=str(match.home_id),
                away_id=str(match.away_id),
                home_goals=home_goals,
                away_goals=away_goals,
                outcome=OUTCOMES[actual],
                pre_match={name: float(frequencies[code]) for code, name in enumerate(OUTCOMES)},
                impacts=_per_club(
                    result.club_ids, {metric: conditional[metric][actual] - baseline[metric] for metric in METRICS}
                ),
                stakes=_per_club(
                    result.club_ids,
                    {metric: conditional[metric].max(axis=0) - conditional[metric].min(axis=0) for metric in METRICS},
                ),
            )
        )
    return impacts


def _per_club(club_ids: tuple[str, ...], values: dict[str, FloatArray]) -> ClubMetrics:
    return {
        club: {metric: round(float(values[metric][index]), 5) for metric in values}
        for index, club in enumerate(club_ids)
    }


def metric_difference(after: ClubMetrics, before: ClubMetrics) -> ClubMetrics:
    return {
        club: {metric: round(after[club][metric] - before[club][metric], 5) for metric in METRICS} for club in after
    }


def unexplained_by_matches(results_effect: ClubMetrics, impacts: list[MatchImpact]) -> ClubMetrics:
    """Parte do efeito dos resultados que a soma dos impactos individuais não explica."""
    return {
        club: {
            metric: round(values[metric] - sum(impact.impacts[club][metric] for impact in impacts), 5)
            for metric in METRICS
        }
        for club, values in results_effect.items()
    }


def expected_noise(
    before: ClubMetrics, after: ClubMetrics, impacts: list[MatchImpact], n_simulations: int
) -> dict[str, float]:
    """Soma esperada de |resíduo| só por ruído de Monte Carlo.

    Soma as variâncias das duas visões independentes e de cada impacto condicional, estimado só com
    as simulações em que o resultado real aconteceu.
    """
    scale = np.sqrt(2.0 / np.pi)
    noise: dict[str, float] = {}
    for metric in METRICS:
        total = 0.0
        for club in after:
            before_variance = before[club][metric] * (1 - before[club][metric])
            variance = (before_variance + after[club][metric] * (1 - after[club][metric])) / n_simulations
            for impact in impacts:
                outcome_count = max(impact.outcome_probability * n_simulations, 1.0)
                variance += before_variance * max(1 / outcome_count - 1 / n_simulations, 0.0)
            total += scale * float(np.sqrt(variance))
        noise[metric] = round(total, 5)
    return noise


def _movement(values: ClubMetrics) -> dict[str, float]:
    return {metric: round(sum(abs(club_values[metric]) for club_values in values.values()), 5) for metric in METRICS}


def summarize_round(
    changes: ClubMetrics,
    impacts: list[MatchImpact],
    results_effect: ClubMetrics,
    strength_effect: ClubMetrics,
    residual: ClubMetrics,
    noise: dict[str, float],
    top_n: int = 3,
) -> RoundSummary:
    """Maiores altas e quedas por métrica, jogo de maior impacto, maior surpresa e peso do resíduo."""
    ordered = {
        metric: sorted((Mover(club, values[metric]) for club, values in changes.items()), key=lambda mover: mover.delta)
        for metric in METRICS
    }
    return RoundSummary(
        risers={metric: [mover for mover in ordered[metric][::-1][:top_n] if mover.delta > 0] for metric in METRICS},
        fallers={metric: [mover for mover in ordered[metric][:top_n] if mover.delta < 0] for metric in METRICS},
        total_movement=_movement(changes),
        results_movement=_movement(results_effect),
        strength_movement=_movement(strength_effect),
        residual_movement=_movement(residual),
        expected_noise_movement=noise,
        decisive_match_id=max(impacts, key=lambda impact: impact.total_impact).match_id if impacts else None,
        surprise_match_id=min(impacts, key=lambda impact: impact.outcome_probability).match_id if impacts else None,
    )


def build_round_view(
    cutoff: RoundCutoff,
    result: SimulationResult,
    rules: SeasonRules,
    previous: tuple[RoundView, SimulationResult] | None,
    season_matches: pd.DataFrame,
    results_only: SimulationResult | None = None,
) -> RoundView:
    """Visão de uma rodada. Com a visão anterior e a simulação intermediária (resultados novos com a
    força anterior), decompõe a variação em efeito dos resultados, por jogo, e reavaliação de força."""
    teams = team_metrics(result, rules)
    if previous is None or results_only is None:
        observed = len(result.observed_matches)
        return RoundView(cutoff.round_number, cutoff.reference_date, cutoff.partial, observed, teams)
    previous_view, previous_result = previous
    played = played_between(season_matches, previous_view.reference_date, cutoff.reference_date)
    impacts = match_impacts(previous_result, rules, played)
    intermediate = team_metrics(results_only, rules)
    changes = metric_difference(teams, previous_view.teams)
    results_effect = metric_difference(intermediate, previous_view.teams)
    strength_effect = metric_difference(teams, intermediate)
    residual = unexplained_by_matches(results_effect, impacts)
    noise = expected_noise(previous_view.teams, intermediate, impacts, result.n_simulations)
    return RoundView(
        round_number=cutoff.round_number,
        reference_date=cutoff.reference_date,
        partial=cutoff.partial,
        observed_matches=len(result.observed_matches),
        teams=teams,
        matches=impacts,
        changes=changes,
        results_effect=results_effect,
        strength_effect=strength_effect,
        residual=residual,
        summary=summarize_round(changes, impacts, results_effect, strength_effect, residual, noise),
    )
