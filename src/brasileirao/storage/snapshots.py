"""Persistência imutável de snapshots de previsão (SQLite local).

Cada linha guarda `composition_mode` e `license_status` do `DataInfo` (ADR-0008, passo 10). Por padrão a
loja só lê o que é publicável: composição de publicação e licença verificada ou com atribuição. Snapshots de
pesquisa, os anteriores ao schema 1.2 (sem modo) e as revisões por rodada sem modo ficam gravados, mas só
aparecem com `include_research=True` (uso local, nunca na API pública nem no export estático).

A coluna `reconstructed` (ajuste 1 da Decisão 3 do ADR-0008) marca o snapshot calculado depois que a base já
tinha resultados posteriores à sua `reference_date`. Fica fora do payload, então o `PredictionSnapshot` e o
`schema_version` não mudam. Linhas antigas ficam com `NULL` (desconhecido) e o export aplica a regra de datas.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from brasileirao.contracts import PUBLISHABLE_LICENSE_STATUSES
from brasileirao.storage.schema import PredictionSnapshot, RoundReview

PUBLICATION_MODE = "publication"

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
    payload TEXT NOT NULL,
    composition_mode TEXT,
    license_status TEXT,
    reconstructed INTEGER
);
CREATE INDEX IF NOT EXISTS idx_snapshots_season_date ON snapshots (season, reference_date);
CREATE TABLE IF NOT EXISTS round_reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    model_version TEXT NOT NULL,
    data_until TEXT NOT NULL,
    payload TEXT NOT NULL,
    composition_mode TEXT,
    license_status TEXT
);
"""

_PUBLICATION_COLUMNS = ("composition_mode", "license_status")

_BACKFILL = {
    "snapshots": ("$.data.composition_mode", "$.data.license_status"),
    "round_reviews": ("$.composition_mode", "$.license_status"),
}

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_snapshots_publication
    ON snapshots (season, composition_mode, license_status, reference_date);
CREATE INDEX IF NOT EXISTS idx_round_reviews_publication
    ON round_reviews (season, composition_mode, license_status, review_id);
"""

_PUBLISHABLE_STATUSES = tuple(sorted(status.value for status in PUBLISHABLE_LICENSE_STATUSES))
_PUBLICATION_FILTER = (
    f" AND composition_mode = '{PUBLICATION_MODE}'"
    f" AND license_status IN ({', '.join(repr(status) for status in _PUBLISHABLE_STATUSES)})"
)


def _migrate(connection: sqlite3.Connection) -> None:
    """Acrescenta as colunas novas a bancos antigos e preenche as de publicação pelo payload (idempotente)."""
    for table, (mode_path, license_path) in _BACKFILL.items():
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for column in _PUBLICATION_COLUMNS:
            if column not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
        connection.execute(
            f"UPDATE {table} SET composition_mode = json_extract(payload, ?), "
            "license_status = json_extract(payload, ?) "
            "WHERE license_status IS NULL AND json_extract(payload, ?) IS NOT NULL",
            (mode_path, license_path, license_path),
        )
    snapshot_columns = {row[1] for row in connection.execute("PRAGMA table_info(snapshots)")}
    if "reconstructed" not in snapshot_columns:
        connection.execute("ALTER TABLE snapshots ADD COLUMN reconstructed INTEGER")
    connection.executescript(_INDEXES)


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: int
    season: int
    reference_date: str
    generated_at: str
    model_version: str
    data_version: str
    n_simulations: int
    reconstructed: bool | None = None


def _record_from_row(row: tuple[Any, ...]) -> SnapshotRecord:
    snapshot_id, season, reference_date, generated_at, model_version, data_version, n_simulations, flag = row
    return SnapshotRecord(
        snapshot_id,
        season,
        reference_date,
        generated_at,
        model_version,
        data_version,
        n_simulations,
        None if flag is None else bool(flag),
    )


class SnapshotStore:
    def __init__(self, database_path: Path, include_research: bool = False) -> None:
        self.database_path = database_path
        self.include_research = include_research
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            _migrate(connection)

    @property
    def _visibility_filter(self) -> str:
        return "" if self.include_research else _PUBLICATION_FILTER

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def save(self, snapshot: PredictionSnapshot, reconstructed: bool = False) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO snapshots (season, reference_date, generated_at, model_version, data_version, "
                "n_simulations, seed, is_synthetic, payload, composition_mode, license_status, reconstructed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    snapshot.data.composition_mode,
                    snapshot.data.license_status,
                    int(reconstructed),
                ),
            )
            return int(cursor.lastrowid or 0)

    def list_records(self, season: int | None = None) -> list[SnapshotRecord]:
        query = (
            "SELECT snapshot_id, season, reference_date, generated_at, model_version, data_version, "
            "n_simulations, reconstructed FROM snapshots WHERE is_synthetic = 0" + self._visibility_filter
        )
        parameters: tuple[int, ...] = ()
        if season is not None:
            query += " AND season = ?"
            parameters = (season,)
        query += " ORDER BY season, reference_date, generated_at"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_record_from_row(row) for row in rows]

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
                "INSERT INTO round_reviews (season, generated_at, model_version, data_until, payload, "
                "composition_mode, license_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    review.season,
                    review.generated_at,
                    review.model_version,
                    review.data_until,
                    review.model_dump_json(),
                    review.composition_mode,
                    review.license_status,
                ),
            )
            return int(cursor.lastrowid or 0)

    def latest_round_review(self, season: int) -> RoundReview | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM round_reviews WHERE season = ?"
                + self._visibility_filter
                + " ORDER BY review_id DESC LIMIT 1",
                (season,),
            ).fetchone()
        return None if row is None else RoundReview.model_validate_json(row[0])
