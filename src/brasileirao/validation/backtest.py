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
    score_log_loss: float = float("nan")
    total_goals_log_loss: float = float("nan")


def _metrics(
    probabilities: np.ndarray, test_features: pd.DataFrame, home_rate: np.ndarray, away_rate: np.ndarray
) -> MatchMetrics:
    home_goals = test_features["home_goals"].to_numpy(dtype=np.int64)
    away_goals = test_features["away_goals"].to_numpy(dtype=np.int64)
    outcomes = outcome_index(home_goals, away_goals)
    score_log_loss, total_goals_log_loss = float("nan"), float("nan")
    if "p_observed_score" in test_features:
        score_log_loss = _mean_negative_log(test_features["p_observed_score"].to_numpy(dtype=np.float64))
        total_goals_log_loss = _mean_negative_log(test_features["p_observed_total"].to_numpy(dtype=np.float64))
    return MatchMetrics(
        n_matches=len(test_features),
        log_loss=log_loss(probabilities, outcomes),
        brier=brier_score(probabilities, outcomes),
        rps=ranked_probability_score(probabilities, outcomes),
        home_goal_deviance=poisson_deviance(home_goals.astype(float), home_rate),
        away_goal_deviance=poisson_deviance(away_goals.astype(float), away_rate),
        score_log_loss=score_log_loss,
        total_goals_log_loss=total_goals_log_loss,
    )


def _mean_negative_log(probabilities: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(probabilities, 1e-12, 1.0))))


def total_goals_probabilities(matrices: np.ndarray) -> np.ndarray:
    """(n, 2·max_goals + 1): P(total de gols = k) a partir das matrizes de placar."""
    size = matrices.shape[-1]
    totals = np.zeros((len(matrices), 2 * size - 1))
    for home_goals in range(size):
        totals[:, home_goals : home_goals + size] += matrices[:, home_goals, :]
    return totals


def _base_rate_matrices(training: pd.DataFrame, n_rows: int, max_goals: int) -> np.ndarray:
    """Frequências empíricas de placar no treino (com suavização de Laplace), iguais para todos os jogos."""
    counts = np.ones((max_goals + 1, max_goals + 1))
    np.add.at(
        counts,
        (
            np.minimum(training["home_goals"].to_numpy(dtype=np.int64), max_goals),
            np.minimum(training["away_goals"].to_numpy(dtype=np.int64), max_goals),
        ),
        1.0,
    )
    return np.broadcast_to(counts / counts.sum(), (n_rows, max_goals + 1, max_goals + 1))


