"""Filtro de publicação no SQLite: snapshots de pesquisa e legados ficam fora da API e do export.

Dados SINTÉTICOS (synthetic): composição, manifestos e partidas gerados em pasta temporária.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from brasileirao import pipeline
from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.config import RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.data_pipeline.composition import CompositionMode
from brasileirao.provenance import build_data_info, load_data_info, load_data_sources
from brasileirao.storage.schema import DataInfo, PredictionSnapshot, RoundReview
from brasileirao.storage.snapshots import SnapshotStore
from tests.fixtures.provenance import write_synthetic_composition

LEGACY_SCHEMA = """
CREATE TABLE snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    reference_date TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    model_version TEXT NOT NULL,
    data_version TEXT NOT NULL,
    n_simulations INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    is_synthetic INTEGER NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE round_reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    model_version TEXT NOT NULL,
    data_until TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""

LEGACY_DATA = {
    "source": "brasileirao_dataset (https://example.org/synthetic)",
    "version": "synthetic-legacy",
    "license_status": "research_only_unverified",
    "retrieved_at": "2032-10-01T00:00:00+00:00",
    "warnings": [],
}


@pytest.fixture(scope="module")
def publication_info(tmp_path_factory: pytest.TempPathFactory) -> DataInfo:
    root = tmp_path_factory.mktemp("visibility")
    write_synthetic_composition(root)
    sources = load_data_sources(root / "data" / "silver", root / "data" / "raw")
    return build_data_info(sources, CompositionMode.PUBLICATION, [])


@pytest.fixture(scope="module")
def research_info(publication_info: DataInfo) -> DataInfo:
    return build_data_info(publication_info.sources, CompositionMode.RESEARCH, [])


@pytest.fixture(scope="module")
def publication_snapshot(
    synthetic_matches: pd.DataFrame,
    synthetic_rules: SeasonRules,
    synthetic_registry: ClubRegistry,
    publication_info: DataInfo,
) -> PredictionSnapshot:
    return pipeline.build_snapshot(
        synthetic_matches,
        2032,
        date(2032, 10, 25),
        200,
        9,
        synthetic_rules,
        synthetic_registry,
        pipeline.ModelConfig("elo_only", RatingParams(), True),
        publication_info,
    )


@pytest.fixture(scope="module")
def research_snapshot(publication_snapshot: PredictionSnapshot, research_info: DataInfo) -> PredictionSnapshot:
    return publication_snapshot.model_copy(update={"data": research_info, "reference_date": "2032-10-26"})


@pytest.fixture(scope="module")
def round_review(
    synthetic_matches: pd.DataFrame,
    synthetic_rules: SeasonRules,
    synthetic_registry: ClubRegistry,
    research_info: DataInfo,
) -> RoundReview:
    season_matches = synthetic_matches[synthetic_matches["season"] == 2032]
    round_two = pd.Timestamp(season_matches.loc[season_matches["round"] == 2, "match_date"].min()).date()
    return pipeline.build_round_review(
        synthetic_matches,
        2032,
        round_two,
        100,
        9,
        synthetic_rules,
        synthetic_registry,
        pipeline.ModelConfig("elo_only", RatingParams(), True),
        research_info,
    )


@pytest.fixture
def mixed_store(
    tmp_path: Path, publication_snapshot: PredictionSnapshot, research_snapshot: PredictionSnapshot
) -> SnapshotStore:
    store = SnapshotStore(tmp_path / "s.sqlite")
    store.save(publication_snapshot)
    store.save(research_snapshot)
    return store


def _legacy_database(path: Path, snapshot: PredictionSnapshot) -> Path:
    payload = snapshot.model_dump(mode="json")
    payload["schema_version"] = "1.1"
    payload["data"] = LEGACY_DATA
    with sqlite3.connect(path) as connection:
        connection.executescript(LEGACY_SCHEMA)
        connection.execute(
            "INSERT INTO snapshots (season, reference_date, generated_at, model_version, data_version, "
            "n_simulations, seed, is_synthetic, payload) VALUES (2032, '2032-10-25', 'x', 'm', 'd', 1, 1, 0, ?)",
            (json.dumps(payload),),
        )
    connection.close()
    return path


def _column(path: Path, query: str) -> list[object]:
    connection = sqlite3.connect(path)
    try:
        return [row[0] for row in connection.execute(query)]
    finally:
        connection.close()


def test_latest_skips_research_snapshot(mixed_store: SnapshotStore) -> None:
    latest = mixed_store.latest(2032)
    assert latest is not None and latest.data.composition_mode == "publication"


def test_research_snapshot_visible_when_requested(mixed_store: SnapshotStore) -> None:
    research_store = SnapshotStore(mixed_store.database_path, include_research=True)
    assert len(research_store.list_records(2032)) == 2


