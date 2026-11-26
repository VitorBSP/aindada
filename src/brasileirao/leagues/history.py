"""Histórico rodada a rodada de uma liga (`data/history.json`).

Para cada rodada já disputada, refaz a previsão como se a data de referência fosse o último jogo dela, com o modelo de
hoje e a mesma semente. Todo ponto anterior à última data é reconstrução (R18, `reconstructed: true`): nunca é o que o
site publicou na época. Só entra informação até a data de cada ponto (as notas só usam jogos de até aquele dia).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from brasileirao.contracts import MatchStatus
from brasileirao.frame_values import as_int
from brasileirao.leagues.forecast import prepare
from brasileirao.leagues.rules import LeagueRules
from brasileirao.leagues.schema import CompetitionHistory, HistoryPoint, HistoryTeam, LeagueForecast
from brasileirao.pipeline import ModelConfig, is_reconstruction
from brasileirao.simulation.summary import position_distribution

HISTORY_FILE_NAME = "history.json"
HISTORY_SIMULATIONS = 5_000


def round_end_dates(matches_data: pd.DataFrame, season: int, up_to: date) -> list[tuple[int, date]]:
    """(rodada, último dia com jogo encerrado dela) até `up_to`, por data crescente.

    Duas rodadas que terminam no mesmo dia ficam com a maior (a tabela daquele dia já tem as duas).
    """
    finished = matches_data[
        (matches_data["season"] == season)
        & (matches_data["status"] == MatchStatus.FINISHED.value)
        & matches_data["round"].notna()
    ]
    by_date: dict[date, int] = {}
    for round_number, round_matches in finished.groupby("round"):
        last_day = round_matches["match_date"].max().date()
        if last_day <= up_to:
            by_date[last_day] = max(by_date.get(last_day, 0), as_int(round_number))
    return [(round_number, day) for day, round_number in sorted(by_date.items())]


def forecast_point(forecast: LeagueForecast, round_number: int, reconstructed: bool) -> HistoryPoint:
    """O último ponto é a própria previsão publicada: mesmos números do `forecast.json`, sem recalcular."""
    return HistoryPoint(
        round=round_number,
        reference_date=forecast.reference_date,
        reconstructed=reconstructed,
        observed_matches=forecast.observed_matches,
        n_simulations=forecast.n_simulations,
        teams={
            team.club_id: HistoryTeam(
                position=team.position,
                points=team.points,
                expected_points=round(team.expected_points, 2),
                zones={zone_id: round(value, 4) for zone_id, value in team.zones.items()},
            )
            for team in forecast.teams
        },
    )


def build_history(
    matches_data: pd.DataFrame,
    forecast: LeagueForecast,
    rules: LeagueRules,
    model_config: ModelConfig,
    first_history_season: int,
    n_simulations: int = HISTORY_SIMULATIONS,
    seed: int | None = None,
) -> CompetitionHistory:
    """Uma previsão por rodada encerrada antes da data da edição, mais a própria edição como último ponto."""
    final_date = date.fromisoformat(forecast.reference_date)
    history_seed = forecast.seed if seed is None else seed
    season_finished = matches_data[
        (matches_data["season"] == rules.season)
        & (matches_data["status"] == MatchStatus.FINISHED.value)
        & (matches_data["match_date"].dt.date <= final_date)
    ]
    latest_round = as_int(season_finished["round"].max()) if season_finished["round"].notna().any() else 0
    last_played = season_finished["match_date"].max().date() if len(season_finished) else final_date
    # Sem jogo entre o último dia de rodada e a edição, a própria edição já é aquele ponto (não duplica a rodada).
    earlier = [
        (number, day) for number, day in round_end_dates(matches_data, rules.season, final_date) if day < last_played
    ]
    points: list[HistoryPoint] = []
    if earlier:
        _, goals_model, _ = prepare(matches_data, rules, final_date, model_config, first_history_season)
        for round_number, day in earlier:
            _, _, simulator = prepare(matches_data, rules, day, model_config, first_history_season, goals_model)
            result = simulator.run(n_simulations, history_seed, model_config.dynamic_ratings, model_config.uncertainty)
            distribution = position_distribution(result)
            table = result.observed_table
            teams: dict[str, HistoryTeam] = {}
            for position, club_id in enumerate(simulator.observed_order(season_complete=False), start=1):
                club = result.club_ids.index(club_id)
                teams[club_id] = HistoryTeam(
                    position=position,
                    points=int(table.points[club]),
                    expected_points=round(float(np.mean(result.points[:, club])), 2),
                    zones={
                        zone.zone_id: round(float(distribution[club, zone.first - 1 : zone.last].sum()), 4)
                        for zone in rules.zones
                    },
                )
            points.append(
                HistoryPoint(
                    round=round_number,
                    reference_date=day.isoformat(),
                    reconstructed=is_reconstruction(matches_data, rules.season, day),
                    observed_matches=len(result.observed_matches),
                    n_simulations=n_simulations,
                    teams=teams,
                )
            )
    if latest_round:
        points.append(forecast_point(forecast, latest_round, is_reconstruction(matches_data, rules.season, final_date)))
    return CompetitionHistory(
        competition=forecast.competition,
        season=forecast.season,
        history_mode="reconstructed" if any(point.reconstructed for point in points) else "recorded",
        generated_at=datetime.now(tz=UTC).isoformat(),
        model_version=forecast.model_version,
        data_version=forecast.data_version,
        n_simulations=n_simulations,
        seed=history_seed,
        zones=forecast.zones,
        points=points,
    )
