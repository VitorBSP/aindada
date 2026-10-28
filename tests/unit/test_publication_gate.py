"""Gate de publicação G1 a G5 do ADR-0008. Dados SINTÉTICOS."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from brasileirao.cli import main
from brasileirao.data_pipeline.adaoduque import AdaoDuqueSource
from brasileirao.data_pipeline.composition import CompositionMode
from brasileirao.data_pipeline.football_data_org import FootballDataOrgSource
from brasileirao.provenance import load_data_info
from brasileirao.publication_gate import (
    GateInputs,
    base_source_of,
    check_g1_gold_sources,
    check_g2_manual_corrections,
    check_g3_snapshot_sources,
    check_g4_attribution,
    check_g5_artifact,
    run_publication_gate,
)
from tests.fixtures.provenance import (
    CURRENT_SOURCE,
    RESEARCH_SOURCE,
    label_gold_sources,
    write_synthetic_composition,
)

FOOTER = f"<footer><p>{FootballDataOrgSource.attribution}</p><p>{AdaoDuqueSource.attribution}</p></footer>"


@pytest.fixture
def composition(tmp_path: Path) -> dict[str, Any]:
    return write_synthetic_composition(tmp_path)


@pytest.fixture
def gold(synthetic_matches: pd.DataFrame) -> pd.DataFrame:
    return label_gold_sources(synthetic_matches)


@pytest.fixture
def snapshot(tmp_path: Path, composition: dict[str, Any]) -> dict[str, Any]:
    data_info = load_data_info(tmp_path / "data" / "silver", tmp_path / "data" / "raw", CompositionMode.PUBLICATION, [])
    return {
        "season": 2032,
        "model": {"training_seasons": [2030, 2031]},
        "data": data_info.model_dump(mode="json"),
    }


def _rules(findings: list[Any]) -> list[str]:
    return [finding.rule for finding in findings]


def test_base_source_ignores_version_and_correction() -> None:
    label = "football_data_org@v4-2032+manual_correction@https://example.org/x:2032-10-01"
    assert base_source_of(label) == "football_data_org"


def test_g1_accepts_gold_from_publication_sources(gold: pd.DataFrame, composition: dict[str, Any]) -> None:
    assert check_g1_gold_sources(gold, composition) == []


def test_g1_rejects_research_mode(gold: pd.DataFrame, composition: dict[str, Any]) -> None:
    assert _rules(check_g1_gold_sources(gold, {**composition, "mode": "research"})) == ["G1"]


def test_g1_rejects_row_from_source_outside_composition(gold: pd.DataFrame, composition: dict[str, Any]) -> None:
    tainted = gold.copy()
    tainted.loc[0, "source"] = f"{RESEARCH_SOURCE}@synthetic"
    assert _rules(check_g1_gold_sources(tainted, composition)).count("G1") >= 1


def test_g1_rejects_source_without_public_display(tmp_path: Path, gold: pd.DataFrame) -> None:
    plan = {2030: RESEARCH_SOURCE, 2031: RESEARCH_SOURCE, 2032: CURRENT_SOURCE}
    document = write_synthetic_composition(tmp_path / "mixed", plan, CompositionMode.PUBLICATION)
    findings = check_g1_gold_sources(label_gold_sources(gold, plan), document)
    assert any("public_display_derived" in finding.detail for finding in findings)


def test_g1_rejects_row_from_other_season_source(gold: pd.DataFrame, composition: dict[str, Any]) -> None:
    swapped = gold.copy()
    swapped.loc[swapped["season"] == 2032, "source"] = "adaoduque_kaggle@synthetic-v1"
    assert any("diferente da composição" in finding.detail for finding in check_g1_gold_sources(swapped, composition))


def test_g1_rejects_season_without_source(gold: pd.DataFrame, composition: dict[str, Any]) -> None:
    seasons = {key: value for key, value in composition["seasons"].items() if key != "2030"}
    findings = check_g1_gold_sources(gold, {**composition, "seasons": seasons})
    assert any("sem fonte na composição" in finding.detail for finding in findings)


def test_g1_rejects_empty_gold(gold: pd.DataFrame, composition: dict[str, Any]) -> None:
    assert _rules(check_g1_gold_sources(gold.iloc[0:0], composition)) == ["G1"]


def test_g2_accepts_correction_with_evidence(gold: pd.DataFrame) -> None:
    corrected = gold.copy()
    corrected.loc[0, "source"] = "football_data_org@v1+manual_correction@https://example.org/evidence:2032-10-01"
    assert check_g2_manual_corrections(corrected) == []


def test_g2_rejects_correction_without_url(gold: pd.DataFrame) -> None:
    corrected = gold.copy()
    corrected.loc[0, "source"] = "football_data_org@v1+manual_correction@sem-evidencia:2032-10-01"
    assert _rules(check_g2_manual_corrections(corrected)) == ["G2"]


def test_g3_accepts_covering_sources(snapshot: dict[str, Any]) -> None:
    assert check_g3_snapshot_sources(snapshot) == []


def test_g3_rejects_uncovered_training_season(snapshot: dict[str, Any]) -> None:
    uncovered = {**snapshot, "model": {"training_seasons": [2029, 2030, 2031]}}
    assert any("2029" in finding.detail for finding in check_g3_snapshot_sources(uncovered))


def test_g3_rejects_restrictive_aggregate_license(snapshot: dict[str, Any]) -> None:
    restricted = {**snapshot, "data": {**snapshot["data"], "license_status": "research_only_unverified"}}
    assert _rules(check_g3_snapshot_sources(restricted)) == ["G3"]


def test_g3_rejects_legacy_snapshot() -> None:
    legacy = {
        "season": 2032,
        "model": {"training_seasons": [2031]},
        "data": {"license_status": "research_only_unverified", "sources": [{"seasons": []}]},
    }
    assert len(check_g3_snapshot_sources(legacy)) == 3


def test_g4_accepts_footer_with_exact_attribution(snapshot: dict[str, Any]) -> None:
    assert check_g4_attribution(snapshot, [FOOTER]) == []


def test_g4_accepts_attribution_split_by_markup(snapshot: dict[str, Any]) -> None:
    linked = FOOTER.replace(
        "Football-Data.org API", '<a href="https://www.football-data.org">Football-Data.org API</a>'
    )
    assert check_g4_attribution(snapshot, [linked]) == []


def test_g4_rejects_html_without_attribution(snapshot: dict[str, Any]) -> None:
    assert len(check_g4_attribution(snapshot, ["<footer>sem créditos</footer>"])) == 2


def test_g4_rejects_source_without_attribution_text(snapshot: dict[str, Any]) -> None:
    sources = [{**source, "attribution": None} for source in snapshot["data"]["sources"]]
    stripped = {**snapshot, "data": {**snapshot["data"], "sources": sources}}
    assert all("sem texto" in finding.detail for finding in check_g4_attribution(stripped, [FOOTER]))


def _artifact(root: Path, *files: str) -> Path:
    for relative in ("index.html", "data/api/seasons/2032/predictions.json", *files):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("synthetic", encoding="utf-8")
    return root


def test_g5_accepts_static_site_and_export(tmp_path: Path) -> None:
    assert check_g5_artifact(_artifact(tmp_path / "site")) == []


@pytest.mark.parametrize(
    "forbidden",
    [
        "data/snapshots.sqlite",
        "data/api/matches.csv",
        "data/raw/football_data_org/manifest.json",
        "data/silver/sources.json",
        "data/gold/matches_model.csv",
    ],
)
def test_g5_rejects_data_files(tmp_path: Path, forbidden: str) -> None:
    assert _rules(check_g5_artifact(_artifact(tmp_path / "site", forbidden))) == ["G5"]


def _gate_inputs(tmp_path: Path, gold: pd.DataFrame, snapshot: dict[str, Any], footer: str) -> GateInputs:
    gold_path = tmp_path / "data" / "gold" / "matches_model.csv"
    gold_path.parent.mkdir(parents=True, exist_ok=True)
    gold.to_csv(gold_path, index=False)
    site = _artifact(tmp_path / "site")
    (site / "index.html").write_text(footer, encoding="utf-8")
    predictions = site / "data" / "api" / "seasons" / "2032" / "predictions.json"
    predictions.write_text(json.dumps(snapshot), encoding="utf-8")
    return GateInputs(gold_path, tmp_path / "data" / "silver" / "sources.json", predictions, site)


def test_gate_passes_complete_publication(tmp_path: Path, gold: pd.DataFrame, snapshot: dict[str, Any]) -> None:
    assert run_publication_gate(_gate_inputs(tmp_path, gold, snapshot, FOOTER)) == []


def test_gate_fails_without_footer(tmp_path: Path, gold: pd.DataFrame, snapshot: dict[str, Any]) -> None:
    assert set(_rules(run_publication_gate(_gate_inputs(tmp_path, gold, snapshot, "<p></p>")))) == {"G4"}


def test_cli_gate_exits_with_error_on_failure(tmp_path: Path, gold: pd.DataFrame, snapshot: dict[str, Any]) -> None:
    inputs = _gate_inputs(tmp_path, gold, snapshot, "<p></p>")
    arguments = [
        "publication-gate",
        "--gold",
        str(inputs.gold_matches),
        "--composition",
        str(inputs.composition),
        "--predictions",
        str(inputs.predictions),
        "--artifact-dir",
        str(inputs.artifact_dir),
    ]
    with pytest.raises(SystemExit) as raised:
        main(arguments)
    assert raised.value.code == 1