def test_probability_history_ignores_research(mixed_store: SnapshotStore) -> None:
    dates = [entry["reference_date"] for entry in pipeline.probability_history(mixed_store, 2032)]
    assert dates == ["2032-10-25"]


def test_only_research_snapshot_is_invisible(tmp_path: Path, research_snapshot: PredictionSnapshot) -> None:
    store = SnapshotStore(tmp_path / "s.sqlite")
    store.save(research_snapshot)
    assert store.latest(2032) is None


def test_export_refuses_research_only_store(tmp_path: Path, research_snapshot: PredictionSnapshot) -> None:
    store = SnapshotStore(tmp_path / "s.sqlite")
    store.save(research_snapshot)
    with pytest.raises(RuntimeError, match="nenhum snapshot"):
        pipeline.export_static_api(store, 2032, tmp_path / "export")


def test_saved_row_records_license_status(tmp_path: Path, publication_snapshot: PredictionSnapshot) -> None:
    SnapshotStore(tmp_path / "s.sqlite").save(publication_snapshot)
    assert _column(tmp_path / "s.sqlite", "SELECT license_status FROM snapshots") == ["licensed_with_attribution"]


def test_research_round_review_hidden(tmp_path: Path, round_review: RoundReview) -> None:
    store = SnapshotStore(tmp_path / "s.sqlite")
    store.save_round_review(round_review)
    assert store.latest_round_review(2032) is None


def test_round_review_records_composition_mode(round_review: RoundReview) -> None:
    assert round_review.composition_mode == "research"


def test_migration_backfills_legacy_license(tmp_path: Path, publication_snapshot: PredictionSnapshot) -> None:
    path = _legacy_database(tmp_path / "legacy.sqlite", publication_snapshot)
    SnapshotStore(path)
    assert _column(path, "SELECT license_status FROM snapshots") == ["research_only_unverified"]


def test_migration_is_idempotent(tmp_path: Path, publication_snapshot: PredictionSnapshot) -> None:
    path = _legacy_database(tmp_path / "legacy.sqlite", publication_snapshot)
    SnapshotStore(path)
    SnapshotStore(path)
    assert _column(path, "SELECT COUNT(*) FROM pragma_table_info('snapshots') WHERE name = 'composition_mode'") == [1]


def test_migration_creates_publication_index(tmp_path: Path, publication_snapshot: PredictionSnapshot) -> None:
    path = _legacy_database(tmp_path / "legacy.sqlite", publication_snapshot)
    SnapshotStore(path)
    indexes = _column(path, "SELECT name FROM sqlite_master WHERE type = 'index'")
    assert "idx_snapshots_publication" in indexes


def test_legacy_snapshot_hidden_from_publication(tmp_path: Path, publication_snapshot: PredictionSnapshot) -> None:
    path = _legacy_database(tmp_path / "legacy.sqlite", publication_snapshot)
    assert SnapshotStore(path).latest(2032) is None


def test_legacy_snapshot_readable_in_research(tmp_path: Path, publication_snapshot: PredictionSnapshot) -> None:
    path = _legacy_database(tmp_path / "legacy.sqlite", publication_snapshot)
    latest = SnapshotStore(path, include_research=True).latest(2032)
    assert latest is not None and latest.data.sources[0].source_name == "brasileirao_dataset"


def test_api_ignores_research_snapshot(tmp_path: Path, research_snapshot: PredictionSnapshot) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from apps.api.main import create_app  # noqa: PLC0415
    from fastapi.testclient import TestClient  # noqa: PLC0415

    store = SnapshotStore(tmp_path / "s.sqlite")
    store.save(research_snapshot)
    client = TestClient(create_app(store, tmp_path / "none.json", tmp_path / "editorial"))
    assert client.get("/api/seasons/2032/predictions").status_code == 404


def test_api_not_found_detail_has_no_local_path(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from apps.api.main import create_app  # noqa: PLC0415
    from fastapi.testclient import TestClient  # noqa: PLC0415

    client = TestClient(create_app(SnapshotStore(tmp_path / "s.sqlite"), tmp_path / "none.json", tmp_path / "ed"))
    details = [client.get(route).text for route in ("/api/seasons/2032/predictions", "/api/models/metrics")]
    assert not any(tmp_path.name in detail or "sqlite" in detail for detail in details)


def test_research_mode_over_publication_composition_is_research(tmp_path: Path) -> None:
    write_synthetic_composition(tmp_path)
    data_info = load_data_info(tmp_path / "data" / "silver", tmp_path / "data" / "raw", CompositionMode.RESEARCH, [])
    assert data_info.composition_mode == "research"
