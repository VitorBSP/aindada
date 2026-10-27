"""Persistência imutável de snapshots de previsão (SQLite local)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from brasileirao.storage.schema import PredictionSnapshot, RoundReview

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
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
CREATE INDEX IF NOT EXISTS idx_snapshots_season_date ON snapshots (season, reference_date);
CREATE TABLE IF NOT EXISTS round_reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    model_version TEXT NOT NULL,
    data_until TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: int
    season: int
    reference_date: str
    generated_at: str
    model_version: str
    data_version: str
    n_simulations: int


class SnapshotStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def save(self, snapshot: PredictionSnapshot) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO snapshots (season, reference_date, generated_at, model_version, "
                "data_version, n_simulations, seed, is_synthetic, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot.season,
                    snapshot.reference_date,
                    snapshot.generated_at,
                    snapshot.model.model_version,
                    snapshot.data.version,
                    snapshot.n_simulations,
                    snapshot.seed,
                    int(snapshot.is_synthetic),
                    snapshot.model_dump_json(),
                ),
            )
            return int(cursor.lastrowid or 0)

    def list_records(self, season: int | None = None) -> list[SnapshotRecord]:
        query = (
            "SELECT snapshot_id, season, reference_date, generated_at, model_version, data_version, "
            "n_simulations FROM snapshots WHERE is_synthetic = 0"
        )
        parameters: tuple[int, ...] = ()
        if season is not None:
            query += " AND season = ?"
            parameters = (season,)
        query += " ORDER BY season, reference_date, generated_at"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [SnapshotRecord(*row) for row in rows]

    def load(self, snapshot_id: int) -> PredictionSnapshot:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return PredictionSnapshot.model_validate_json(row[0])

    def latest_per_reference_date(self, season: int) -> list[SnapshotRecord]:
        """Snapshot mais recente para cada data de referência (histórico de probabilidades)."""
        latest: dict[str, SnapshotRecord] = {}
        for record in self.list_records(season):
            latest[record.reference_date] = record
        return [latest[reference_date] for reference_date in sorted(latest)]

    def latest(self, season: int) -> PredictionSnapshot | None:
        records = self.latest_per_reference_date(season)
        if not records:
            return None
        return self.load(records[-1].snapshot_id)

    def save_round_review(self, review: RoundReview) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO round_reviews (season, generated_at, model_version, data_until, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (review.season, review.generated_at, review.model_version, review.data_until, review.model_dump_json()),
            )
            return int(cursor.lastrowid or 0)

    def latest_round_review(self, season: int) -> RoundReview | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM round_reviews WHERE season = ? ORDER BY review_id DESC LIMIT 1", (season,)
            ).fetchone()
        return None if row is None else RoundReview.model_validate_json(row[0])
