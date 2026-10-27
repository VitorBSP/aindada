"""Camadas raw (bronze), silver e gold."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from brasileirao.contracts import ClubCardTotals, MatchRecord, MatchStatus, SourceManifest
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.data_pipeline.corrections import (
    CorrectionAction,
    CorrectionOutcome,
    ManualCorrection,
    apply_corrections,
)
from brasileirao.data_pipeline.sources import BrasileiraoDatasetSource, RawCard, RawMatch, SourceSnapshot
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


def _same_file(first: Path, second: Path) -> bool:
    return first.resolve() == second.resolve()


def ingest_raw(snapshot: SourceSnapshot, raw_root: Path) -> Path:
    """Copia os arquivos da fonte, sem modificação, e grava o manifesto de proveniência.

    Se o manifesto já existe com os mesmos hashes, ele é mantido: reingerir a mesma entrada não muda
    nenhum arquivo (critério de aceite do 01).
    """
    target_dir = raw_root / snapshot.source_name / snapshot.target_dir_name
    target_dir.mkdir(parents=True, exist_ok=True)
    file_hashes: dict[str, str] = {}
    for logical_name, source_path in snapshot.files.items():
        target_path = target_dir / f"{logical_name}{source_path.suffix}"
        if not _same_file(source_path, target_path):
            shutil.copyfile(source_path, target_path)
        file_hashes[target_path.name] = sha256_of(target_path)
    manifest_path = target_dir / "manifest.json"
    if manifest_path.exists():
        existing = load_manifest(target_dir)
        if existing.files == file_hashes and existing.version == snapshot.version:
            LOGGER.info("raw_unchanged", extra={"dir": str(target_dir)})
            return target_dir
    manifest = SourceManifest(
        source_name=snapshot.source_name,
        origin=snapshot.origin,
        version=snapshot.version,
        retrieved_at=snapshot.retrieved_at,
        files=file_hashes,
        license_status=snapshot.license_status,
        license_notes=snapshot.license_notes,
        allowed_uses=list(snapshot.allowed_uses),
        license_name=snapshot.license_name,
        terms_url=snapshot.terms_url,
        terms_checked_at=snapshot.terms_checked_at,
        attribution=snapshot.attribution,
    )
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    LOGGER.info("raw_ingested", extra={"dir": str(target_dir), "files": file_hashes})
    return target_dir


def load_manifest(raw_dir: Path) -> SourceManifest:
    return SourceManifest.model_validate_json((raw_dir / "manifest.json").read_text("utf-8"))


def assign_match_ids(raw_matches: Sequence[RawMatch], club_ids: Mapping[str, str]) -> list[str]:
    """`match_id` estável entre fontes: `<temporada>-<mandante>-<visitante>` com IDs canônicos.

    Um par mandante/visitante repetido na mesma temporada (exceção conhecida de 2009) recebe o sufixo
    `-r<rodada>` em todas as ocorrências. Se a rodada não desambiguar, a ingestão falha.
    """
    base_ids = [
        f"{match.season}-{club_ids[match.home_name.strip()]}-{club_ids[match.away_name.strip()]}"
        for match in raw_matches
    ]
    occurrences = Counter(base_ids)
    match_ids = [
        f"{base_id}-r{match.round:02d}" if occurrences[base_id] > 1 and match.round is not None else base_id
        for base_id, match in zip(base_ids, raw_matches, strict=True)
    ]
    repeated = sorted(match_id for match_id, count in Counter(match_ids).items() if count > 1)
    if repeated:
        raise ValueError(f"match_id repetido mesmo com a rodada: {repeated}")
    return match_ids


def normalize_matches(raw_matches: Sequence[RawMatch], registry: ClubRegistry, source_label: str) -> list[MatchRecord]:
    club_ids = registry.resolve_many(
        [match.home_name for match in raw_matches] + [match.away_name for match in raw_matches]
    )
    match_ids = assign_match_ids(raw_matches, club_ids)
    return [
        MatchRecord(
            match_id=match_id,
            season=raw_match.season,
            round=raw_match.round,
            match_date=raw_match.match_date,
            home_id=club_ids[raw_match.home_name.strip()],
            away_id=club_ids[raw_match.away_name.strip()],
            home_goals=raw_match.home_goals,
            away_goals=raw_match.away_goals,
            status=raw_match.status,
            source=source_label,
            source_match_id=raw_match.source_match_id,
        )
        for match_id, raw_match in zip(match_ids, raw_matches, strict=True)
    ]


def source_label_of(manifest: SourceManifest) -> str:
    return f"{manifest.source_name}@{manifest.version[:12]}"


def build_match_records(raw_dir: Path, registry: ClubRegistry) -> list[MatchRecord]:
    """Partidas do `brasileirao-dataset` (só pesquisa local e conferência)."""
    manifest = load_manifest(raw_dir)
    return normalize_matches(
        BrasileiraoDatasetSource.parse_matches(raw_dir / "matches.json"), registry, source_label_of(manifest)
    )


CARD_COLUMNS = ["season", "match_id", "club_id", "red_cards", "yellow_cards"]


def cards_by_match_frame(
    raw_cards: Sequence[RawCard], match_ids_by_source: Mapping[tuple[int, str], str], registry: ClubRegistry
) -> pd.DataFrame:
    """Cartões por clube e partida, para permitir totais "até a data de referência".

    `match_ids_by_source` liga (temporada, ID da partida na fonte) ao `match_id` estável; cartões sem
    partida correspondente ficam de fora.
    """
    known_cards = [card for card in raw_cards if (card.season, card.source_match_id) in match_ids_by_source]
    club_ids = registry.resolve_many(card.club_name for card in known_cards)
    red_counter: Counter[tuple[int, str, str]] = Counter()
    yellow_counter: Counter[tuple[int, str, str]] = Counter()
    keys: set[tuple[int, str, str]] = set()
    for card in known_cards:
        match_id = match_ids_by_source[(card.season, card.source_match_id)]
        key = (card.season, match_id, club_ids[card.club_name.strip()])
        keys.add(key)
        color = card.card_color.strip().lower()
        if color.startswith("vermelh"):
            red_counter[key] += 1
        elif color.startswith("amarel"):
            yellow_counter[key] += 1
    if len(known_cards) != len(raw_cards):
        LOGGER.info("cards_without_match", extra={"n_cards": len(raw_cards) - len(known_cards)})
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
    return pd.DataFrame(rows, columns=CARD_COLUMNS)


def build_cards_by_match(raw_dir: Path, registry: ClubRegistry) -> pd.DataFrame:
    match_records = build_match_records(raw_dir, registry)
    match_ids_by_source = {(record.season, record.source_match_id): record.match_id for record in match_records}
    return cards_by_match_frame(
        BrasileiraoDatasetSource.parse_cards(raw_dir / "cards.json"), match_ids_by_source, registry
    )


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


def _correction_log_entries(outcomes: Sequence[CorrectionOutcome]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for outcome in outcomes:
        extra = {"match_id": outcome.correction.match_id, "action": outcome.action.value}
        if outcome.action == CorrectionAction.APPLIED:
            LOGGER.info("manual_correction_applied", extra=extra)
            continue
        entry = {
            "match_id": outcome.correction.match_id,
            "reason": outcome.action.value,
            "found": str(outcome.found),
            "expected_source": str(outcome.correction.source_result),
            "evidence_url": outcome.correction.evidence_url,
        }
        if outcome.action == CorrectionAction.SOURCE_AGREES:
            LOGGER.info("manual_correction_redundant", extra=extra)
            entries.append({**entry, "change": "manual_correction_redundant"})
        else:
            LOGGER.warning("manual_correction_not_applied", extra=extra)
            entries.append({**entry, "change": "manual_correction_not_applied"})
    return entries


def append_changes(silver_dir: Path, entries: Sequence[Mapping[str, str]], stamp: str | None = None) -> None:
    if not entries:
        return
    detected_at = stamp or datetime.now(tz=UTC).isoformat()
    with (silver_dir / "changes.jsonl").open("a", encoding="utf-8") as change_log:
        for entry in entries:
            change_log.write(json.dumps({"detected_at": detected_at, **entry}, ensure_ascii=False) + "\n")


def write_silver_frames(
    matches_data: pd.DataFrame,
    cards_data: pd.DataFrame,
    silver_dir: Path,
    corrections: Sequence[ManualCorrection] = (),
) -> pd.DataFrame:
    """Aplica correções manuais, registra no `changes.jsonl` o que mudou e grava a camada silver.

    Correções redundantes (a fonte já concorda) e não aplicadas (conflito) também vão para o
    `changes.jsonl`. Mudanças causadas por correção saem com `origin = manual_correction` e a URL.
    """
    silver_dir.mkdir(parents=True, exist_ok=True)
    matches_data, outcomes = apply_corrections(matches_data, corrections)
    applied = {
        outcome.correction.match_id: outcome.correction
        for outcome in outcomes
        if outcome.action == CorrectionAction.APPLIED
    }
    stamp = datetime.now(tz=UTC).isoformat()
    log_entries = _correction_log_entries(outcomes)
    matches_path = silver_dir / "matches.csv"
    if matches_path.exists():
        changes = detect_changes(read_matches(matches_path), matches_data)
        for change in changes:
            correction = applied.get(change["match_id"])
            provenance = (
                {
                    "origin": "manual_correction",
                    "evidence_name": correction.evidence_name,
                    "evidence_url": correction.evidence_url,
                    "checked_at": correction.checked_at.isoformat(),
                }
                if correction is not None
                else {}
            )
            log_entries.append({**change, **provenance})
        LOGGER.info("silver_changes", extra={"n_changes": len(changes)})
    append_changes(silver_dir, log_entries, stamp)
    matches_data.to_csv(matches_path, index=False)
    cards_data.to_csv(silver_dir / "cards_by_match.csv", index=False)
    LOGGER.info("silver_written", extra={"n_matches": len(matches_data)})
    return matches_data


def write_silver(
    raw_dir: Path,
    registry: ClubRegistry,
    silver_dir: Path,
    corrections: Sequence[ManualCorrection] = (),
) -> pd.DataFrame:
    """Caminho de pesquisa: camada silver só do `brasileirao-dataset` (nunca publicável, ADR-0008)."""
    match_records = build_match_records(raw_dir, registry)
    match_ids_by_source = {(record.season, record.source_match_id): record.match_id for record in match_records}
    cards_data = cards_by_match_frame(
        BrasileiraoDatasetSource.parse_cards(raw_dir / "cards.json"), match_ids_by_source, registry
    )
    return write_silver_frames(matches_to_frame(match_records), cards_data, silver_dir, corrections)


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
