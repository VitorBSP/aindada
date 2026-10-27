"""Backtesting temporal: partidas (walk-forward por temporada) e snapshots de temporada.

Regras anti-vazamento:
- features pré-jogo vêm do processamento online (só partidas anteriores à data);
- o modelo de gols da temporada S é treinado apenas com temporadas < S;
- hiperparâmetros são escolhidos em temporadas de validação anteriores às de teste.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.competition_rules.standings import accumulate_table, rank_table
from brasileirao.config import AttackDefenseParams, EloParams, FormParams, RatingParams, SimulationUncertainty
from brasileirao.contracts import MatchStatus
from brasileirao.frame_values import as_int
from brasileirao.logging_utils import get_logger
from brasileirao.prediction.goals_model import GoalsModel
from brasileirao.prediction.metrics import (
    binary_brier,
    brier_score,
    calibration_table,
    expected_calibration_error,
    log_loss,
    outcome_index,
    poisson_deviance,
    ranked_probability_score,
)
from brasileirao.ratings.history import RatingEngine, RatingState, build_state_as_of, season_clubs_from_fixtures
from brasileirao.simulation.engine import SeasonSimulator

LOGGER = get_logger(__name__)


def compute_features(matches_data: pd.DataFrame, params: RatingParams) -> pd.DataFrame:
    finished = matches_data[matches_data["status"] == MatchStatus.FINISHED.value]
    engine = RatingEngine(params)
    return engine.run(finished, season_clubs_from_fixtures(matches_data))


def training_window(features: pd.DataFrame, season: int, window: int, first_season: int) -> pd.DataFrame:
    lower = max(first_season, season - window)
    return features[(features["season"] >= lower) & (features["season"] < season)]


@dataclass(frozen=True)
class MatchMetrics:
    n_matches: int
    log_loss: float
    brier: float
    rps: float
    home_goal_deviance: float
    away_goal_deviance: float


def _metrics(
    probabilities: np.ndarray, test_features: pd.DataFrame, home_rate: np.ndarray, away_rate: np.ndarray
) -> MatchMetrics:
    home_goals = test_features["home_goals"].to_numpy(dtype=np.int64)
    away_goals = test_features["away_goals"].to_numpy(dtype=np.int64)
    outcomes = outcome_index(home_goals, away_goals)
    return MatchMetrics(
        n_matches=len(test_features),
        log_loss=log_loss(probabilities, outcomes),
        brier=brier_score(probabilities, outcomes),
        rps=ranked_probability_score(probabilities, outcomes),
        home_goal_deviance=poisson_deviance(home_goals.astype(float), home_rate),
        away_goal_deviance=poisson_deviance(away_goals.astype(float), away_rate),
    )


def walk_forward_predictions(
    features: pd.DataFrame,
    test_seasons: Iterable[int],
    feature_set: str,
    window: int = 10,
    first_season: int = 2006,
    dixon_coles: bool = True,
    draw_inflation: bool = False,
) -> pd.DataFrame:
    """Probabilidades 1X2 e gols esperados fora da amostra, temporada a temporada."""
    prediction_frames: list[pd.DataFrame] = []
    for season in test_seasons:
        training = training_window(features, season, window, first_season)
        test = features[features["season"] == season]
        if feature_set == "base_rate":
            outcomes = outcome_index(training["home_goals"].to_numpy(), training["away_goals"].to_numpy())
            frequencies = np.bincount(outcomes, minlength=3) / len(outcomes)
            probabilities = np.tile(frequencies, (len(test), 1))
            home_rate = np.full(len(test), training["home_goals"].mean())
            away_rate = np.full(len(test), training["away_goals"].mean())
        else:
            model = GoalsModel.fit(training, feature_set, dixon_coles=dixon_coles, draw_inflation=draw_inflation)
            probabilities = model.outcome_probabilities(test)
            home_rate, away_rate = model.expected_goals(test)
        prediction_frames.append(
            pd.DataFrame(
                {
                    "match_id": test["match_id"].to_numpy(),
                    "season": season,
                    "home_goals": test["home_goals"].to_numpy(),
                    "away_goals": test["away_goals"].to_numpy(),
                    "p_home": probabilities[:, 0],
                    "p_draw": probabilities[:, 1],
                    "p_away": probabilities[:, 2],
                    "xg_home": home_rate,
                    "xg_away": away_rate,
                }
            )
        )
    return pd.concat(prediction_frames, ignore_index=True)


def evaluate_predictions(predictions: pd.DataFrame) -> MatchMetrics:
    probabilities = predictions[["p_home", "p_draw", "p_away"]].to_numpy()
    return _metrics(probabilities, predictions, predictions["xg_home"].to_numpy(), predictions["xg_away"].to_numpy())


def calibration_report(predictions: pd.DataFrame) -> dict[str, Any]:
    home_goals = predictions["home_goals"].to_numpy(dtype=np.int64)
    away_goals = predictions["away_goals"].to_numpy(dtype=np.int64)
    outcomes = outcome_index(home_goals, away_goals)
    report: dict[str, Any] = {}
    for outcome_position, outcome_name in enumerate(("home", "draw", "away")):
        table = calibration_table(
            predictions[f"p_{outcome_name}"].to_numpy(), (outcomes == outcome_position).astype(float)
        )
        report[outcome_name] = {"ece": expected_calibration_error(table), "bins": table}
    return report


def with_params(base: RatingParams, **changes: float) -> RatingParams:
    elo_changes = {key.removeprefix("elo_"): value for key, value in changes.items() if key.startswith("elo_")}
    ad_changes = {key.removeprefix("ad_"): value for key, value in changes.items() if key.startswith("ad_")}
    form_changes = {key.removeprefix("form_"): int(value) for key, value in changes.items() if key.startswith("form_")}
    return RatingParams(
        elo=replace(base.elo, **elo_changes) if elo_changes else base.elo,
        attack_defense=replace(base.attack_defense, **ad_changes) if ad_changes else base.attack_defense,
        form=replace(base.form, **form_changes) if form_changes else base.form,
    )


def tune_stage(
    matches_data: pd.DataFrame,
    base_params: RatingParams,
    grid: dict[str, Sequence[float]],
    feature_set: str,
    validation_seasons: Sequence[int],
) -> tuple[RatingParams, list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    best_params, best_loss = base_params, float("inf")
    names = list(grid)
    for values in product(*(grid[name] for name in names)):
        candidate_changes = dict(zip(names, values, strict=True))
        candidate = with_params(base_params, **candidate_changes)
        features = compute_features(matches_data, candidate)
        predictions = walk_forward_predictions(features, validation_seasons, feature_set)
        metrics = evaluate_predictions(predictions)
        records.append({**candidate_changes, "feature_set": feature_set, **asdict(metrics)})
        LOGGER.info("tuning_candidate", extra={**candidate_changes, "log_loss": metrics.log_loss})
        if metrics.log_loss < best_loss:
            best_params, best_loss = candidate, metrics.log_loss
    return best_params, records


def tune_rating_params(
    matches_data: pd.DataFrame, validation_seasons: Sequence[int]
) -> tuple[RatingParams, list[dict[str, Any]]]:
    """Busca coordenada: Elo → ataque/defesa → forma, sempre em temporadas de validação."""
    params = RatingParams(elo=EloParams(), attack_defense=AttackDefenseParams(), form=FormParams())
    all_records: list[dict[str, Any]] = []
    stages: list[tuple[dict[str, Sequence[float]], str]] = [
        (
            {
                "elo_k_factor": (6.0, 8.0, 10.0, 15.0, 20.0, 30.0),
                "elo_home_advantage": (50.0, 80.0),
                "elo_season_regression": (0.15, 0.3, 0.5),
            },
            "elo_only",
        ),
        ({"ad_learning_rate": (0.015, 0.03, 0.05), "ad_season_regression": (0.15, 0.3, 0.5)}, "attack_defense_only"),
        ({"form_span_matches": (2.0, 3.0, 6.0, 12.0)}, "full"),
    ]
    for grid, feature_set in stages:
        params, records = tune_stage(matches_data, params, grid, feature_set, validation_seasons)
        all_records.extend(records)
    return params, all_records


@dataclass(frozen=True)
class SeasonCheckpoint:
    season: int
    round_number: int
    reference_date: date


def season_checkpoints(
    matches_data: pd.DataFrame, seasons: Sequence[int], rounds: Sequence[int]
) -> list[SeasonCheckpoint]:
    checkpoints: list[SeasonCheckpoint] = []
    for season in seasons:
        season_matches = matches_data[matches_data["season"] == season]
        for round_number in rounds:
            round_dates = season_matches.loc[season_matches["round"] == round_number, "match_date"]
            if len(round_dates):
                checkpoints.append(SeasonCheckpoint(season, round_number, round_dates.max().date()))
    return checkpoints


def actual_final_order(season_matches: pd.DataFrame, rules: SeasonRules) -> list[str]:
    clubs = sorted(set(season_matches["home_id"]) | set(season_matches["away_id"]))
    club_index = {club: index for index, club in enumerate(clubs)}
    finished = season_matches[season_matches["status"] == MatchStatus.FINISHED.value]
    stats = accumulate_table(
        clubs,
        [club_index[club] for club in finished["home_id"]],
        [club_index[club] for club in finished["away_id"]],
        finished["home_goals"].astype(int).tolist(),
        finished["away_goals"].astype(int).tolist(),
        rules,
    )
    return rank_table(stats, rules)


@dataclass(frozen=True)
class SimulationVariant:
    name: str
    dynamic_ratings: bool = True
    draw_inflation: bool = False
    uncertainty: SimulationUncertainty = field(default_factory=SimulationUncertainty)


DYNAMIC_VS_FIXED = (SimulationVariant("dinamico", True), SimulationVariant("fixo", False))


@dataclass(frozen=True)
class PreparedCheckpoint:
    checkpoint: SeasonCheckpoint
    state: RatingState
    season_matches: pd.DataFrame
    rules: SeasonRules
    models: dict[bool, GoalsModel]
    actual_order: list[str]
    actual_points: dict[str, int]


def prepare_checkpoints(
    matches_data: pd.DataFrame,
    params: RatingParams,
    rules_template: SeasonRules,
    seasons: Sequence[int],
    rounds: Sequence[int],
    feature_set: str,
    window: int = 10,
) -> list[PreparedCheckpoint]:
    """Estado, modelos (com e sem inflação de empates) e resultado real de cada checkpoint.

    O estado de cada checkpoint é reconstruído do zero com `build_state_as_of`, porque a data de
    corte não cresce monotonicamente com a rodada quando há jogos adiados.
    """
    all_features = compute_features(matches_data, params)
    prepared: list[PreparedCheckpoint] = []
    for checkpoint in season_checkpoints(matches_data, seasons, rounds):
        engine, _ = build_state_as_of(matches_data, checkpoint.reference_date, checkpoint.season, params)
        rules = replace(rules_template, season=checkpoint.season)
        season_matches = matches_data[matches_data["season"] == checkpoint.season]
        training = training_window(all_features, checkpoint.season, window, 2006)
        prepared.append(
            PreparedCheckpoint(
                checkpoint=checkpoint,
                state=engine.state,
                season_matches=season_matches,
                rules=rules,
                models={
                    inflation: GoalsModel.fit(training, feature_set, draw_inflation=inflation)
                    for inflation in (False, True)
                },
                actual_order=actual_final_order(season_matches, rules),
                actual_points=_final_points(season_matches, rules),
            )
        )
    return prepared


def score_simulation_variants(
    prepared: Sequence[PreparedCheckpoint],
    params: RatingParams,
    variants: Sequence[SimulationVariant],
    n_simulations: int = 2000,
    seed: int = 7,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in prepared:
        for variant in variants:
            simulator = SeasonSimulator(
                item.season_matches,
                item.checkpoint.reference_date,
                item.state,
                item.models[variant.draw_inflation],
                params,
                item.rules,
            )
            result = simulator.run(n_simulations, seed, variant.dynamic_ratings, variant.uncertainty)
            record = _score_checkpoint(
                item.checkpoint, variant.dynamic_ratings, result, item.actual_order, item.actual_points
            )
            records.append({"variant": variant.name, **record})
    return records


def season_simulation_backtest(
    matches_data: pd.DataFrame,
    params: RatingParams,
    rules_template: SeasonRules,
    seasons: Sequence[int],
    rounds: Sequence[int],
    feature_set: str,
    n_simulations: int = 2000,
    seed: int = 7,
    window: int = 10,
    variants: Sequence[SimulationVariant] = DYNAMIC_VS_FIXED,
) -> list[dict[str, Any]]:
    """Simula snapshots históricos e pontua cada variante (por padrão, ratings dinâmicos vs. fixos)."""
    prepared = prepare_checkpoints(matches_data, params, rules_template, seasons, rounds, feature_set, window)
    return score_simulation_variants(prepared, params, variants, n_simulations, seed)


def _final_points(season_matches: pd.DataFrame, rules: SeasonRules) -> dict[str, int]:
    finished = season_matches[season_matches["status"] == MatchStatus.FINISHED.value]
    points: dict[str, int] = {}
    for match in finished.itertuples(index=False):
        home_goals, away_goals = as_int(match.home_goals), as_int(match.away_goals)
        home_points = (
            rules.points_win if home_goals > away_goals else (rules.points_draw if home_goals == away_goals else 0)
        )
        away_points = (
            rules.points_win if away_goals > home_goals else (rules.points_draw if home_goals == away_goals else 0)
        )
        points[str(match.home_id)] = points.get(str(match.home_id), 0) + home_points
        points[str(match.away_id)] = points.get(str(match.away_id), 0) + away_points
    return points


def _score_checkpoint(
    checkpoint: SeasonCheckpoint, dynamic: bool, result: Any, actual_order: list[str], actual_points: dict[str, int]
) -> dict[str, Any]:
    club_ids = list(result.club_ids)
    n_clubs = len(club_ids)
    actual_position = np.array([actual_order.index(club) for club in club_ids])
    positions = result.positions
    title_probability = (positions == 0).mean(axis=0)
    top4_probability = (positions < 4).mean(axis=0)
    relegation_probability = (positions >= n_clubs - 4).mean(axis=0)
    position_probability = (positions == actual_position[None, :]).mean(axis=0)
    expected_points = result.points.mean(axis=0)
    observed_points = np.array([actual_points[club] for club in club_ids])
    lower, upper = np.percentile(result.points, [5, 95], axis=0)
    return {
        "season": checkpoint.season,
        "round": checkpoint.round_number,
        "reference_date": checkpoint.reference_date.isoformat(),
        "dynamic_ratings": dynamic,
        "title_brier": binary_brier(title_probability, (actual_position == 0).astype(float)),
        "top4_brier": binary_brier(top4_probability, (actual_position < 4).astype(float)),
        "relegation_brier": binary_brier(relegation_probability, (actual_position >= n_clubs - 4).astype(float)),
        "position_log_loss": float(-np.mean(np.log(np.clip(position_probability, 1e-4, 1.0)))),
        "points_mae": float(np.mean(np.abs(expected_points - observed_points))),
        "points_interval_90_coverage": float(np.mean((observed_points >= lower) & (observed_points <= upper))),
    }
