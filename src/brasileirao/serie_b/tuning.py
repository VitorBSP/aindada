"""Hiperparâmetros próprios da Série B (pendência do 02 no ADR-0010).

Mesmo protocolo da Série A (ADR-0006): tudo é escolhido nas temporadas de validação e só relatado nas de
teste. Os ratings vêm da busca coordenada da Série A; a incerteza da simulação, da mesma grade de força
latente, escolhida pelo log loss da posição final com parcimônia.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from brasileirao.config import RatingParams
from brasileirao.pipeline import ModelConfig
from brasileirao.serie_b.forecast import SERIE_B_TRAINING
from brasileirao.serie_b.rules import SerieBRules
from brasileirao.validation.backtest import (
    MatchMetrics,
    compute_features,
    evaluate_predictions,
    prepare_checkpoints,
    score_simulation_variants,
    tune_rating_params,
    walk_forward_predictions,
)
from brasileirao.validation.report import (
    SIMULATION_METRIC_NAMES,
    rating_params_to_dict,
    select_with_parsimony,
    summarize_variants,
    uncertainty_candidates,
)

VALIDATION_SEASONS = (2020, 2021, 2022)
TEST_SEASONS = (2023, 2024, 2025)
CHECKPOINT_ROUNDS = (19, 28, 33)


def _match_metrics(
    history: pd.DataFrame, params: RatingParams, seasons: tuple[int, ...], config: ModelConfig
) -> MatchMetrics:
    features = compute_features(history, params)
    predictions = walk_forward_predictions(
        features,
        seasons,
        config.feature_set,
        SERIE_B_TRAINING.training_seasons_window,
        SERIE_B_TRAINING.first_training_season,
        goal_dispersion=config.goal_dispersion,
    )
    return evaluate_predictions(predictions)


def _season_records(
    history: pd.DataFrame,
    params: RatingParams,
    rules: SerieBRules,
    seasons: tuple[int, ...],
    config: ModelConfig,
    n_simulations: int,
    seed: int,
) -> list[dict[str, Any]]:
    prepared = prepare_checkpoints(
        history, params, rules.league_rules(), seasons, CHECKPOINT_ROUNDS, config.feature_set
    )
    variants = [variant for variant, _ in uncertainty_candidates(False, False, config.goal_dispersion)]
    return score_simulation_variants(prepared, params, variants, n_simulations, seed)


def run_tuning(
    matches_data: pd.DataFrame,
    rules: SerieBRules,
    serie_a_config: ModelConfig,
    n_simulations: int = 2000,
    seed: int = 7,
) -> dict[str, Any]:
    history = matches_data[matches_data["season"] < rules.season]
    tuned_params, tuning_records = tune_rating_params(history, VALIDATION_SEASONS)
    candidates = {"serie_a": serie_a_config.rating_params, "serie_b": tuned_params}
    match_level = {
        name: {
            "validation": asdict(_match_metrics(history, params, VALIDATION_SEASONS, serie_a_config)),
            "test": asdict(_match_metrics(history, params, TEST_SEASONS, serie_a_config)),
        }
        for name, params in candidates.items()
    }
    chosen_params_name = select_with_parsimony(
        {name: metrics["validation"]["log_loss"] for name, metrics in match_level.items()},
        {"serie_a": 0.0, "serie_b": 1.0},
    )
    chosen_params = candidates[chosen_params_name]

    complexity = {variant.name: weight for variant, weight in uncertainty_candidates(False, False, True)}
    validation_records = _season_records(
        history, chosen_params, rules, VALIDATION_SEASONS, serie_a_config, n_simulations, seed
    )
    test_records = _season_records(history, chosen_params, rules, TEST_SEASONS, serie_a_config, n_simulations, seed)
    validation_summary = summarize_variants(validation_records)
    chosen_variant_name = select_with_parsimony(
        {name: metrics["position_log_loss"] for name, metrics in validation_summary.items()}, complexity
    )
    chosen_variant = next(
        variant
        for variant, _ in uncertainty_candidates(False, False, serie_a_config.goal_dispersion)
        if variant.name == chosen_variant_name
    )
    by_round = {
        str(round_number): {metric: float(group[metric].mean()) for metric in SIMULATION_METRIC_NAMES}
        for round_number, group in pd.DataFrame(test_records).query("variant == @chosen_variant_name").groupby("round")
    }
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "protocol": "escolha na validação, teste só relatado (ADR-0006)",
        "validation_seasons": list(VALIDATION_SEASONS),
        "test_seasons": list(TEST_SEASONS),
        "feature_set": serie_a_config.feature_set,
        "goal_dispersion": serie_a_config.goal_dispersion,
        "rating_params_candidates": {name: rating_params_to_dict(params) for name, params in candidates.items()},
        "match_level": match_level,
        "chosen_rating_params": chosen_params_name,
        "n_tuning_candidates": len(tuning_records),
        "season_level": {
            "rounds": list(CHECKPOINT_ROUNDS),
            "n_simulations": n_simulations,
            "seed": seed,
            "validation": validation_summary,
            "test": summarize_variants(test_records),
            "test_by_round_chosen": by_round,
        },
        "chosen_uncertainty": chosen_variant_name,
        "model_config": {
            "model_version_base": "cmp-elo-ad-0.3.0",
            "feature_set": serie_a_config.feature_set,
            "rating_params": rating_params_to_dict(chosen_params),
            "dynamic_ratings_in_simulation": False,
            "draw_inflation": False,
            "goal_dispersion": serie_a_config.goal_dispersion,
            "simulation_uncertainty": asdict(chosen_variant.uncertainty),
            "source_report": "serie_b_tuning_report.json",
        },
    }
