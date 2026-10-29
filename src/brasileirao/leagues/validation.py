"""Calibração e backtest das ligas europeias (ADR-0011, Decisão 3), com o protocolo do ADR-0006.

Validação: as três temporadas antes das de teste; teste: as três anteriores à corrente. Tudo é escolhido
na validação; o teste só é relatado e alimenta o resumo exibido no site. O backtest por temporada usa a
ordenação da Série A (pontos, vitórias, saldo, gols): só empates exatos mudam, o que pouco afeta as métricas.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from brasileirao.config import MODEL_VERSION, RatingParams
from brasileirao.leagues.forecast import training_config
from brasileirao.leagues.rules import LeagueRules
from brasileirao.pipeline import ModelConfig
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

CHECKPOINT_ROUNDS = (10, 19, 28)


def split_seasons(current_season: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    test = tuple(range(current_season - 3, current_season))
    validation = tuple(range(current_season - 6, current_season - 3))
    return validation, test


def _match_metrics(
    history: pd.DataFrame,
    params: RatingParams,
    seasons: tuple[int, ...],
    config: ModelConfig,
    feature_set: str,
    first_history_season: int,
) -> MatchMetrics:
    training = training_config(first_history_season)
    predictions = walk_forward_predictions(
        compute_features(history, params),
        seasons,
        feature_set,
        training.training_seasons_window,
        training.first_training_season,
        goal_dispersion=config.goal_dispersion,
    )
    return evaluate_predictions(predictions)


def run_tuning(
    matches_data: pd.DataFrame,
    rules: LeagueRules,
    serie_a_config: ModelConfig,
    first_history_season: int,
    model_version: str,
    n_simulations: int = 2000,
    seed: int = 7,
) -> dict[str, Any]:
    history = matches_data[matches_data["season"] < rules.season]
    validation, test = split_seasons(rules.season)
    tuned_params, tuning_records = tune_rating_params(history, validation)
    candidates = {"serie_a": serie_a_config.rating_params, "liga": tuned_params}
    feature_set = serie_a_config.feature_set
    match_level = {
        name: {
            period: asdict(_match_metrics(history, params, seasons, serie_a_config, feature_set, first_history_season))
            for period, seasons in (("validation", validation), ("test", test))
        }
        for name, params in candidates.items()
    }
    chosen_name = select_with_parsimony(
        {name: metrics["validation"]["log_loss"] for name, metrics in match_level.items()},
        {"serie_a": 0.0, "liga": 1.0},
    )
    chosen_params = candidates[chosen_name]
    variants = uncertainty_candidates(False, False, serie_a_config.goal_dispersion)
    complexity = {variant.name: weight for variant, weight in variants}

    def season_records(seasons: tuple[int, ...]) -> list[dict[str, Any]]:
        prepared = prepare_checkpoints(
            history, chosen_params, rules.league_rules(), seasons, CHECKPOINT_ROUNDS, feature_set
        )
        return score_simulation_variants(
            prepared, chosen_params, [variant for variant, _ in variants], n_simulations, seed
        )

    validation_summary = summarize_variants(season_records(validation))
    test_records = season_records(test)
    chosen_variant_name = select_with_parsimony(
        {name: metrics["position_log_loss"] for name, metrics in validation_summary.items()}, complexity
    )
    chosen_variant = next(variant for variant, _ in variants if variant.name == chosen_variant_name)
    chosen_rows = pd.DataFrame(test_records).query("variant == @chosen_variant_name")
    by_round = {
        str(round_number): {metric: float(group[metric].mean()) for metric in SIMULATION_METRIC_NAMES}
        for round_number, group in chosen_rows.groupby("round")
    }
    base_rate_test = asdict(
        _match_metrics(history, chosen_params, test, serie_a_config, "base_rate", first_history_season)
    )
    return {
        "competition": rules.code,
        "model_version": model_version,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "protocol": "escolha na validação, teste só relatado (ADR-0006)",
        "validation_seasons": list(validation),
        "test_seasons": list(test),
        "rating_params_candidates": {name: rating_params_to_dict(params) for name, params in candidates.items()},
        "match_level": match_level,
        "base_rate_test": base_rate_test,
        "chosen_rating_params": chosen_name,
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
            "model_version": model_version,
            "model_version_base": MODEL_VERSION,
            "feature_set": feature_set,
            "rating_params": rating_params_to_dict(chosen_params),
            "dynamic_ratings_in_simulation": False,
            "draw_inflation": False,
            "goal_dispersion": serie_a_config.goal_dispersion,
            "simulation_uncertainty": asdict(chosen_variant.uncertainty),
        },
    }


def backtest_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Resumo exibido no site: só agregados do teste, sem clubes nem jogos."""
    chosen = report["chosen_rating_params"]
    model = report["match_level"][chosen]["test"]
    base = report["base_rate_test"]
    rounds = report["season_level"]["test_by_round_chosen"]
    late_round = max(int(round_number) for round_number in rounds)
    late = rounds[str(late_round)]
    return {
        "model_version": report["model_version"],
        "test_seasons": report["test_seasons"],
        "n_matches": int(model["n_matches"]),
        "log_loss": float(model["log_loss"]),
        "log_loss_base_rate": float(base["log_loss"]),
        "rps": float(model["rps"]),
        "rps_base_rate": float(base["rps"]),
        "late_round": late_round,
        "late_title_brier": float(late["title_brier"]),
        "late_top4_brier": float(late["top4_brier"]),
        "late_points_interval_90_coverage": float(late["points_interval_90_coverage"]),
        "by_round": rounds,
    }
