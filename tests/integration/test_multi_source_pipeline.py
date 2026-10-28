"""`load_inputs` pela composição de fontes, export e API com `data.sources` (ADR-0008, passo 10).

Dados SINTÉTICOS: gold, manifestos e composição gerados em pasta temporária.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from brasileirao import pipeline
from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.config import ProjectPaths, RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.data_pipeline.composition import CompositionMode
from brasileirao.data_pipeline.football_data_org import FootballDataOrgSource
from brasileirao.provenance import ProvenanceError, load_data_info
from brasileirao.storage.schema import PredictionSnapshot
from brasileirao.storage.snapshots import SnapshotStore
from tests.fixtures.provenance import RESEARCH_SOURCE, label_gold_sources, write_synthetic_composition

KNOWN_EXCEPTIONS_HEADER = "season,code,note,source_name,source_match_id,home_goals,away_goals\n"


def _project(root: Path, gold: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> None:
    (root / "data" / "gold").mkdir(parents=True, exist_ok=True)
    (root / "data" / "reference").mkdir(parents=True, exist_ok=True)
    gold.to_csv(root / "data" / "gold" / "matches_model.csv", index=False)
    (root / "data" / "reference" / "known_exceptions.csv").write_text(KNOWN_EXCEPTIONS_HEADER, encoding="utf-8")
    monkeypatch.setattr(pipeline, "PATHS", ProjectPaths(root=root))


@pytest.fixture
def publication_project(tmp_path: Path, synthetic_matches: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> Path:
    write_synthetic_composition(tmp_path)
    _project(tmp_path, label_gold_sources(synthetic_matches), monkeypatch)
    return tmp_path


def test_load_inputs_reads_every_source(publication_project: Path) -> None:
    data_info = pipeline.load_inputs(2026)[4]
    assert len(data_info.sources) == 2


def test_load_inputs_fails_without_composition(
    tmp_path: Path, synthetic_matches: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(tmp_path, label_gold_sources(synthetic_matches), monkeypatch)
    with pytest.raises(ProvenanceError, match=r"sources.json"):
        pipeline.load_inputs(2026)


def test_load_inputs_rejects_gold_outside_composition(
    publication_project: Path, synthetic_matches: pd.DataFrame
) -> None:
    tainted = label_gold_sources(synthetic_matches)
    tainted.loc[0, "source"] = f"{RESEARCH_SOURCE}@synthetic"
    tainted.to_csv(publication_project / "data" / "gold" / "matches_model.csv", index=False)
    with pytest.raises(ProvenanceError, match="fora da composição"):
        pipeline.load_inputs(2026)


def test_load_inputs_research_mode_is_explicit(
    tmp_path: Path, synthetic_matches: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = {2030: RESEARCH_SOURCE, 2031: RESEARCH_SOURCE, 2032: RESEARCH_SOURCE}
    write_synthetic_composition(tmp_path, plan, CompositionMode.RESEARCH)
    _project(tmp_path, label_gold_sources(synthetic_matches, plan), monkeypatch)
    assert pipeline.load_inputs(2026, CompositionMode.RESEARCH)[4].composition_mode == "research"


@pytest.fixture(scope="module")
def stored_snapshot(
    tmp_path_factory: pytest.TempPathFactory,
    synthetic_matches: pd.DataFrame,
    synthetic_rules: SeasonRules,
    synthetic_registry: ClubRegistry,
) -> SnapshotStore:
    root = tmp_path_factory.mktemp("multi_source")
    write_synthetic_composition(root)
    data_info = load_data_info(root / "data" / "silver", root / "data" / "raw", CompositionMode.PUBLICATION, [])
    store = SnapshotStore(root / "snapshots.sqlite")
    snapshot = pipeline.build_snapshot(
        synthetic_matches,
        2032,
        date(2032, 10, 25),
        200,
        5,
        synthetic_rules,
        synthetic_registry,
        pipeline.ModelConfig("elo_only", RatingParams(), True),
        data_info,
    )
    store.save(snapshot)
    return store


def test_snapshot_roundtrip_keeps_sources(stored_snapshot: SnapshotStore) -> None:
    snapshot = stored_snapshot.latest(2032)
    assert snapshot is not None and [source.seasons for source in snapshot.data.sources] == [[2030, 2031], [2032]]


def test_export_carries_exact_attribution(stored_snapshot: SnapshotStore, tmp_path: Path) -> None:
    pipeline.export_static_api(stored_snapshot, 2032, tmp_path)
    exported = json.loads((tmp_path / "api" / "seasons" / "2032" / "predictions.json").read_text(encoding="utf-8"))
    assert FootballDataOrgSource.attribution in [source["attribution"] for source in exported["data"]["sources"]]


def test_api_predictions_expose_sources(stored_snapshot: SnapshotStore, tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from apps.api.main import create_app  # noqa: PLC0415
    from fastapi.testclient import TestClient  # noqa: PLC0415

    client = TestClient(create_app(stored_snapshot, tmp_path / "none.json", tmp_path / "editorial"))
    body = client.get("/api/seasons/2032/predictions").json()
    assert body["data"]["license_status"] == "licensed_with_attribution"


def test_legacy_snapshot_payload_still_loads(stored_snapshot: SnapshotStore, tmp_path: Path) -> None:
    snapshot = stored_snapshot.latest(2032)
    assert snapshot is not None
    payload = snapshot.model_dump(mode="json")
    payload["schema_version"] = "1.1"
    payload["data"] = {
        "source": "brasileirao_dataset (https://example.org/synthetic)",
        "version": "synthetic-legacy",
        "license_status": "research_only_unverified",
        "retrieved_at": "2032-10-01T00:00:00+00:00",
        "warnings": [],
    }
    reloaded = PredictionSnapshot.model_validate_json(json.dumps(payload))
    assert reloaded.data.sources[0].source_name == "brasileirao_dataset"