def observed_score_probabilities(matrices: np.ndarray, test_features: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Probabilidade prevista do placar exato e do total de gols observados (placares acima do teto vão ao teto)."""
    max_goals = matrices.shape[-1] - 1
    home_goals = np.minimum(test_features["home_goals"].to_numpy(dtype=np.int64), max_goals)
    away_goals = np.minimum(test_features["away_goals"].to_numpy(dtype=np.int64), max_goals)
    rows = np.arange(len(home_goals))
    return matrices[rows, home_goals, away_goals], total_goals_probabilities(matrices)[rows, home_goals + away_goals]


def walk_forward_predictions(
    features: pd.DataFrame,
    test_seasons: Iterable[int],
    feature_set: str,
    window: int = 10,
    first_season: int = 2006,
    dixon_coles: bool = True,
    draw_inflation: bool = False,
    goal_dispersion: bool = False,
) -> pd.DataFrame:
    """Probabilidades 1X2, gols esperados e probabilidade do placar e do total observados, fora da amostra."""
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
            matrices = _base_rate_matrices(training, len(test), 10)
        else:
            model = GoalsModel.fit(
                training,
                feature_set,
                dixon_coles=dixon_coles,
                draw_inflation=draw_inflation,
                goal_dispersion=goal_dispersion,
            )
            matrices = model.score_probabilities(test)
            probabilities = model.outcome_probabilities(test)
            home_rate, away_rate = model.expected_goals(test)
        observed_score, observed_total = observed_score_probabilities(matrices, test)
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
                    "p_observed_score": observed_score,
                    "p_observed_total": observed_total,
                }
            )
        )
    return pd.concat(prediction_frames, ignore_index=True)


GOAL_COUNT_BUCKETS = 5
TOTAL_GOAL_LINES = (1.5, 2.5, 3.5)
DIAGNOSTIC_SCORES = ((0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2), (2, 1), (1, 2), (2, 2), (3, 0), (3, 1), (1, 3))


def _predicted_observed(predicted: np.ndarray, observed: np.ndarray) -> dict[str, float]:
    return {"predicted": float(np.mean(predicted)), "observed": float(np.mean(observed))}


def _count_buckets(pmf: np.ndarray, observed: np.ndarray) -> dict[str, dict[str, float]]:
    buckets = {str(goals): _predicted_observed(pmf[:, goals], observed == goals) for goals in range(GOAL_COUNT_BUCKETS)}
    buckets[f"{GOAL_COUNT_BUCKETS}+"] = _predicted_observed(
        pmf[:, GOAL_COUNT_BUCKETS:].sum(axis=1), observed >= GOAL_COUNT_BUCKETS
    )
    return buckets


def goal_distribution_summary(matrices: np.ndarray, test_features: pd.DataFrame) -> dict[str, Any]:
    """Previsto (média das matrizes de placar) × observado: médias, dispersão, contagens, linhas e placares."""
    home_goals = test_features["home_goals"].to_numpy(dtype=np.int64)
    away_goals = test_features["away_goals"].to_numpy(dtype=np.int64)
    total_goals = home_goals + away_goals
    goals = np.arange(matrices.shape[-1])
    home_pmf, away_pmf = matrices.sum(axis=2), matrices.sum(axis=1)
    total_pmf = total_goals_probabilities(matrices)
    totals_grid = np.arange(total_pmf.shape[1])
    summary: dict[str, Any] = {"n_matches": len(home_goals)}
    means: dict[str, Any] = {}
    variances: dict[str, Any] = {}
    pearson: dict[str, float] = {}
    for name, pmf, grid, observed in (
        ("home", home_pmf, goals, home_goals),
        ("away", away_pmf, goals, away_goals),
        ("total", total_pmf, totals_grid, total_goals),
    ):
        match_mean = pmf @ grid
        match_variance = pmf @ grid**2 - match_mean**2
        means[name] = _predicted_observed(match_mean, observed)
        variances[name] = {
            "predicted": float(np.mean(match_variance + match_mean**2) - np.mean(match_mean) ** 2),
            "observed": float(np.var(observed)),
        }
        pearson[name] = float(np.mean((observed - match_mean) ** 2 / match_variance))
    summary["mean_goals"] = means
    summary["variance"] = variances
    summary["pearson_dispersion"] = pearson
    summary["goals_per_team"] = {
        "home": _count_buckets(home_pmf, home_goals),
        "away": _count_buckets(away_pmf, away_goals),
    }
    summary["total_goals"] = _count_buckets(total_pmf, total_goals)
    summary["over"] = {
        str(line): _predicted_observed(total_pmf[:, int(np.ceil(line)) :].sum(axis=1), total_goals > line)
        for line in TOTAL_GOAL_LINES
    }
    summary["scores"] = {
        f"{home}-{away}": _predicted_observed(matrices[:, home, away], (home_goals == home) & (away_goals == away))
        for home, away in DIAGNOSTIC_SCORES
    }
    summary["draw"] = _predicted_observed(np.trace(matrices, axis1=1, axis2=2), home_goals == away_goals)
    flat_mode = matrices.reshape(len(matrices), -1).argmax(axis=1)
    mode_labels = pd.Series([f"{index // len(goals)}-{index % len(goals)}" for index in flat_mode])
    summary["most_likely_score_share"] = {
        str(label): float(share) for label, share in mode_labels.value_counts(normalize=True).items()
    }
    return summary


def goal_distribution_diagnostic(
    features: pd.DataFrame,
    seasons: Iterable[int],
    feature_set: str,
    window: int = 10,
    first_season: int = 2006,
    goal_dispersion: bool = False,
) -> dict[str, Any]:
    """Distribuição de gols prevista fora da amostra (treino só com temporadas anteriores) × observada."""
    matrices: list[np.ndarray] = []
    tests: list[pd.DataFrame] = []
    for season in seasons:
        test = features[features["season"] == season]
        if test.empty:
            continue
        training = training_window(features, season, window, first_season)
        model = GoalsModel.fit(training, feature_set, goal_dispersion=goal_dispersion)
        matrices.append(model.score_probabilities(test))
        tests.append(test)
    return goal_distribution_summary(np.concatenate(matrices), pd.concat(tests, ignore_index=True))


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
    goal_dispersion: bool = False


DYNAMIC_VS_FIXED = (SimulationVariant("dinamico", True), SimulationVariant("fixo", False))


@dataclass(frozen=True)
class PreparedCheckpoint:
    checkpoint: SeasonCheckpoint
    state: RatingState
    season_matches: pd.DataFrame
    rules: SeasonRules
    models: dict[tuple[bool, bool], GoalsModel]
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
    """Estado, modelos (chave: inflação de empates, dispersão dos gols) e resultado real de cada checkpoint.

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
                    (inflation, dispersion): GoalsModel.fit(
                        training, feature_set, draw_inflation=inflation, goal_dispersion=dispersion
                    )
                    for inflation, dispersion in product((False, True), (False, True))
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
                item.models[(variant.draw_inflation, variant.goal_dispersion)],
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
