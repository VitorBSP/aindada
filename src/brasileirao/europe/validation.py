"""Calibração e backtest do Elo entre ligas (ADR-0012, Decisão 3), com o protocolo do ADR-0006.

Validação: copas europeias de 2023/24. Teste (só relatado): 2024/25 e 2025/26. O modelo de gols é treinado só
com jogos das copas europeias de temporadas anteriores; as métricas são sobre os jogos da Champions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from brasileirao.europe.forecast import fit_goals_model
from brasileirao.europe.ratings import CUP_COMPETITIONS, GlobalElo, GlobalEloParams
from brasileirao.europe.simulation import STAGES, ChampionsSimulator, LeaguePhase
from brasileirao.validation.backtest import MatchMetrics, evaluate_predictions, walk_forward_predictions

VALIDATION_SEASONS = (2023,)
TEST_SEASONS = (2024, 2025)
FIRST_TRAINING_SEASON = 2022
FEATURE_SET = "elo_only"
GRID: dict[str, Sequence[float]] = {
    "k_factor": (20.0, 30.0, 40.0),
    "home_advantage": (60.0, 80.0, 100.0),
    "season_regression": (0.05, 0.1, 0.25),
    "newcomer_offset": (50.0, 100.0, 150.0),
    "unknown_offset": (100.0, 200.0, 300.0),
}


def cup_features(matches_data: pd.DataFrame, params: GlobalEloParams, countries: Mapping[str, str]) -> pd.DataFrame:
    features = GlobalElo(params, countries).run(matches_data)
    return features[features["competition"].isin(CUP_COMPETITIONS)].reset_index(drop=True)


def champions_metrics(features: pd.DataFrame, seasons: Sequence[int], feature_set: str = FEATURE_SET) -> MatchMetrics:
    predictions = walk_forward_predictions(features, seasons, feature_set, 10, FIRST_TRAINING_SEASON)
    champions_ids = set(features.loc[features["competition"] == "CL", "match_id"])
    return evaluate_predictions(predictions[predictions["match_id"].isin(champions_ids)])


def tune(
    matches_data: pd.DataFrame, countries: Mapping[str, str], base: GlobalEloParams | None = None
) -> tuple[GlobalEloParams, list[dict[str, Any]]]:
    """Busca coordenada: um parâmetro por vez, na ordem da grade, pelo log loss da validação."""
    params = base or GlobalEloParams()
    history = matches_data[matches_data["season"] < max(TEST_SEASONS) + 1]
    records: list[dict[str, Any]] = []
    for name, values in GRID.items():
        best_value, best_loss = getattr(params, name), float("inf")
        for value in values:
            candidate = replace(params, **{name: value})
            loss = champions_metrics(cup_features(history, candidate, countries), VALIDATION_SEASONS).log_loss
            records.append({**asdict(candidate), "validation_log_loss": loss})
            if loss < best_loss:
                best_value, best_loss = value, loss
        params = replace(params, **{name: best_value})
    return params, records


def match_report(matches_data: pd.DataFrame, countries: Mapping[str, str], params: GlobalEloParams) -> dict[str, Any]:
    history = matches_data[matches_data["season"] <= max(TEST_SEASONS)]
    features = cup_features(history, params, countries)
    report: dict[str, Any] = {}
    for feature_set in ("base_rate", FEATURE_SET):
        report[feature_set] = {
            period: asdict(champions_metrics(features, seasons, feature_set))
            for period, seasons in (("validation", VALIDATION_SEASONS), ("test", TEST_SEASONS))
        }
    return report


def grid_size() -> int:
    return len(list(product(*GRID.values())))


CHECKPOINT_MATCHDAYS = (4, 6)
STAGE_PREFIX = {
    "round_of_16": "Finals, Round of 16",
    "quarter_finals": "Finals, Quarterfinals",
    "semi_finals": "Finals, Semifinals",
    "final": "Finals, Final",
}


def _actual_outcomes(champions: pd.DataFrame, clubs: Sequence[str]) -> dict[str, dict[str, float]]:
    """O que aconteceu: top 8 = oitavas sem playoff; playoff = jogou o playoff; campeão pelo placar da final."""
    playoff_clubs = set(champions.loc[champions["stage"].str.startswith("Playoffs"), ["home_id", "away_id"]].stack())
    reached = {
        stage: set(champions.loc[champions["stage"] == prefix, ["home_id", "away_id"]].stack())
        for stage, prefix in STAGE_PREFIX.items()
    }
    final = champions[champions["stage"] == STAGE_PREFIX["final"]].iloc[0]
    home_total = (final["extra_time_home"] if pd.notna(final["extra_time_home"]) else final["home_goals"]) + (
        0 if pd.isna(final["penalties_home"]) else final["penalties_home"] * 100
    )
    away_total = (final["extra_time_away"] if pd.notna(final["extra_time_away"]) else final["away_goals"]) + (
        0 if pd.isna(final["penalties_away"]) else final["penalties_away"] * 100
    )
    winner = final["home_id"] if home_total > away_total else final["away_id"]
    outcomes: dict[str, dict[str, float]] = {}
    for club in clubs:
        top8 = club in reached["round_of_16"] and club not in playoff_clubs
        outcomes[club] = {
            "top8": float(top8),
            "playoff": float(club in playoff_clubs),
            "out": float(not top8 and club not in playoff_clubs),
            **{stage: float(club in clubs_in_stage) for stage, clubs_in_stage in reached.items()},
            "winner": float(club == winner),
        }
    return outcomes


def season_backtest(
    matches_data: pd.DataFrame,
    countries: Mapping[str, str],
    params: GlobalEloParams,
    seasons: Sequence[int] = TEST_SEASONS,
    n_simulations: int = 20_000,
    seed: int = 7,
) -> list[dict[str, Any]]:
    """Para cada temporada e rodada de corte: simula o resto com o que se sabia e pontua contra o que aconteceu."""
    records: list[dict[str, Any]] = []
    for season in seasons:
        champions = matches_data[(matches_data["competition"] == "CL") & (matches_data["season"] == season)]
        league = champions[champions["stage"].str.startswith("League")]
        clubs = tuple(sorted(set(league["home_id"]) | set(league["away_id"])))
        outcomes = _actual_outcomes(champions, clubs)
        for matchday in CHECKPOINT_MATCHDAYS:
            matchday_number = league["stage"].str.extract(r"Matchday (\d+)")[0].astype(int)
            cutoff = league.loc[matchday_number == matchday, "match_date"].max()
            engine = GlobalElo(params, countries)
            features = engine.run(matches_data[matches_data["match_date"] <= cutoff])
            model = fit_goals_model(features, season, goal_dispersion=True)
            phase = LeaguePhase(clubs, league[matchday_number <= matchday], league[matchday_number > matchday])
            simulator = ChampionsSimulator(
                phase, {club: engine.rating(club) for club in clubs}, model, params.home_advantage
            )
            result = simulator.run(n_simulations, seed)
            positions = result.positions
            predicted = {
                "top8": (positions < 8).mean(axis=0),
                "playoff": ((positions >= 8) & (positions < 24)).mean(axis=0),
                "out": (positions >= 24).mean(axis=0),
                **{stage: result.stage_counts[stage] for stage in STAGES},
            }
            record: dict[str, Any] = {"season": season, "matchday": matchday}
            for metric, values in predicted.items():
                actual = np.array([outcomes[club][metric] for club in clubs])
                base = actual.mean()
                record[f"{metric}_brier"] = float(np.mean((values - actual) ** 2))
                record[f"{metric}_brier_base"] = float(np.mean((base - actual) ** 2))
            winner_index = [outcomes[club]["winner"] for club in clubs].index(1.0)
            record["winner_log_loss"] = float(-np.log(max(predicted["winner"][winner_index], 1e-4)))
            record["winner_log_loss_uniform"] = float(np.log(len(clubs)))
            records.append(record)
    return records
