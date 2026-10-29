"""Backtesting temporal da Série B com os hiperparâmetros da Série A (ADR-0010, Decisão 3).

Partidas: walk-forward por temporada contra a taxa base. Temporadas: checkpoints em rodadas fixas,
pontuando "4 primeiros" (acesso direto em 2021–2025) e rebaixamento. 2025 usa as datas do calendário
do openfootball (aproximadas).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from brasileirao.pipeline import ModelConfig
from brasileirao.serie_b.forecast import SERIE_B_MODEL_VERSION, SERIE_B_TRAINING
from brasileirao.serie_b.rules import SerieBRules
from brasileirao.validation.backtest import (
    SimulationVariant,
    compute_features,
    evaluate_predictions,
    season_simulation_backtest,
    walk_forward_predictions,
)

TEST_SEASONS = (2021, 2022, 2023, 2024, 2025)
CHECKPOINT_ROUNDS = (19, 28, 33)
SEASON_METRICS = ("top4_brier", "relegation_brier", "position_log_loss", "points_mae", "points_interval_90_coverage")


def _climatology_brier(share: float) -> float:
    return share * (1 - share)


def run_backtest(
    matches_data: pd.DataFrame,
    rules: SerieBRules,
    model_config: ModelConfig,
    n_simulations: int = 2000,
    seed: int = 7,
) -> dict[str, Any]:
    history = matches_data[matches_data["season"] < rules.season]
    features = compute_features(history, model_config.rating_params)
    window, first = SERIE_B_TRAINING.training_seasons_window, SERIE_B_TRAINING.first_training_season
    match_metrics = {}
    for feature_set in ("base_rate", model_config.feature_set):
        predictions = walk_forward_predictions(
            features, TEST_SEASONS, feature_set, window, first, goal_dispersion=model_config.goal_dispersion
        )
        match_metrics[feature_set] = asdict(evaluate_predictions(predictions))
        match_metrics[feature_set]["by_season"] = {
            str(season): asdict(evaluate_predictions(predictions[predictions["season"] == season]))["log_loss"]
            for season in TEST_SEASONS
        }
    variant = SimulationVariant(
        "fixo", model_config.dynamic_ratings, model_config.draw_inflation, model_config.uncertainty,
        model_config.goal_dispersion,
    )  # fmt: skip
    records = season_simulation_backtest(
        history,
        model_config.rating_params,
        rules.league_rules(),
        TEST_SEASONS,
        CHECKPOINT_ROUNDS,
        model_config.feature_set,
        n_simulations=n_simulations,
        seed=seed,
        window=window,
        variants=(variant,),
    )
    season_records = pd.DataFrame.from_records(records)
    by_round = {
        str(round_number): {metric: float(group[metric].mean()) for metric in SEASON_METRICS}
        for round_number, group in season_records.groupby("round")
    }
    share = 4 / rules.n_clubs
    return {
        "model_version": SERIE_B_MODEL_VERSION,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "feature_set": model_config.feature_set,
        "test_seasons": list(TEST_SEASONS),
        "training": {"window": window, "first_season": first},
        "match_level": match_metrics,
        "season_level": {
            "rounds": list(CHECKPOINT_ROUNDS),
            "n_simulations": n_simulations,
            "seed": seed,
            "by_round": by_round,
            "climatology_brier_top4_or_bottom4": _climatology_brier(share),
            "n_checkpoints": len(season_records),
        },
    }


def backtest_summary(report: dict[str, Any]) -> dict[str, object]:
    """Resumo exibido no site: só agregados, sem clubes nem jogos."""
    model = report["match_level"][report["feature_set"]]
    base = report["match_level"]["base_rate"]
    late = report["season_level"]["by_round"][str(max(report["season_level"]["rounds"]))]
    return {
        "test_seasons": report["test_seasons"],
        "n_matches": int(model["n_matches"]),
        "log_loss": float(model["log_loss"]),
        "log_loss_base_rate": float(base["log_loss"]),
        "rps": float(model["rps"]),
        "rps_base_rate": float(base["rps"]),
        "late_round": max(report["season_level"]["rounds"]),
        "late_top4_brier": float(late["top4_brier"]),
        "late_relegation_brier": float(late["relegation_brier"]),
        "late_points_interval_90_coverage": float(late["points_interval_90_coverage"]),
        "climatology_brier": float(report["season_level"]["climatology_brier_top4_or_bottom4"]),
        "generated_at": str(report["generated_at"]),
        "model_version": str(report["model_version"]),
        "mean_position_log_loss": float(
            np.mean([v["position_log_loss"] for v in report["season_level"]["by_round"].values()])
        ),
    }
