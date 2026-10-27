"""Camadas raw (bronze), silver e gold."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from brasileirao.contracts import ClubCardTotals, MatchRecord, MatchStatus, SourceManifest
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.data_pipeline.sources import BrasileiraoDatasetSource, SourceSnapshot
from brasileirao.logging_utils import get_logger

LOGGER = get_logger(__name__)

SILVER_MATCH_COLUMNS = [
    "match_id",
    "season",
    "round",
    "match_date",
    "home_id",
    "away_id",
    "home_goals",
    "away_goals",
    "status",
    "source",
    "source_match_id",
]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ingest_raw(snapshot: SourceSnapshot, raw_root: Path) -> Path:
    """Copia os arquivos da fonte, sem modificação, e grava o manifesto de proveniência."""
    target_dir = raw_root / snapshot.source_name / snapshot.version[:12]
    target_dir.mkdir(parents=True, exist_ok=True)
    file_hashes: dict[str, str] = {}
    for logical_name, source_path in snapshot.files.items():
        target_path = target_dir / f"{logical_name}{source_path.suffix}"
        shutil.copyfile(source_path, target_path)
        file_hashes[target_path.name] = sha256_of(target_path)
    manifest = SourceManifest(
        source_name=snapshot.source_name,
        origin=snapshot.origin,
        version=snapshot.version,
        retrieved_at=snapshot.retrieved_at,
        files=file_hashes,
        license_status=snapshot.license_status,
        license_notes=snapshot.license_notes,
        allowed_uses=list(snapshot.allowed_uses),
    )
    (target_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    LOGGER.info("raw_ingested", extra={"dir": str(target_dir), "files": file_hashes})
    return target_dir


def load_manifest(raw_dir: Path) -> SourceManifest:
    return SourceManifest.model_validate_json((raw_dir / "manifest.json").read_text("utf-8"))


def build_match_records(raw_dir: Path, registry: ClubRegistry) -> list[MatchRecord]:
    manifest = load_manifest(raw_dir)
    raw_matches = BrasileiraoDatasetSource.parse_matches(raw_dir / "matches.json")
    club_ids = registry.resolve_many(
        [match.home_name for match in raw_matches] + [match.away_name for match in raw_matches]
    )
    return [
        MatchRecord(
            match_id=f"bds-{raw_match.source_match_id}",
            season=raw_match.season,
            round=raw_match.round,
            match_date=raw_match.match_date,
            home_id=club_ids[raw_match.home_name.strip()],
            away_id=club_ids[raw_match.away_name.strip()],
            home_goals=raw_match.home_goals,
            away_goals=raw_match.away_goals,
            status=raw_match.status,
            source=f"{manifest.source_name}@{manifest.version[:12]}",
            source_match_id=raw_match.source_match_id,
        )
        for raw_match in raw_matches
    ]


def build_cards_by_match(raw_dir: Path, registry: ClubRegistry) -> pd.DataFrame:
    """Cartões por clube e partida, para permitir totais "até a data de referência"."""
    raw_cards = BrasileiraoDatasetSource.parse_cards(raw_dir / "cards.json")
    club_ids = registry.resolve_many(card.club_name for card in raw_cards)
    red_counter: Counter[tuple[int, str, str]] = Counter()
    yellow_counter: Counter[tuple[int, str, str]] = Counter()
    keys: set[tuple[int, str, str]] = set()
    for card in raw_cards:
        key = (card.season, f"bds-{card.source_match_id}", club_ids[card.club_name.strip()])
        keys.add(key)
        color = card.card_color.strip().lower()
        if color.startswith("vermelh"):
            red_counter[key] += 1
        elif color.startswith("amarel"):
            yellow_counter[key] += 1
    rows = [
        {
            "season": season,
            "match_id": match_id,
            "club_id": club_id,
            "red_cards": red_counter[(season, match_id, club_id)],
            "yellow_cards": yellow_counter[(season, match_id, club_id)],
        }
        for season, match_id, club_id in sorted(keys)
    ]
    return pd.DataFrame(rows, columns=["season", "match_id", "club_id", "red_cards", "yellow_cards"])


def card_totals_as_of(
    cards_by_match: pd.DataFrame, matches_data: pd.DataFrame, season: int, reference_date: date
) -> list[ClubCardTotals]:
    observed_ids = set(
        matches_data.loc[
            (matches_data["season"] == season)
            & (matches_data["status"] == MatchStatus.FINISHED.value)
            & (matches_data["match_date"].dt.date <= reference_date),
            "match_id",
        ]
    )
    season_cards = cards_by_match[(cards_by_match["season"] == season) & cards_by_match["match_id"].isin(observed_ids)]
    grouped = season_cards.groupby("club_id").agg(
        red_cards=("red_cards", "sum"), yellow_cards=("yellow_cards", "sum"), matches_covered=("match_id", "nunique")
    )
    return [
        ClubCardTotals(
            season=season,
            club_id=str(club_id),
            red_cards=int(row.red_cards),
            yellow_cards=int(row.yellow_cards),
            matches_covered=int(row.matches_covered),
        )
        for club_id, row in grouped.iterrows()
    ]


def matches_to_frame(match_records: list[MatchRecord]) -> pd.DataFrame:
    matches_data = pd.DataFrame([record.model_dump(mode="json") for record in match_records])
    matches_data = matches_data[SILVER_MATCH_COLUMNS]
    matches_data["status"] = matches_data["status"].astype(str)
    matches_data["match_date"] = pd.to_datetime(matches_data["match_date"])
    for column in ("round", "home_goals", "away_goals"):
        matches_data[column] = matches_data[column].astype("Int64")
    return matches_data.sort_values(["season", "match_date", "match_id"]).reset_index(drop=True)


def detect_changes(previous_matches: pd.DataFrame, current_matches: pd.DataFrame) -> list[dict[str, str]]:
    """Diferenças de calendário/resultado entre duas versões da camada silver."""
    tracked_columns = ["match_date", "status", "home_goals", "away_goals", "round"]
    previous_indexed = previous_matches.set_index("match_id")
    changes: list[dict[str, str]] = []
    for current_row in current_matches.itertuples(index=False):
        match_id = str(current_row.match_id)
        if match_id not in previous_indexed.index:
            changes.append({"match_id": match_id, "change": "new_match"})
            continue
        previous_row = previous_indexed.loc[match_id]
        for column in tracked_columns:
            old_value, new_value = previous_row[column], getattr(current_row, column)
            if str(old_value) != str(new_value):
                changes.append({"match_id": match_id, "change": column, "old": str(old_value), "new": str(new_value)})
    return changes


def write_silver(raw_dir: Path, registry: ClubRegistry, silver_dir: Path) -> pd.DataFrame:
    silver_dir.mkdir(parents=True, exist_ok=True)
    matches_data = matches_to_frame(build_match_records(raw_dir, registry))
    matches_path = silver_dir / "matches.csv"
    if matches_path.exists():
        previous_matches = read_matches(matches_path)
        changes = detect_changes(previous_matches, matches_data)
        if changes:
            stamp = datetime.now(tz=UTC).isoformat()
            with (silver_dir / "changes.jsonl").open("a", encoding="utf-8") as change_log:
                for change in changes:
                    change_log.write(json.dumps({"detected_at": stamp, **change}) + "\n")
        LOGGER.info("silver_changes", extra={"n_changes": len(changes)})
    matches_data.to_csv(matches_path, index=False)
    build_cards_by_match(raw_dir, registry).to_csv(silver_dir / "cards_by_match.csv", index=False)
    LOGGER.info("silver_written", extra={"n_matches": len(matches_data)})
    return matches_data


def read_matches(path: Path) -> pd.DataFrame:
    matches_data = pd.read_csv(
        path,
        dtype={"match_id": str, "source_match_id": str, "home_id": str, "away_id": str},
        parse_dates=["match_date"],
    )
    for column in ("round", "home_goals", "away_goals"):
        matches_data[column] = matches_data[column].astype("Int64")
    return matches_data


def write_gold(silver_dir: Path, gold_dir: Path) -> pd.DataFrame:
    gold_dir.mkdir(parents=True, exist_ok=True)
    matches_data = read_matches(silver_dir / "matches.csv")
    model_matches = matches_data[
        matches_data["status"].isin(
            [MatchStatus.FINISHED.value, MatchStatus.SCHEDULED.value, MatchStatus.POSTPONED.value]
        )
    ].sort_values(["match_date", "match_id"])
    model_matches.to_csv(gold_dir / "matches_model.csv", index=False)
    return model_matches.reset_index(drop=True)
