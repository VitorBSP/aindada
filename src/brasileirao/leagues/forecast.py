"""Previsão de liga: Monte Carlo do motor da Série A com o desempate de cada regulamento (ADR-0011)."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from brasileirao.config import MODEL_VERSION, ModelTrainingConfig
from brasileirao.contracts import MatchStatus
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.frame_values import as_timestamp, optional_int
from brasileirao.leagues.rules import LeagueRules, Zone
from brasileirao.leagues.schema import ClinchState, LeagueForecast, MatchForecast, SourceCredit, TeamForecast, ZoneInfo
from brasileirao.leagues.simulator import LeagueSimulator
from brasileirao.pipeline import ModelConfig
from brasileirao.prediction.goals_model import GoalsModel
from brasileirao.ratings.history import RatingEngine, build_state_as_of
from brasileirao.simulation.summary import position_distribution
from brasileirao.validation.backtest import training_window

IntArray = npt.NDArray[np.int64]

LEAGUE_MODEL_VERSION = f"ligas-0.1.0+{MODEL_VERSION}"
LEAGUE_MODEL_CONFIG = "league_model_config_{code}.json"


def training_config(first_history_season: int) -> ModelTrainingConfig:
    """A primeira temporada do histórico só aquece os ratings; o modelo de gols treina a partir da seguinte."""
    return ModelTrainingConfig(first_training_season=first_history_season + 1)


def zone_clinch(points: IntArray, remaining: IntArray, points_win: int, zone: Zone) -> list[ClinchState | None]:
    """Condições suficientes pela aritmética dos pontos (os confrontos diretos entre rivais são ignorados)."""
    max_points = points + points_win * remaining
    states: list[ClinchState | None] = []
    for club in range(len(points)):
        others = np.arange(len(points)) != club
        surely_above = int((points[others] > max_points[club]).sum())
        can_reach = int((max_points[others] >= points[club]).sum())
        if surely_above >= zone.first - 1 and can_reach <= zone.last - 1:
            states.append("in")
        elif surely_above >= zone.last or can_reach <= zone.first - 2:
            states.append("out")
        else:
            states.append(None)
    return states


def data_version(sources: dict[str, Any]) -> str:
    tags = sorted(str(item["tag"]) for item in sources["sources"])
    return hashlib.sha256("|".join(tags).encode("utf-8")).hexdigest()[:12]


def prepare(
    matches_data: pd.DataFrame,
    rules: LeagueRules,
    reference_date: date,
    model_config: ModelConfig,
    first_history_season: int,
) -> tuple[RatingEngine, GoalsModel, LeagueSimulator]:
    training = training_config(first_history_season)
    engine, features = build_state_as_of(matches_data, reference_date, rules.season, model_config.rating_params)
    model = GoalsModel.fit(
        training_window(features, rules.season, training.training_seasons_window, training.first_training_season),
        model_config.feature_set,
        alpha=training.poisson_alpha,
        max_goals=training.max_goals,
        draw_inflation=model_config.draw_inflation,
        goal_dispersion=model_config.goal_dispersion,
    )
    simulator = LeagueSimulator(
        matches_data[matches_data["season"] == rules.season],
        reference_date,
        engine.state,
        model,
        model_config.rating_params,
        rules.league_rules(),
        rules.tiebreak_order,
    )
    return engine, model, simulator


def build_forecast(
    matches_data: pd.DataFrame,
    sources: dict[str, Any],
    rules: LeagueRules,
    registry: ClubRegistry,
    model_config: ModelConfig,
    n_simulations: int,
    seed: int,
    first_history_season: int,
    model_version: str = LEAGUE_MODEL_VERSION,
    backtest_summary: dict[str, Any] | None = None,
) -> LeagueForecast:
    reference_date = date.fromisoformat(str(sources["reference_date"]))
    engine, model, simulator = prepare(matches_data, rules, reference_date, model_config, first_history_season)
    result = simulator.run(n_simulations, seed, model_config.dynamic_ratings, model_config.uncertainty)
    club_ids = result.club_ids
    distribution = position_distribution(result)
    table = result.observed_table
    remaining_counts = np.zeros(len(club_ids), dtype=np.int64)
    for column in ("home_id", "away_id"):
        for club_id in result.remaining_matches[column]:
            remaining_counts[club_ids.index(str(club_id))] += 1
    clinch = {
        zone.zone_id: zone_clinch(table.points.astype(np.int64), remaining_counts, rules.points_win, zone)
        for zone in rules.zones
    }
    teams = []
    for position, club_id in enumerate(
        simulator.observed_order(season_complete=len(result.remaining_matches) == 0), start=1
    ):
        club = club_ids.index(club_id)
        club_points = result.points[:, club]
        teams.append(
            TeamForecast(
                club_id=club_id,
                name=registry.display_name(club_id),
                short_name=registry.clubs[club_id].short_name,
                position=position,
                played=int(table.played[club]),
                points=int(table.points[club]),
                wins=int(table.wins[club]),
                draws=int(table.draws[club]),
                losses=int(table.losses[club]),
                goals_for=int(table.goals_for[club]),
                goals_against=int(table.goals_against[club]),
                remaining=int(remaining_counts[club]),
                expected_points=float(club_points.mean()),
                points_interval_90=(float(np.percentile(club_points, 5)), float(np.percentile(club_points, 95))),
                expected_position=float(result.positions[:, club].mean() + 1),
                position_probabilities=[float(value) for value in distribution[club]],
                zones={
                    zone.zone_id: float(distribution[club, zone.first - 1 : zone.last].sum()) for zone in rules.zones
                },
                clinched={zone.zone_id: clinch[zone.zone_id][club] for zone in rules.zones},
                elo=float(engine.state.ratings[club_id].elo),
            )
        )

    remaining: list[MatchForecast] = []
    pending = result.remaining_matches
    if len(pending):
        feature_rows = pd.DataFrame(
            [engine.pre_match_features(str(match.home_id), str(match.away_id)) for match in pending.itertuples()]
        )
        outcome = model.outcome_probabilities(feature_rows)
        home_rate, away_rate = model.expected_goals(feature_rows)
        for position, match in enumerate(pending.itertuples(index=False)):
            status = str(match.status)
            kickoff = getattr(match, "kickoff_utc", None)
            remaining.append(
                MatchForecast(
                    match_id=str(match.match_id),
                    round=optional_int(match.round),
                    match_date=as_timestamp(match.match_date).date().isoformat(),
                    kickoff_utc=None if kickoff is None or pd.isna(kickoff) else str(kickoff),
                    status=status if status != MatchStatus.FINISHED.value else MatchStatus.SCHEDULED.value,
                    home_id=str(match.home_id),
                    away_id=str(match.away_id),
                    p_home=float(outcome[position, 0]),
                    p_draw=float(outcome[position, 1]),
                    p_away=float(outcome[position, 2]),
                    expected_home_goals=float(home_rate[position]),
                    expected_away_goals=float(away_rate[position]),
                )
            )

    late_finished = int(
        (
            (matches_data["season"] == rules.season)
            & (matches_data["status"] == MatchStatus.FINISHED.value)
            & (matches_data["match_date"].dt.date > reference_date)
        ).sum()
    )
    warnings = [
        rules.lot_note,
        "Tabela atual ordenada por pontos, saldo e gols; o confronto direto só entra na classificação final.",
        "Ratings fixos no que falta da temporada: a força de cada clube é a da data de referência.",
    ]
    if late_finished:
        warnings.append(f"{late_finished} jogos encerrados depois da data de referência ficaram de fora.")
    return LeagueForecast(
        competition=rules.code,
        competition_name=rules.name,
        season=rules.season,
        season_label=rules.season_label,
        reference_date=reference_date.isoformat(),
        generated_at=datetime.now(tz=UTC).isoformat(),
        n_simulations=n_simulations,
        seed=seed,
        observed_matches=len(result.observed_matches),
        remaining_matches=len(result.remaining_matches),
        model_version=model_version,
        data_version=data_version(sources),
        regulation={
            "title": rules.regulation_title,
            "url": rules.regulation_url,
            "date": rules.regulation_date,
            "note": rules.regulation_note,
        },
        tiebreak_order=list(rules.tiebreak_order),
        zones=[
            ZoneInfo(
                zone_id=zone.zone_id, label=zone.label, first=zone.first, last=zone.last, kind=zone.kind, note=zone.note
            )
            for zone in rules.zones
        ],
        warnings=warnings,
        sources=[
            SourceCredit(
                source_name=str(item["source_name"]),
                version=str(item["version"]),
                origin=str(item["origin"]),
                license_name=item.get("license_name"),
                attribution=item.get("attribution"),
                retrieved_at=str(item["retrieved_at"]),
            )
            for item in sources["sources"]
        ],
        teams=teams,
        remaining=remaining,
        backtest=backtest_summary,
    )
