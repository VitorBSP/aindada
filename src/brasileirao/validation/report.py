"""Relatório de backtesting e seleção de modelo (Agente 06)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.config import (
    MODEL_VERSION,
    AttackDefenseParams,
    EloParams,
    FormParams,
    RatingParams,
    SimulationUncertainty,
)
from brasileirao.frame_values import as_int
from brasileirao.logging_utils import get_logger
from brasileirao.validation.backtest import (
    DYNAMIC_VS_FIXED,
    PreparedCheckpoint,
    SimulationVariant,
    calibration_report,
    compute_features,
    evaluate_predictions,
    prepare_checkpoints,
    score_simulation_variants,
    tune_rating_params,
    walk_forward_predictions,
)

LOGGER = get_logger(__name__)

VALIDATION_SEASONS = tuple(range(2013, 2019))
TEST_SEASONS = tuple(range(2019, 2026))
CANDIDATE_FEATURE_SETS = ("elo_only", "attack_defense_only", "elo_attack_defense", "full")
BENCHMARKS = ("base_rate", "intercept_only")
PARSIMONY_TOLERANCE = 0.001
FEATURE_SET_COMPLEXITY = {"elo_only": 1, "attack_defense_only": 1, "elo_attack_defense": 2, "full": 3}
STRENGTH_SD_GRID = (0.025, 0.05, 0.075, 0.1)
ROLLING_LOOKBACK = 6
SIMULATION_METRIC_NAMES = (
    "title_brier",
    "top4_brier",
    "relegation_brier",
    "position_log_loss",
    "points_mae",
    "points_interval_90_coverage",
)


def select_with_parsimony(losses: dict[str, float], complexity: dict[str, float]) -> str:
    """Menor perda; entre candidatos a até 0,001 da melhor, o mais simples."""
    best_loss = min(losses.values())
    eligible = [name for name, loss in losses.items() if loss <= best_loss + PARSIMONY_TOLERANCE]
    return min(eligible, key=lambda name: (complexity[name], losses[name]))


def select_feature_set(validation_losses: dict[str, float]) -> str:
    return select_with_parsimony(validation_losses, {name: FEATURE_SET_COMPLEXITY[name] for name in validation_losses})


def uncertainty_candidates(dynamic: bool, draw_inflation: bool) -> list[tuple[SimulationVariant, float]]:
    """Variantes de incerteza e sua complexidade (nenhuma < coeficientes < força latente crescente)."""
    candidates = [
        (SimulationVariant("sem_incerteza", dynamic, draw_inflation), 0.0),
        (
            SimulationVariant("coeficientes", dynamic, draw_inflation, SimulationUncertainty(coefficient_draws=True)),
            1.0,
        ),
    ]
    for position, strength_sd in enumerate(STRENGTH_SD_GRID, start=2):
        uncertainty = SimulationUncertainty(strength_sd=strength_sd)
        candidates.append(
            (SimulationVariant(f"forca_sd_{strength_sd}", dynamic, draw_inflation, uncertainty), position)
        )
    return candidates


def rolling_origin_selection(
    records: list[dict[str, Any]],
    target_seasons: Sequence[int],
    complexity: dict[str, float],
    lookback: int = ROLLING_LOOKBACK,
) -> dict[int, str]:
    """Para cada temporada-alvo, a variante com menor log loss de posição nas `lookback` anteriores."""
    season_losses = pd.DataFrame(records).groupby(["season", "variant"])["position_log_loss"].mean()
    available = {as_int(season) for season in season_losses.index.get_level_values("season")}
    choices: dict[int, str] = {}
    for target in target_seasons:
        window = list(range(target - lookback, target))
        missing = [season for season in window if season not in available]
        if missing:
            raise ValueError(f"temporadas sem registros para a origem móvel de {target}: {missing}")
        window_losses = season_losses.loc[window].groupby(level="variant").mean()
        choices[target] = select_with_parsimony(
            {str(name): float(loss) for name, loss in window_losses.items()}, complexity
        )
    return choices


def rolling_origin_summary(records: list[dict[str, Any]], choices: dict[int, str]) -> dict[str, float]:
    """Métricas no teste usando, em cada temporada, a variante escolhida pela origem móvel."""
    frame = pd.DataFrame(records)
    chosen_rows = frame[frame["variant"] == frame["season"].map(choices)]
    return {metric: float(chosen_rows[metric].mean()) for metric in SIMULATION_METRIC_NAMES}


def summarize_variants(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    means = pd.DataFrame(records).groupby("variant")[list(SIMULATION_METRIC_NAMES)].mean()
    return {
        str(name): {metric: float(row[metric]) for metric in SIMULATION_METRIC_NAMES} for name, row in means.iterrows()
    }


def rating_params_to_dict(params: RatingParams) -> dict[str, Any]:
    return asdict(params)


def rating_params_from_dict(payload: dict[str, Any]) -> RatingParams:
    return RatingParams(
        elo=EloParams(**payload["elo"]),
        attack_defense=AttackDefenseParams(**payload["attack_defense"]),
        form=FormParams(**payload["form"]),
    )


def run_backtest_report(
    matches_data: pd.DataFrame,
    rules_template: SeasonRules,
    output_dir: Path,
    simulation_rounds: tuple[int, ...] = (10, 19, 28),
    n_simulations: int = 2000,
) -> dict[str, Any]:
    tuned_params, tuning_records = tune_rating_params(matches_data, VALIDATION_SEASONS)
    features = compute_features(matches_data, tuned_params)

    validation_losses = {
        feature_set: evaluate_predictions(walk_forward_predictions(features, VALIDATION_SEASONS, feature_set)).log_loss
        for feature_set in CANDIDATE_FEATURE_SETS
    }
    chosen_feature_set = select_feature_set(validation_losses)

    test_metrics: dict[str, Any] = {}
    for feature_set in (*BENCHMARKS, *CANDIDATE_FEATURE_SETS):
        predictions = walk_forward_predictions(features, TEST_SEASONS, feature_set)
        test_metrics[feature_set] = asdict(evaluate_predictions(predictions))
    no_dixon_coles = walk_forward_predictions(features, TEST_SEASONS, chosen_feature_set, dixon_coles=False)
    test_metrics[f"{chosen_feature_set}_sem_dixon_coles"] = asdict(evaluate_predictions(no_dixon_coles))
    chosen_predictions = walk_forward_predictions(features, TEST_SEASONS, chosen_feature_set)
    per_season = {
        as_int(season): asdict(evaluate_predictions(season_predictions))
        for season, season_predictions in chosen_predictions.groupby("season")
    }
    predicted_draw_rate = float(chosen_predictions["p_draw"].mean())
    observed_draw_rate = float((chosen_predictions["home_goals"] == chosen_predictions["away_goals"]).mean())

    inflated_validation = walk_forward_predictions(
        features, VALIDATION_SEASONS, chosen_feature_set, draw_inflation=True
    )
    inflated_test = walk_forward_predictions(features, TEST_SEASONS, chosen_feature_set, draw_inflation=True)
    test_metrics[f"{chosen_feature_set}_inflacao_empates"] = asdict(evaluate_predictions(inflated_test))
    inflation_match_validation = {
        "sem_inflacao": validation_losses[chosen_feature_set],
        "inflacao_empates": evaluate_predictions(inflated_validation).log_loss,
    }
    predicted_draw_rate_inflated = float(inflated_test["p_draw"].mean())

    validation_checkpoints = prepare_checkpoints(
        matches_data, tuned_params, rules_template, VALIDATION_SEASONS, simulation_rounds, chosen_feature_set
    )
    test_checkpoints = prepare_checkpoints(
        matches_data, tuned_params, rules_template, TEST_SEASONS, simulation_rounds, chosen_feature_set
    )

    def score(checkpoints: Sequence[PreparedCheckpoint], variants: Sequence[SimulationVariant]) -> list[dict[str, Any]]:
        return score_simulation_variants(checkpoints, tuned_params, variants, n_simulations)

    simulation_records = score(test_checkpoints, DYNAMIC_VS_FIXED)
    simulation_summary = (
        pd.DataFrame(simulation_records)
        .groupby(["dynamic_ratings", "round"])
        .mean(numeric_only=True)
        .drop(columns=["season"])
        .reset_index()
        .to_dict(orient="records")
    )
    test_dynamic_vs_fixed = summarize_variants(simulation_records)
    validation_dynamic_vs_fixed = summarize_variants(score(validation_checkpoints, DYNAMIC_VS_FIXED))
    use_dynamic_ratings = bool(
        validation_dynamic_vs_fixed["dinamico"]["position_log_loss"]
        <= validation_dynamic_vs_fixed["fixo"]["position_log_loss"]
    )

    inflation_variants = [
        SimulationVariant("sem_inflacao", use_dynamic_ratings, False),
        SimulationVariant("inflacao_empates", use_dynamic_ratings, True),
    ]
    inflation_validation = summarize_variants(score(validation_checkpoints, inflation_variants))
    inflation_test = summarize_variants(score(test_checkpoints, inflation_variants))
    use_draw_inflation = bool(
        inflation_match_validation["inflacao_empates"]
        <= inflation_match_validation["sem_inflacao"] + PARSIMONY_TOLERANCE
        and inflation_validation["inflacao_empates"]["position_log_loss"]
        < inflation_validation["sem_inflacao"]["position_log_loss"] - PARSIMONY_TOLERANCE
    )

    candidates = uncertainty_candidates(use_dynamic_ratings, use_draw_inflation)
    candidate_variants = [variant for variant, _ in candidates]
    uncertainty_validation_records = score(validation_checkpoints, candidate_variants)
    uncertainty_test_records = score(test_checkpoints, candidate_variants)
    uncertainty_validation = summarize_variants(uncertainty_validation_records)
    uncertainty_test = summarize_variants(uncertainty_test_records)
    candidate_complexity = {variant.name: complexity for variant, complexity in candidates}
    all_uncertainty_records = uncertainty_validation_records + uncertainty_test_records
    rolling_choices = rolling_origin_selection(all_uncertainty_records, TEST_SEASONS, candidate_complexity)
    next_season = max(TEST_SEASONS) + 1
    rolling_next_choice = rolling_origin_selection(all_uncertainty_records, [next_season], candidate_complexity)
    chosen_uncertainty_name = select_with_parsimony(
        {name: metrics["position_log_loss"] for name, metrics in uncertainty_validation.items()},
        candidate_complexity,
    )
    chosen_uncertainty = next(variant for variant in candidate_variants if variant.name == chosen_uncertainty_name)

    report: dict[str, Any] = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "model_version": MODEL_VERSION,
        "validation_seasons": list(VALIDATION_SEASONS),
        "test_seasons": list(TEST_SEASONS),
        "tuned_rating_params": rating_params_to_dict(tuned_params),
        "validation_log_loss": validation_losses,
        "chosen_feature_set": chosen_feature_set,
        "selection_rule": "menor log loss em validação; empate técnico (<=0,001) favorece o modelo mais simples",
        "test_metrics": test_metrics,
        "test_metrics_by_season": per_season,
        "draw_rate": {
            "predicted": predicted_draw_rate_inflated if use_draw_inflation else predicted_draw_rate,
            "observed": observed_draw_rate,
            "predicted_without_inflation": predicted_draw_rate,
            "predicted_with_inflation": predicted_draw_rate_inflated,
        },
        "calibration": calibration_report(chosen_predictions),
        "season_simulation": {
            "rounds": list(simulation_rounds),
            "n_simulations": n_simulations,
            "summary_by_round": simulation_summary,
            "overall": {"dynamic": test_dynamic_vs_fixed["dinamico"], "fixed": test_dynamic_vs_fixed["fixo"]},
            "validation_overall": {
                "dynamic": validation_dynamic_vs_fixed["dinamico"],
                "fixed": validation_dynamic_vs_fixed["fixo"],
            },
            "dynamic_selected_on": "validation_seasons (log loss da posição final)",
            "draw_inflation": {
                "match_validation_log_loss": inflation_match_validation,
                "validation": inflation_validation,
                "test": inflation_test,
                "selected": use_draw_inflation,
                "selection_rule": (
                    "log loss de partidas na validação não piora mais que 0,001 e log loss da posição final "
                    "na validação melhora mais que 0,001"
                ),
            },
            "uncertainty": {
                "validation": uncertainty_validation,
                "test": uncertainty_test,
                "selected": chosen_uncertainty_name,
                "selection_rule": (
                    "menor log loss da posição final na validação; empate técnico (<=0,001) favorece o mais simples"
                ),
                "common_random_numbers": True,
                "rolling_origin": {
                    "lookback_seasons": ROLLING_LOOKBACK,
                    "selection_rule": (
                        "para cada temporada, menor log loss da posição final nas 6 temporadas anteriores; "
                        "empate técnico (<=0,001) favorece o mais simples"
                    ),
                    "choices": rolling_choices,
                    "test": rolling_origin_summary(uncertainty_test_records, rolling_choices),
                    "next_season_choice": rolling_next_choice,
                    "by_season_test": {
                        str(season): {
                            str(variant): float(loss)
                            for variant, loss in season_frame.groupby("variant")["position_log_loss"].mean().items()
                        }
                        for season, season_frame in pd.DataFrame(uncertainty_test_records).groupby("season")
                    },
                },
            },
            "records": simulation_records,
        },
        "tuning_records": tuning_records,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "backtest_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8"
    )
    (output_dir / "model_config.json").write_text(
        json.dumps(
            {
                "model_version": MODEL_VERSION,
                "feature_set": chosen_feature_set,
                "rating_params": rating_params_to_dict(tuned_params),
                "dynamic_ratings_in_simulation": use_dynamic_ratings,
                "draw_inflation": use_draw_inflation,
                "simulation_uncertainty": asdict(chosen_uncertainty.uncertainty),
                "source_report": "backtest_report.json",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    LOGGER.info("backtest_report_written", extra={"chosen": chosen_feature_set})
    return report


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return str(value)
