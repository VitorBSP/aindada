"""Histórico rodada a rodada da fase de liga da Champions (`data/history.json`).

Cada rodada (1 a 8) já disputada vira um ponto: a previsão refeita como se a data de referência fosse o último jogo
dela, com o modelo de hoje e a mesma semente. Todo ponto anterior à edição é reconstrução (R18). O último ponto é a
própria edição publicada, sem recalcular. O mata-mata não entra: a história cobre a fase de liga.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from brasileirao.contracts import MatchStatus
from brasileirao.europe.forecast import ZONES, ChampionsForecast, fit_goals_model
from brasileirao.europe.ratings import GlobalElo, GlobalEloParams
from brasileirao.europe.simulation import STAGES, ChampionsSimulator, split_league_phase
from brasileirao.frame_values import as_int
from brasileirao.leagues.schema import CompetitionHistory, HistoryPoint, HistoryTeam, ZoneInfo

HISTORY_SIMULATIONS = 5_000
LEAGUE_STAGE = "LEAGUE_STAGE"


def matchday_end_dates(matches_data: pd.DataFrame, season: int, up_to: date) -> list[tuple[int, date]]:
    """(rodada da fase de liga, último dia com jogo encerrado dela) até `up_to`, por data crescente."""
    finished = matches_data[
        (matches_data["competition"] == "CL")
        & (matches_data["season"] == season)
        & (matches_data["stage"] == LEAGUE_STAGE)
        & (matches_data["status"] == MatchStatus.FINISHED.value)
        & matches_data["round"].notna()
    ]
    by_date: dict[date, int] = {}
    for round_number, round_matches in finished.groupby("round"):
        last_day = round_matches["match_date"].max().date()
        if last_day <= up_to:
            by_date[last_day] = max(by_date.get(last_day, 0), as_int(round_number))
    return [(round_number, day) for day, round_number in sorted(by_date.items())]


def _is_reconstruction(matches_data: pd.DataFrame, season: int, day: date) -> bool:
    later = matches_data[
        (matches_data["competition"] == "CL")
        & (matches_data["season"] == season)
        & (matches_data["status"] == MatchStatus.FINISHED.value)
    ]
    return bool((later["match_date"].dt.date > day).any())


def forecast_point(forecast: ChampionsForecast, round_number: int, reconstructed: bool) -> HistoryPoint:
    return HistoryPoint(
        round=round_number,
        reference_date=forecast.reference_date,
        reconstructed=reconstructed,
        observed_matches=forecast.observed_matches,
        n_simulations=forecast.n_simulations,
        teams={
            club.club_id: HistoryTeam(
                position=club.position,
                points=club.points,
                expected_points=round(club.expected_points, 2),
                zones={zone_id: round(value, 4) for zone_id, value in club.zones.items()},
                stages={stage: round(value, 4) for stage, value in club.stages.items()},
            )
            for club in forecast.clubs
        },
    )


def build_history(
    matches_data: pd.DataFrame,
    forecast: ChampionsForecast,
    countries: Mapping[str, str],
    params: GlobalEloParams,
    n_simulations: int = HISTORY_SIMULATIONS,
    seed: int | None = None,
    goal_dispersion: bool = True,
) -> CompetitionHistory:
    final_date = date.fromisoformat(forecast.reference_date)
    history_seed = forecast.seed if seed is None else seed
    season = forecast.season
    ended = matchday_end_dates(matches_data, season, final_date)
    league_done_round = max((round_number for round_number, _ in ended), default=0)
    # Fase de liga em andamento: a própria edição é o último ponto (sem duplicar a rodada). Mata-mata: todas as rodadas.
    last_day = max((day for _, day in ended), default=final_date)
    earlier = [(number, day) for number, day in ended if forecast.phase != "league" or day < last_day]
    points: list[HistoryPoint] = []
    if earlier:
        full_engine = GlobalElo(params, countries)
        features = full_engine.run(matches_data[matches_data["match_date"] <= pd.Timestamp(final_date)])
        model = fit_goals_model(features, season, goal_dispersion)
        champions = matches_data[(matches_data["competition"] == "CL") & (matches_data["season"] == season)]
        for round_number, day in earlier:
            reference = pd.Timestamp(day)
            engine = GlobalElo(params, countries)
            engine.run(matches_data[matches_data["match_date"] <= reference])
            engine.start_season_if_needed(season)
            phase = split_league_phase(champions, reference)
            ratings = {club: engine.rating(club) for club in phase.club_ids}
            simulator = ChampionsSimulator(phase, ratings, model, params.home_advantage)
            result = simulator.run(n_simulations, history_seed)
            n_clubs = len(phase.club_ids)
            distribution = np.stack(
                [(result.positions == position).mean(axis=0) for position in range(n_clubs)], axis=1
            )
            table = _table_now(phase.observed, simulator.index, n_clubs)
            order = sorted(
                range(n_clubs),
                key=lambda club: (-table[club][0], -table[club][1], -table[club][2], phase.club_ids[club]),
            )
            teams: dict[str, HistoryTeam] = {}
            for position, club in enumerate(order, start=1):
                teams[phase.club_ids[club]] = HistoryTeam(
                    position=position,
                    points=int(table[club][0]),
                    expected_points=round(float(result.points[:, club].mean()), 2),
                    zones={
                        zone.zone_id: round(float(distribution[club, zone.first - 1 : zone.last].sum()), 4)
                        for zone in ZONES
                    },
                    stages={stage: round(float(result.stage_counts[stage][club]), 4) for stage in STAGES},
                )
            points.append(
                HistoryPoint(
                    round=round_number,
                    reference_date=day.isoformat(),
                    reconstructed=_is_reconstruction(matches_data, season, day),
                    observed_matches=len(phase.observed),
                    n_simulations=n_simulations,
                    teams=teams,
                )
            )
    if forecast.phase == "league" and league_done_round:
        points.append(forecast_point(forecast, league_done_round, _is_reconstruction(matches_data, season, final_date)))
    return CompetitionHistory(
        competition=forecast.competition,
        season=season,
        history_mode="reconstructed" if any(point.reconstructed for point in points) else "recorded",
        generated_at=datetime.now(tz=UTC).isoformat(),
        model_version=forecast.model_version,
        data_version=forecast.data_version,
        n_simulations=n_simulations,
        seed=history_seed,
        zones=[
            ZoneInfo(zone_id=zone.zone_id, label=zone.label, first=zone.first, last=zone.last, kind=zone.kind)
            for zone in ZONES
        ],
        points=points,
    )


def _table_now(observed: pd.DataFrame, index: Mapping[str, int], n_clubs: int) -> list[tuple[int, int, int]]:
    """(pontos, saldo, gols marcados) de cada clube só com os jogos encerrados até a data."""
    values = [[0, 0, 0] for _ in range(n_clubs)]
    for match in observed.itertuples(index=False):
        home, away = index[str(match.home_id)], index[str(match.away_id)]
        home_goals, away_goals = as_int(match.home_goals), as_int(match.away_goals)
        values[home][0] += 3 if home_goals > away_goals else 1 if home_goals == away_goals else 0
        values[away][0] += 3 if away_goals > home_goals else 1 if home_goals == away_goals else 0
        values[home][1] += home_goals - away_goals
        values[away][1] += away_goals - home_goals
        values[home][2] += home_goals
        values[away][2] += away_goals
    return [(row[0], row[1], row[2]) for row in values]
