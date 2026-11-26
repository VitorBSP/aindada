"""Previsão da Champions League (ADR-0012): Elo entre ligas, modelo de gols das copas e simulação completa.

Fase de liga em andamento: simula o resto da fase e o mata-mata inteiro. Fase de liga encerrada: parte do mata-mata
real (europe/knockout.py), com os confrontos, placares e mandos que a fonte trouxe. Formato fora do conhecido trava.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from brasileirao.config import MODEL_VERSION
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.europe.knockout import (
    KNOCKOUT_STAGES,
    NEXT_STAGE,
    STAGE_LABELS,
    TIES_PER_STAGE,
    KnockoutFormatError,
    Leg,
    RealTie,
    check_progression,
    consistent_configs,
    league_complete,
    read_knockout,
)
from brasileirao.europe.ratings import CUP_COMPETITIONS, GlobalElo, GlobalEloParams
from brasileirao.europe.simulation import STAGES, ChampionsSimulation, ChampionsSimulator, split_league_phase
from brasileirao.frame_values import as_int, as_timestamp, optional_int
from brasileirao.leagues.forecast import zone_clinch
from brasileirao.leagues.rules import Zone
from brasileirao.leagues.schema import ClinchState, SourceCredit
from brasileirao.prediction.goals_model import GoalsModel

CHAMPIONS_SCHEMA_VERSION = "1.1"
CHAMPIONS_MODEL_VERSION = f"champions-0.1.0+{MODEL_VERSION}"
ZONES = (
    Zone("top8", "Direto às oitavas", 1, 8, "up"),
    Zone("playoff", "Playoff", 9, 24, "up"),
    Zone("out", "Eliminado", 25, 36, "down"),
)
TRAINING_SEASONS_WINDOW = 4
KNOCKOUT_WARNINGS = (
    "Mata-mata a partir do real: confronto decidido não é sorteado, ida disputada entra com o placar real e o mando "
    "é o da fonte.",
    "Enquanto a fonte não mostra o cruzamento das fases seguintes (lado da chave), a simulação sorteia entre os "
    "chaveamentos do regulamento que batem com os confrontos já conhecidos.",
)
REGULATION_TITLE = "Regulations of the UEFA Champions League 2026/27, Art. 18 (empate na fase de liga) e Art. 19"
REGULATION_URL = (
    "https://documents.uefa.com/r/Regulations-of-the-UEFA-Champions-League-2026/27/"
    "Article-18-Equality-of-points-league-phase-Online"
)


class ClubForecast(BaseModel):
    club_id: str
    name: str
    short_name: str
    country: str
    position: int = Field(ge=1)
    played: int
    points: int
    goals_for: int
    goals_against: int
    expected_points: float
    position_probabilities: list[float]
    zones: dict[str, float]
    clinched: dict[str, ClinchState | None]
    stages: dict[str, float]
    elo: float


class ChampionsMatch(BaseModel):
    match_id: str
    round: int | None
    match_date: str
    kickoff_utc: str | None
    home_id: str
    away_id: str
    p_home: float
    p_draw: float
    p_away: float


class KnockoutLeg(BaseModel):
    """Jogo do mata-mata. Encerrado: placar de 90 minutos, prorrogação (total dos 120) e pênaltis, sem probabilidade.
    Por disputar: sem placar e com a probabilidade do modelo para os 90 minutos."""

    match_id: str
    leg: int = Field(ge=1, le=2)
    match_date: str
    kickoff_utc: str | None
    home_id: str
    away_id: str
    status: str
    home_goals: int | None = None
    away_goals: int | None = None
    extra_time: list[int] | None = None
    penalties: list[int] | None = None
    p_home: float | None = None
    p_draw: float | None = None
    p_away: float | None = None


class KnockoutTie(BaseModel):
    """`club_ids` = (mandante da ida, mandante da volta); na final, os dois finalistas. `aggregate` na mesma ordem,
    com a prorrogação somada. `advance` = probabilidade de cada um passar (1 e 0 quando decidido)."""

    stage: str
    stage_label: str
    club_ids: list[str]
    legs: list[KnockoutLeg]
    aggregate: list[int] | None
    winner_id: str | None
    advance: dict[str, float]


class ChampionsForecast(BaseModel):
    schema_version: str = CHAMPIONS_SCHEMA_VERSION
    competition: str = "champions-league"
    competition_name: str
    season: int
    season_label: str
    reference_date: str
    generated_at: str
    n_simulations: int
    seed: int
    observed_matches: int
    remaining_matches: int
    model_version: str
    data_version: str
    regulation: dict[str, str]
    zones: list[dict[str, Any]]
    warnings: list[str]
    sources: list[SourceCredit]
    clubs: list[ClubForecast]
    remaining: list[ChampionsMatch]
    backtest: dict[str, Any] | None = None
    phase: str = "league"
    current_stage: str | None = None
    knockout: list[KnockoutTie] = Field(default_factory=list)


def knockout_ties(champions: pd.DataFrame, reference: pd.Timestamp) -> tuple[dict[str, list[RealTie]], bool]:
    """Confrontos reais e se a fase de liga acabou. Mata-mata com a fase de liga em andamento trava (formato novo)."""
    ties = read_knockout(champions, reference)
    done = league_complete(champions, reference)
    if not done and any(ties[stage] for stage in KNOCKOUT_STAGES):
        raise KnockoutFormatError("jogos do mata-mata com a fase de liga ainda em andamento")
    return ties, done


def current_stage(ties: dict[str, list[RealTie]]) -> str:
    """Primeira fase com confronto por decidir; sem nenhum, a fase seguinte à última decidida (a do sorteio)."""
    for stage in KNOCKOUT_STAGES:
        stage_ties = ties[stage]
        if len(stage_ties) < TIES_PER_STAGE[stage] or any(tie.winner is None for tie in stage_ties):
            return stage
    return "FINAL"


def data_version(sources: dict[str, Any]) -> str:
    tags = sorted(str(item["tag"]) for item in sources["sources"])
    return hashlib.sha256("|".join(tags).encode("utf-8")).hexdigest()[:12]


def fit_goals_model(features: pd.DataFrame, season: int, goal_dispersion: bool) -> GoalsModel:
    cups = features[
        features["competition"].isin(CUP_COMPETITIONS)
        & (features["season"] < season)
        & (features["season"] >= season - TRAINING_SEASONS_WINDOW)
    ]
    return GoalsModel.fit(cups, "elo_only", goal_dispersion=goal_dispersion)


def build_forecast(
    matches_data: pd.DataFrame,
    sources: dict[str, Any],
    registry: ClubRegistry,
    countries: Mapping[str, str],
    params: GlobalEloParams,
    season: int,
    n_simulations: int,
    seed: int,
    goal_dispersion: bool = True,
    backtest: dict[str, Any] | None = None,
) -> ChampionsForecast:
    reference_date = date.fromisoformat(str(sources["reference_date"]))
    reference = pd.Timestamp(reference_date)
    engine = GlobalElo(params, countries)
    features = engine.run(matches_data[matches_data["match_date"] <= reference])
    engine.start_season_if_needed(season)
    model = fit_goals_model(features, season, goal_dispersion)
    champions = matches_data[(matches_data["competition"] == "CL") & (matches_data["season"] == season)]
    ties, league_done = knockout_ties(champions, reference)
    phase = split_league_phase(champions, reference)
    ratings = {club: engine.rating(club) for club in phase.club_ids}
    simulator = ChampionsSimulator(phase, ratings, model, params.home_advantage)
    final_order: list[int] | None = None
    result: ChampionsSimulation
    if league_done:
        final_order = [int(club) for club in simulator.final_league_order()]
        league_position = {phase.club_ids[club]: rank for rank, club in enumerate(final_order, start=1)}
        check_progression(ties, league_position)
        result = simulator.run_knockout(n_simulations, seed, ties, consistent_configs(ties, league_position))
    else:
        result = simulator.run(n_simulations, seed)
    n_clubs = len(phase.club_ids)
    distribution = np.stack([(result.positions == position).mean(axis=0) for position in range(n_clubs)], axis=1)
    played = np.zeros(n_clubs, dtype=np.int64)
    goals_for = np.zeros(n_clubs, dtype=np.int64)
    goals_against = np.zeros(n_clubs, dtype=np.int64)
    points_now = np.zeros(n_clubs, dtype=np.int64)
    for match in phase.observed.itertuples(index=False):
        home, away = simulator.index[str(match.home_id)], simulator.index[str(match.away_id)]
        home_goals, away_goals = as_int(match.home_goals), as_int(match.away_goals)
        played[[home, away]] += 1
        goals_for[home] += home_goals
        goals_against[home] += away_goals
        goals_for[away] += away_goals
        goals_against[away] += home_goals
        points_now[home] += 3 if home_goals > away_goals else 1 if home_goals == away_goals else 0
        points_now[away] += 3 if away_goals > home_goals else 1 if home_goals == away_goals else 0
    remaining_counts = 8 - played
    clinch = {zone.zone_id: zone_clinch(points_now, remaining_counts, 3, zone) for zone in ZONES}
    current_order = final_order or sorted(
        range(n_clubs),
        key=lambda club: (
            -points_now[club],
            -(goals_for[club] - goals_against[club]),
            -goals_for[club],
            phase.club_ids[club],
        ),
    )
    clubs = []
    for position, club in enumerate(current_order, start=1):
        club_id = phase.club_ids[club]
        clubs.append(
            ClubForecast(
                club_id=club_id,
                name=registry.display_name(club_id),
                short_name=registry.clubs[club_id].short_name,
                country=countries[club_id],
                position=position,
                played=int(played[club]),
                points=int(points_now[club]),
                goals_for=int(goals_for[club]),
                goals_against=int(goals_against[club]),
                expected_points=float(result.points[:, club].mean()),
                position_probabilities=[float(value) for value in distribution[club]],
                zones={zone.zone_id: float(distribution[club, zone.first - 1 : zone.last].sum()) for zone in ZONES},
                clinched={zone.zone_id: clinch[zone.zone_id][club] for zone in ZONES},
                stages={stage: float(result.stage_counts[stage][club]) for stage in STAGES},
                elo=float(ratings[club_id]),
            )
        )
    remaining = []
    for match in phase.remaining.itertuples(index=False):
        diff = np.array([ratings[str(match.home_id)] + params.home_advantage - ratings[str(match.away_id)]])
        outcome = model.outcome_probabilities({"elo_diff": diff})[0]
        kickoff = match.kickoff_utc if isinstance(match.kickoff_utc, str) else None
        remaining.append(
            ChampionsMatch(
                match_id=str(match.match_id),
                round=optional_int(match.round),
                match_date=as_timestamp(match.match_date).date().isoformat(),
                kickoff_utc=kickoff,
                home_id=str(match.home_id),
                away_id=str(match.away_id),
                p_home=float(outcome[0]),
                p_draw=float(outcome[1]),
                p_away=float(outcome[2]),
            )
        )
    knockout = (
        knockout_view(ties, result, simulator.index, ratings, model, params.home_advantage) if league_done else []
    )
    return ChampionsForecast(
        competition_name=f"Champions League {season}/{str(season + 1)[2:]}",
        season=season,
        season_label=f"{season}/{str(season + 1)[2:]}",
        reference_date=reference_date.isoformat(),
        generated_at=datetime.now(tz=UTC).isoformat(),
        n_simulations=n_simulations,
        seed=seed,
        observed_matches=len(phase.observed),
        remaining_matches=len(phase.remaining),
        model_version=CHAMPIONS_MODEL_VERSION,
        data_version=data_version(sources),
        regulation={
            "title": REGULATION_TITLE,
            "url": REGULATION_URL,
            "date": "2026-07-29",
        },
        zones=[
            {"zone_id": z.zone_id, "label": z.label, "first": z.first, "last": z.last, "kind": z.kind} for z in ZONES
        ],
        warnings=[
            "Pontos disciplinares e coeficiente da UEFA (últimos critérios de desempate) viram sorteio: sem dados.",
            "Onde a UEFA sorteia (lado da chave e confronto em cada seção), "
            "a simulação sorteia com probabilidades iguais.",
            "Prorrogação com um terço das taxas de gol; pênaltis 50/50.",
            "Ratings fixos no que falta da competição; a força de cada clube é a da data de referência.",
            *(KNOCKOUT_WARNINGS if league_done else ()),
        ],
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
        clubs=clubs,
        remaining=remaining,
        backtest=backtest,
        phase="knockout" if league_done else "league",
        current_stage=current_stage(ties) if league_done else None,
        knockout=knockout,
    )


def _leg_view(
    leg_number: int, leg: Leg, ratings: Mapping[str, float], model: GoalsModel, advantage: float, neutral: bool
) -> KnockoutLeg:
    view = KnockoutLeg(
        match_id=leg.match_id,
        leg=leg_number,
        match_date=leg.match_date.isoformat(),
        kickoff_utc=leg.kickoff_utc,
        home_id=leg.home_id,
        away_id=leg.away_id,
        status="finished" if leg.finished else "scheduled",
    )
    if leg.finished:
        return view.model_copy(
            update={
                "home_goals": leg.home_goals,
                "away_goals": leg.away_goals,
                "extra_time": list(leg.extra_time) if leg.extra_time else None,
                "penalties": list(leg.penalties) if leg.penalties else None,
            }
        )
    diff = ratings[leg.home_id] + (0.0 if neutral else advantage) - ratings[leg.away_id]
    outcome = model.outcome_probabilities({"elo_diff": np.array([diff])})[0]
    return view.model_copy(
        update={"p_home": float(outcome[0]), "p_draw": float(outcome[1]), "p_away": float(outcome[2])}
    )


def knockout_view(
    ties: dict[str, list[RealTie]],
    result: ChampionsSimulation,
    index: Mapping[str, int],
    ratings: Mapping[str, float],
    model: GoalsModel,
    advantage: float,
) -> list[KnockoutTie]:
    """Confrontos reais com placares e a probabilidade de cada clube passar, tirada da mesma simulação."""
    view = []
    for stage in KNOCKOUT_STAGES:
        reached = result.stage_counts[NEXT_STAGE[stage]]
        for tie in ties[stage]:
            neutral = stage == "FINAL"
            view.append(
                KnockoutTie(
                    stage=stage,
                    stage_label=STAGE_LABELS[stage],
                    club_ids=list(tie.clubs),
                    legs=[
                        _leg_view(number, leg, ratings, model, advantage, neutral)
                        for number, leg in enumerate(tie.legs, start=1)
                    ],
                    aggregate=list(tie.aggregate) if tie.aggregate else None,
                    winner_id=tie.winner,
                    advance={club: float(reached[index[club]]) for club in tie.clubs},
                )
            )
    return view
