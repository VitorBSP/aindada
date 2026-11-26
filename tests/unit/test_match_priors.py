"""Export de probabilidades pré-jogo (point-in-time). Dados SINTÉTICOS (tests/fixtures/synthetic.py)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from brasileirao import cli
from brasileirao.config import ModelTrainingConfig, RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.exports.match_priors import (
    COLUMNS,
    MODEL_COLUMNS,
    ExportError,
    PriorInputs,
    build_match_priors,
    export_match_priors,
    manifest_path_for,
    market_probabilities,
    point_in_time_view,
    round_cutoffs,
    validate_match_priors,
)
from brasileirao.pipeline import ModelConfig
from brasileirao.prediction.goals_model import GoalsModel, score_matrix
from brasileirao.provenance import ProvenanceError
from brasileirao.ratings.history import build_state_as_of
from brasileirao.validation.backtest import training_window
from tests.fixtures.synthetic import SYNTHETIC_SOURCE

SEASONS = [2031, 2032]
TRAINING = ModelTrainingConfig(first_training_season=2030)
CONFIG = ModelConfig("elo_attack_defense", RatingParams(), dynamic_ratings=False, goal_dispersion=True)


@pytest.fixture(scope="module")
def priors_inputs(synthetic_matches: pd.DataFrame, synthetic_registry: ClubRegistry) -> PriorInputs:
    return PriorInputs(synthetic_matches, synthetic_registry, CONFIG, TRAINING)


@pytest.fixture(scope="module")
def priors(priors_inputs: PriorInputs) -> pd.DataFrame:
    return build_match_priors(priors_inputs, SEASONS)


def _round_frame(frame: pd.DataFrame, season: int, round_number: int) -> pd.DataFrame:
    selected = frame[(frame["season"] == season) & (frame["round"] == round_number)]
    return selected.sort_values("match_id").reset_index(drop=True)


def test_changing_scores_of_round_r_and_later_does_not_change_round_r(
    priors_inputs: PriorInputs, priors: pd.DataFrame
) -> None:
    altered = priors_inputs.matches_data.copy()
    target = (altered["season"] == 2032) & (altered["round"] >= 12) & (altered["status"] == "finished")
    altered.loc[target, "home_goals"] = altered.loc[target, "home_goals"] + 3
    altered.loc[target, "away_goals"] = 0
    altered_priors = build_match_priors(
        PriorInputs(altered, priors_inputs.registry, priors_inputs.model_config, priors_inputs.training), [2032]
    )
    for round_number in (1, 11, 12):
        before = _round_frame(priors, 2032, round_number)[MODEL_COLUMNS]
        after = _round_frame(altered_priors, 2032, round_number)[MODEL_COLUMNS]
        pd.testing.assert_frame_equal(before, after, check_exact=True)


def test_changing_scores_of_round_r_changes_the_following_round(
    priors_inputs: PriorInputs, priors: pd.DataFrame
) -> None:
    altered = priors_inputs.matches_data.copy()
    target = (altered["season"] == 2032) & (altered["round"] == 12) & (altered["status"] == "finished")
    altered.loc[target, "home_goals"] = altered.loc[target, "home_goals"] + 4
    altered_priors = build_match_priors(
        PriorInputs(altered, priors_inputs.registry, priors_inputs.model_config, priors_inputs.training), [2032]
    )
    before = _round_frame(priors, 2032, 13)["home_win_probability"].to_numpy()
    after = _round_frame(altered_priors, 2032, 13)["home_win_probability"].to_numpy()
    assert not np.allclose(before, after)


def test_point_in_time_view_hides_results_after_cutoff(synthetic_matches: pd.DataFrame) -> None:
    view = point_in_time_view(synthetic_matches, date(2032, 6, 1))
    hidden = view[view["match_date"].dt.date > date(2032, 6, 1)]
    assert hidden["home_goals"].isna().all() and (hidden["status"] != "finished").all()


def test_every_match_has_exactly_one_row_per_season(priors: pd.DataFrame, synthetic_matches: pd.DataFrame) -> None:
    expected = synthetic_matches[synthetic_matches["season"].isin(SEASONS)].groupby("season").size().to_dict()
    assert {int(season): int(count) for season, count in priors.groupby("season").size().items()} == expected


def test_schema_columns_and_order(priors: pd.DataFrame) -> None:
    assert list(priors.columns) == COLUMNS


def test_no_nan_in_probabilities_and_expected_goals(priors: pd.DataFrame) -> None:
    assert int(priors[MODEL_COLUMNS].isna().sum().sum()) == 0


def test_outcome_probabilities_sum_to_one(priors: pd.DataFrame) -> None:
    total = priors[["home_win_probability", "draw_probability", "away_win_probability"]].sum(axis=1)
    assert np.allclose(total, 1.0, atol=1e-9)


def test_over_and_under_are_complementary(priors: pd.DataFrame) -> None:
    assert np.allclose(priors["over_2_5_probability"] + priors["under_2_5_probability"], 1.0, atol=1e-12)


def test_scheduled_matches_have_null_scores_never_zero(priors: pd.DataFrame) -> None:
    scheduled = priors[priors["status"] == "scheduled"]
    assert len(scheduled) > 0 and scheduled[["home_score", "away_score"]].isna().all().all()


def test_finished_matches_carry_the_real_score(priors: pd.DataFrame, synthetic_matches: pd.DataFrame) -> None:
    finished = priors[priors["status"] == "finished"].copy()
    finished["source_id"] = (
        finished["season"].astype(str) + "-" + finished["home_club_id"] + "-" + finished["away_club_id"]
    )
    original = synthetic_matches[synthetic_matches["status"] == "finished"].copy()
    original["source_id"] = original["season"].astype(str) + "-" + original["home_id"] + "-" + original["away_id"]
    merged = finished.merge(original, on="source_id")
    assert (merged["home_score"] == merged["home_goals"]).all() and (merged["away_score"] == merged["away_goals"]).all()


def test_match_id_is_stable_season_home_away(priors: pd.DataFrame) -> None:
    row = priors.iloc[0]
    assert row["match_id"] == f"{row['season']}-{row['home_club_id']}-{row['away_club_id']}"


def test_as_of_round_is_zero_in_round_one_and_below_the_round_after(priors: pd.DataFrame) -> None:
    season_priors = priors[priors["season"] == 2032]
    assert (season_priors[season_priors["round"] == 1]["as_of_round"] == 0).all()
    assert (season_priors["as_of_round"] < season_priors["round"]).all()


def test_club_names_come_from_the_reference(priors: pd.DataFrame, synthetic_registry: ClubRegistry) -> None:
    row = priors.iloc[0]
    club = synthetic_registry.clubs[row["home_club_id"]]
    assert (row["home_club_name"], row["home_club_short"]) == (club.display_name, club.short_name)


def test_build_is_deterministic(priors_inputs: PriorInputs, priors: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(build_match_priors(priors_inputs, SEASONS), priors, check_exact=True)


def test_prediction_equals_the_production_engine_path(priors_inputs: PriorInputs, priors: pd.DataFrame) -> None:
    """Mesmo motor: ratings do corte + modelo treinado em temporadas anteriores, sem a máscara do export."""
    season_matches = priors_inputs.matches_data[priors_inputs.matches_data["season"] == 2032]
    cutoff = round_cutoffs(season_matches)[20]
    engine, _ = build_state_as_of(priors_inputs.matches_data, cutoff, 2032, CONFIG.rating_params)
    first_cutoff = round_cutoffs(season_matches)[1]
    _, training_features = build_state_as_of(priors_inputs.matches_data, first_cutoff, 2032, CONFIG.rating_params)
    model = GoalsModel.fit(
        training_window(training_features, 2032, TRAINING.training_seasons_window, TRAINING.first_training_season),
        CONFIG.feature_set,
        alpha=TRAINING.poisson_alpha,
        max_goals=TRAINING.max_goals,
        goal_dispersion=True,
    )
    row = _round_frame(priors, 2032, 20).iloc[0]
    features = pd.DataFrame([engine.pre_match_features(row["home_club_id"], row["away_club_id"])])
    expected = model.outcome_probabilities(features)[0]
    assert np.allclose(
        [row["home_win_probability"], row["draw_probability"], row["away_win_probability"]], expected, atol=1e-12
    )


def test_clean_sheet_and_totals_follow_the_score_matrix() -> None:
    matrix = score_matrix(np.array([1.5]), np.array([1.0]), 0.0, 10)
    markets = market_probabilities(matrix)
    assert markets["home_clean_sheet"][0] == pytest.approx(matrix[0, :, 0].sum())
    assert markets["away_clean_sheet"][0] == pytest.approx(matrix[0, 0, :].sum())
    assert markets["home_clean_sheet"][0] == pytest.approx(np.exp(-1.0), abs=1e-3)
    assert markets["over_1_5"][0] == pytest.approx(1.0 - matrix[0, 0, 0] - matrix[0, 1, 0] - matrix[0, 0, 1])


def test_season_without_history_is_refused(priors_inputs: PriorInputs) -> None:
    with pytest.raises(ExportError, match="sem histórico"):
        build_match_priors(priors_inputs, [2030])


def test_unknown_competition_is_refused(priors_inputs: PriorInputs) -> None:
    with pytest.raises(ExportError, match="competição desconhecida"):
        build_match_priors(priors_inputs, SEASONS, "serie_z")


def test_validation_rejects_nan(priors: pd.DataFrame) -> None:
    broken = priors.copy()
    broken.loc[0, "home_expected_goals"] = np.nan
    with pytest.raises(ExportError, match="NaN"):
        validate_match_priors(broken)


def test_validation_rejects_score_on_scheduled_match(priors: pd.DataFrame) -> None:
    broken = priors.copy()
    position = broken.index[broken["status"] == "scheduled"][0]
    broken.loc[position, "home_score"] = 0
    with pytest.raises(ExportError, match="não encerrada com placar"):
        validate_match_priors(broken)


def test_validation_rejects_wrong_season_count(priors: pd.DataFrame) -> None:
    with pytest.raises(ExportError, match="contagem por temporada"):
        validate_match_priors(priors, expected_per_season=380 + 1)


def _composition(seasons: list[int], source_name: str = SYNTHETIC_SOURCE) -> dict[str, object]:
    return {
        "mode": "publication",
        "seasons": {
            str(season): {"source_name": source_name, "version": "v-sintetica", "n_matches": 380} for season in seasons
        },
        "sources": [
            {
                "source_name": source_name,
                "origin": "sintetico",
                "version": "v-sintetica",
                "license_status": "licensed_with_attribution",
                "allowed_uses": ["research_local", "prototype_local", "public_display_derived"],
                "attribution": "Fixture sintética",
                "seasons": sorted(seasons),
                "manifest": "x/y/manifest.json",
                "manifest_sha256": "0" * 64,
            }
        ],
    }


def _write_workspace(
    root: Path, matches: pd.DataFrame, registry_csv: Path, source_name: str = SYNTHETIC_SOURCE
) -> dict[str, Path]:
    gold, silver = root / "gold", root / "silver"
    gold.mkdir()
    silver.mkdir()
    matches.assign(source=source_name).to_csv(gold / "matches_model.csv", index=False)
    (gold / "model_config.json").write_text(json.dumps({"feature_set": "elo_attack_defense"}), encoding="utf-8")
    (silver / "sources.json").write_text(json.dumps(_composition([2030, 2031, 2032], source_name)), encoding="utf-8")
    return {
        "gold": gold / "matches_model.csv",
        "config": gold / "model_config.json",
        "silver": silver,
        "clubs": registry_csv,
    }


def test_export_writes_parquet_csv_and_manifest(
    tmp_path: Path, synthetic_matches: pd.DataFrame, synthetic_registry: ClubRegistry
) -> None:
    from brasileirao.data_pipeline.ingest import read_matches  # noqa: PLC0415
    from tests.fixtures.synthetic import SYNTHETIC_CLUBS_CSV  # noqa: PLC0415

    paths = _write_workspace(tmp_path, synthetic_matches, SYNTHETIC_CLUBS_CSV)
    output = tmp_path / "out" / "match_priors_synthetic.parquet"
    written, manifest = export_match_priors(
        "serie_a",
        SEASONS,
        output,
        read_matches(paths["gold"]),
        synthetic_registry,
        CONFIG,
        paths["gold"],
        paths["config"],
        paths["silver"],
        paths["clubs"],
        TRAINING,
        write_csv=True,
        expected_per_season=None,
    )
    stored = pd.read_parquet(output)
    assert list(stored.columns) == COLUMNS and len(stored) == manifest["validation"]["n_rows"]
    assert written["manifest"] == manifest_path_for(output) and written["csv"].exists()
    assert manifest["outputs"]["parquet"]["sha256"] == __import__("hashlib").sha256(output.read_bytes()).hexdigest()
    assert manifest["sources"][0]["source_name"] == SYNTHETIC_SOURCE and manifest["seasons"] == SEASONS
    assert manifest["license"]["redistribution"] is False and manifest["model"]["seed"] is None


def test_export_refuses_gold_whose_source_differs_from_the_composition(
    tmp_path: Path, synthetic_matches: pd.DataFrame, synthetic_registry: ClubRegistry
) -> None:
    from brasileirao.data_pipeline.ingest import read_matches  # noqa: PLC0415
    from tests.fixtures.synthetic import SYNTHETIC_CLUBS_CSV  # noqa: PLC0415

    paths = _write_workspace(tmp_path, synthetic_matches, SYNTHETIC_CLUBS_CSV)
    gold = read_matches(paths["gold"]).assign(source="outra-fonte")
    with pytest.raises(ProvenanceError):
        export_match_priors(
            "serie_a",
            SEASONS,
            tmp_path / "x.parquet",
            gold,
            synthetic_registry,
            CONFIG,
            paths["gold"],
            paths["config"],
            paths["silver"],
            paths["clubs"],
            TRAINING,
            expected_per_season=None,
        )


def test_cli_parser_accepts_the_documented_command() -> None:
    arguments = cli.build_parser().parse_args(
        ["export-match-priors", "--competition", "serie_a", "--seasons", "2024,2025,2026", "--output", "x.parquet"]
    )
    assert (arguments.seasons, arguments.expected_matches_per_season, arguments.csv) == ("2024,2025,2026", 380, False)


def test_cli_fails_cleanly_without_gold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from brasileirao.config import ProjectPaths  # noqa: PLC0415

    monkeypatch.setattr(cli, "PATHS", ProjectPaths(root=tmp_path))
    with pytest.raises(SystemExit) as error:
        cli.main(["export-match-priors", "--seasons", "2031", "--output", str(tmp_path / "o.parquet")])
    assert error.value.code == 1
