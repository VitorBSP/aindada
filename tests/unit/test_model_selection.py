"""Regras de seleção do relatório de backtesting (Agente 06)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brasileirao.config import SimulationUncertainty
from brasileirao.pipeline import load_model_config
from brasileirao.validation.report import (
    SIMULATION_METRIC_NAMES,
    rolling_origin_selection,
    rolling_origin_summary,
    select_with_parsimony,
    uncertainty_candidates,
)


def test_parsimony_prefers_simpler_within_tolerance() -> None:
    chosen = select_with_parsimony({"simples": 2.2610, "complexo": 2.2605}, {"simples": 0, "complexo": 1})
    assert chosen == "simples"


def test_parsimony_accepts_complex_beyond_tolerance() -> None:
    chosen = select_with_parsimony({"simples": 2.2650, "complexo": 2.2600}, {"simples": 0, "complexo": 1})
    assert chosen == "complexo"


def test_uncertainty_candidates_start_without_uncertainty() -> None:
    first_variant, complexity = uncertainty_candidates(True, False)[0]
    assert (first_variant.uncertainty, complexity) == (SimulationUncertainty(), 0.0)


def test_model_config_without_new_fields_defaults_to_no_uncertainty(tmp_path: Path) -> None:
    payload = {"feature_set": "elo_only", "rating_params": {"elo": {}, "attack_defense": {}, "form": {}}}
    (tmp_path / "model_config.json").write_text(json.dumps(payload), encoding="utf-8")
    assert load_model_config(tmp_path).uncertainty == SimulationUncertainty()


def test_model_config_reads_simulation_uncertainty(tmp_path: Path) -> None:
    payload = {
        "feature_set": "elo_only",
        "rating_params": {"elo": {}, "attack_defense": {}, "form": {}},
        "draw_inflation": True,
        "simulation_uncertainty": {"coefficient_draws": False, "strength_sd": 0.05},
    }
    (tmp_path / "model_config.json").write_text(json.dumps(payload), encoding="utf-8")
    assert load_model_config(tmp_path).uncertainty.strength_sd == 0.05


COMPLEXITY = {"base": 0.0, "extra": 1.0}


def _records(losses: dict[int, dict[str, float]]) -> list[dict[str, float | int | str]]:
    return [
        {"season": season, "variant": variant, **dict.fromkeys(SIMULATION_METRIC_NAMES, 0.0), "position_log_loss": loss}
        for season, by_variant in losses.items()
        for variant, loss in by_variant.items()
    ]


def test_rolling_origin_ignores_target_season() -> None:
    losses = {2010: {"base": 2.0, "extra": 2.1}, 2011: {"base": 2.0, "extra": 2.1}, 2012: {"base": 9.0, "extra": 1.0}}
    assert rolling_origin_selection(_records(losses), [2012], COMPLEXITY, lookback=2) == {2012: "base"}


def test_rolling_origin_follows_recent_window() -> None:
    losses = {2010: {"base": 2.0, "extra": 2.1}, 2011: {"base": 2.2, "extra": 2.0}, 2012: {"base": 2.2, "extra": 2.0}}
    assert rolling_origin_selection(_records(losses), [2013], COMPLEXITY, lookback=2) == {2013: "extra"}


def test_rolling_origin_requires_full_window() -> None:
    with pytest.raises(ValueError):
        rolling_origin_selection(_records({2011: {"base": 2.0, "extra": 2.1}}), [2012], COMPLEXITY, lookback=2)


def test_rolling_origin_summary_uses_choice_per_season() -> None:
    losses = {2012: {"base": 2.0, "extra": 3.0}, 2013: {"base": 5.0, "extra": 4.0}}
    summary = rolling_origin_summary(_records(losses), {2012: "base", 2013: "extra"})
    assert summary["position_log_loss"] == pytest.approx(3.0)
