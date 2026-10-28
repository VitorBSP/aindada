"""Marcação do histórico reconstruído (ajuste 1 da Decisão 3 do ADR-0008, D-034).

Dados SINTÉTICOS (synthetic): partidas, snapshots e bancos gerados em pasta temporária.
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
from brasileirao.config import MODEL_VERSION, RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.storage.schema import DataInfo, PredictionSnapshot
from brasileirao.storage.snapshots import SnapshotRecord, SnapshotStore

SYNTHETIC_INFO = DataInfo(
    source="synthetic-fixture",
    version="synthetic",
    license_status="synthetic",
    retrieved_at="2032-10-01T00:00:00+00:00",
    warnings=["dados sintéticos de teste"],
)

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
    payload TEXT NOT NULL,
    composition_mode TEXT,
    license_status TEXT
);
"""


def _record(reference_date: str, generated_at: str, reconstructed: bool | None = None) -> SnapshotRecord:
    return SnapshotRecord(1, 2032, reference_date, generated_at, "m", "d", 10, reconstructed)


@pytest.fixture(scope="module")
def snapshot(
    synthetic_matches: pd.DataFrame, synthetic_rules: SeasonRules, synthetic_registry: ClubRegistry
) -> PredictionSnapshot:
    built = pipeline.build_snapshot(
        synthetic_matches,
        2032,
        date(2032, 10, 25),
        200,
        5,
        synthetic_rules,
        synthetic_registry,
        pipeline.ModelConfig("elo_only", RatingParams(), True),
        SYNTHETIC_INFO,
    )
    return built.model_copy(update={"is_synthetic": False})


@pytest.fixture
def reconstructed_store(tmp_path: Path, snapshot: PredictionSnapshot) -> SnapshotStore:
    store = SnapshotStore(tmp_path / "s.sqlite", include_research=True)
    store.save(snapshot.model_copy(update={"reference_date": "2032-10-18"}), reconstructed=True)
    store.save(snapshot)
    return store


def test_live_history_is_not_reconstructed() -> None:
    records = [_record("2032-05-01", "2032-05-02T12:00:00+00:00"), _record("2032-05-08", "2032-05-09T12:00:00+00:00")]
    assert pipeline.reconstruction_flags(records) == [False, False]


def test_point_generated_after_next_reference_is_reconstructed() -> None:
    records = [_record("2032-05-01", "2032-06-01T12:00:00+00:00"), _record("2032-05-08", "2032-06-01T12:00:00+00:00")]
    assert pipeline.reconstruction_flags(records)[0] is True


def test_last_point_follows_date_rule_when_not_flagged() -> None:
    records = [_record("2032-05-01", "2032-06-01T12:00:00+00:00"), _record("2032-05-08", "2032-06-01T12:00:00+00:00")]
    assert pipeline.reconstruction_flags(records)[-1] is False


def test_stored_flag_marks_last_point() -> None:
    records = [_record("2032-05-01", "2032-05-02T12:00:00+00:00", reconstructed=True)]
    assert pipeline.reconstruction_flags(records) == [True]


def test_date_rule_uses_brasilia_day() -> None:
    records = [_record("2032-05-01", "2032-05-09T02:00:00+00:00"), _record("2032-05-08", "2032-05-09T12:00:00+00:00")]
    assert pipeline.reconstruction_flags(records)[0] is False


def test_naive_generated_at_is_read_as_utc() -> None:
    assert pipeline.aware_timestamp("2032-05-09T02:00:00").isoformat() == "2032-05-09T02:00:00+00:00"


def test_history_mode_recorded_without_reconstruction() -> None:
    assert pipeline.history_mode([_record("2032-05-01", "2032-05-02T12:00:00+00:00")]) == "recorded"


def test_history_mode_reconstructed_with_any_point() -> None:
    records = [_record("2032-05-01", "2032-05-02T12:00:00+00:00", reconstructed=True)]
    assert pipeline.history_mode(records) == "reconstructed"


def test_past_reference_date_is_reconstruction(synthetic_matches: pd.DataFrame) -> None:
    assert pipeline.is_reconstruction(synthetic_matches, 2032, date(2032, 6, 1)) is True


def test_latest_finished_date_is_not_reconstruction(synthetic_matches: pd.DataFrame) -> None:
    latest = pipeline.default_reference_date(synthetic_matches, 2032)
    assert pipeline.is_reconstruction(synthetic_matches, 2032, latest) is False


def test_store_keeps_reconstructed_flag(reconstructed_store: SnapshotStore) -> None:
    assert [record.reconstructed for record in reconstructed_store.list_records(2032)] == [True, False]


def test_history_points_carry_reconstructed(reconstructed_store: SnapshotStore) -> None:
    points = pipeline.probability_history(reconstructed_store, 2032)
    assert [point["reconstructed"] for point in points] == [True, False]


def test_history_points_carry_model_version(reconstructed_store: SnapshotStore) -> None:
    points = pipeline.probability_history(reconstructed_store, 2032)
    assert {point["model_version"] for point in points} == {MODEL_VERSION}


def test_history_generated_at_has_timezone(reconstructed_store: SnapshotStore) -> None:
    points = pipeline.probability_history(reconstructed_store, 2032)
    assert all(pipeline.aware_timestamp(point["generated_at"]).utcoffset() is not None for point in points)


def test_export_seasons_has_history_mode(tmp_path: Path, reconstructed_store: SnapshotStore) -> None:
    pipeline.export_static_api(reconstructed_store, 2032, tmp_path / "export")
    seasons = json.loads((tmp_path / "export" / "api" / "seasons.json").read_text(encoding="utf-8"))
    assert seasons[0]["history_mode"] == "reconstructed"


def _legacy_database(path: Path, snapshot: PredictionSnapshot) -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(LEGACY_SCHEMA)
        connection.execute(
            "INSERT INTO snapshots (season, reference_date, generated_at, model_version, data_version, "
            "n_simulations, seed, is_synthetic, payload, composition_mode, license_status) "
            "VALUES (2032, ?, ?, 'm', 'd', 1, 1, 0, ?, 'publication', 'synthetic')",
            (snapshot.reference_date, snapshot.generated_at, snapshot.model_dump_json()),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def test_migration_adds_reconstructed_column_once(tmp_path: Path, snapshot: PredictionSnapshot) -> None:
    path = _legacy_database(tmp_path / "legacy.sqlite", snapshot)
    SnapshotStore(path)
    SnapshotStore(path)
    connection = sqlite3.connect(path)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM pragma_table_info('snapshots') WHERE name = 'reconstructed'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 1


def test_legacy_row_has_unknown_flag(tmp_path: Path, snapshot: PredictionSnapshot) -> None:
    path = _legacy_database(tmp_path / "legacy.sqlite", snapshot)
    assert SnapshotStore(path, include_research=True).list_records(2032)[0].reconstructed is None


def test_legacy_history_still_readable(tmp_path: Path, snapshot: PredictionSnapshot) -> None:
    path = _legacy_database(tmp_path / "legacy.sqlite", snapshot)
    points = pipeline.probability_history(SnapshotStore(path, include_research=True), 2032)
    assert points[0]["reconstructed"] is False
