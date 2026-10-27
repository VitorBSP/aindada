"""Composição da camada silver por temporada, com precedência explícita de fontes (ADR-0008).

Cada temporada vem de exatamente uma fonte de publicação (`config.PUBLICATION_SOURCE_BY_SEASON`).
Temporada sem fonte, fonte sem dados da temporada ou fonte sem licença publicável fazem a ingestão
falhar: não há fallback para o `brasileirao-dataset`. A composição usada fica em
`data/silver/sources.json` (temporada → fonte → versão do manifesto).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from brasileirao.config import PUBLICATION_SOURCE_BY_SEASON
from brasileirao.contracts import MatchRecord, MatchStatus, SourceManifest
from brasileirao.data_pipeline.adaoduque import AdaoDuqueSource
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.data_pipeline.corrections import ManualCorrection
from brasileirao.data_pipeline.football_data_org import FootballDataOrgSource
from brasileirao.data_pipeline.ingest import (
    CARD_COLUMNS,
    cards_by_match_frame,
    matches_to_frame,
    normalize_matches,
    sha256_of,
    source_label_of,
    write_silver_frames,
)
from brasileirao.data_pipeline.sources import BrasileiraoDatasetSource, RawCard, RawMatch

BRASILIA = ZoneInfo("America/Sao_Paulo")
SOURCES_DOCUMENT_VERSION = "1.0"


class CompositionMode(StrEnum):
    PUBLICATION = "publication"
    RESEARCH = "research"


class CompositionError(RuntimeError):
    """A composição pedida não pode ser montada sem violar o ADR-0008."""


@dataclass(frozen=True)
class SourceInput:
    """Partidas e cartões já lidos de uma ingestão raw, com o manifesto dela."""

    raw_dir: Path
    manifest: SourceManifest
    matches: Sequence[RawMatch]
    cards: Sequence[RawCard] = field(default_factory=tuple)


def publication_source_for(
    season: int, precedence: Sequence[tuple[int, int | None, str]] = PUBLICATION_SOURCE_BY_SEASON
) -> str:
    for first_season, last_season, source_name in precedence:
        if first_season <= season and (last_season is None or season <= last_season):
            return source_name
    raise CompositionError(f"temporada {season} sem fonte de publicação em PUBLICATION_SOURCE_BY_SEASON")


def publication_plan(
    last_season: int, precedence: Sequence[tuple[int, int | None, str]] = PUBLICATION_SOURCE_BY_SEASON
) -> dict[int, str]:
    first_season = min(first for first, _, _ in precedence)
    return {season: publication_source_for(season, precedence) for season in range(first_season, last_season + 1)}


@dataclass(frozen=True)
class Composition:
    mode: CompositionMode
    records: list[MatchRecord]
    cards: pd.DataFrame
    season_sources: dict[int, str]
    inputs: dict[str, SourceInput]

    def sources_document(self) -> dict[str, object]:
        seasons_by_source: dict[str, list[int]] = {}
        for season, source_name in sorted(self.season_sources.items()):
            seasons_by_source.setdefault(source_name, []).append(season)
        counts = pd.Series([record.season for record in self.records]).value_counts()
        return {
            "document_version": SOURCES_DOCUMENT_VERSION,
            "mode": self.mode.value,
            "seasons": {
                str(season): {
                    "source_name": source_name,
                    "version": self.inputs[source_name].manifest.version,
                    "n_matches": int(counts.get(season, 0)),
                }
                for season, source_name in sorted(self.season_sources.items())
            },
            "sources": [
                {
                    "source_name": source_name,
                    "origin": source_input.manifest.origin,
                    "version": source_input.manifest.version,
                    "retrieved_at": source_input.manifest.retrieved_at.isoformat(),
                    "license_status": source_input.manifest.license_status.value,
                    "allowed_uses": [use.value for use in source_input.manifest.allowed_uses],
                    "attribution": source_input.manifest.attribution,
                    "seasons": seasons_by_source[source_name],
                    "manifest": f"{source_input.raw_dir.parent.name}/{source_input.raw_dir.name}/manifest.json",
                    "manifest_sha256": sha256_of(source_input.raw_dir / "manifest.json"),
                }
                for source_name, source_input in sorted(self.inputs.items())
                if source_name in seasons_by_source
            ],
        }


def _check_publishable(source_input: SourceInput) -> None:
    manifest = source_input.manifest
    if not manifest.allows_public_display:
        raise CompositionError(
            f"fonte {manifest.source_name} ({manifest.license_status.value}) não tem uso public_display_derived; "
            "não pode compor a camada de publicação (regra G1)"
        )


def _check_no_future_results(source_input: SourceInput, records: Sequence[MatchRecord]) -> None:
    """Nenhuma partida encerrada pode ter data posterior à coleta, no dia de Brasília."""
    collected_on: date = source_input.manifest.retrieved_at.astimezone(BRASILIA).date()
    future = [
        record.match_id
        for record in records
        if record.status == MatchStatus.FINISHED and record.match_date > collected_on
    ]
    if future:
        raise CompositionError(
            f"{source_input.manifest.source_name}: {len(future)} partidas encerradas com data posterior à coleta "
            f"({collected_on}): {future[:5]}"
        )


def compose(
    inputs: Mapping[str, SourceInput],
    season_sources: Mapping[int, str],
    registry: ClubRegistry,
    mode: CompositionMode = CompositionMode.PUBLICATION,
) -> Composition:
    used_sources = sorted(set(season_sources.values()))
    missing_inputs = [source_name for source_name in used_sources if source_name not in inputs]
    if missing_inputs:
        raise CompositionError(f"fontes sem ingestão disponível: {missing_inputs}")
    records: list[MatchRecord] = []
    card_frames: list[pd.DataFrame] = []
    for source_name in used_sources:
        source_input = inputs[source_name]
        if mode == CompositionMode.PUBLICATION:
            _check_publishable(source_input)
        wanted = {season for season, name in season_sources.items() if name == source_name}
        raw_matches = [match for match in source_input.matches if match.season in wanted]
        empty = sorted(wanted - {match.season for match in raw_matches})
        if empty:
            raise CompositionError(f"temporadas {empty} sem partidas na fonte {source_name}; sem fallback")
        source_records = normalize_matches(raw_matches, registry, source_label_of(source_input.manifest))
        _check_no_future_results(source_input, source_records)
        records.extend(source_records)
        match_ids_by_source = {(record.season, record.source_match_id): record.match_id for record in source_records}
        card_frames.append(cards_by_match_frame(source_input.cards, match_ids_by_source, registry))
    non_empty_cards = [frame for frame in card_frames if len(frame)]
    cards = (
        pd.concat(non_empty_cards, ignore_index=True).sort_values(["season", "match_id", "club_id"])
        if non_empty_cards
        else pd.DataFrame(columns=CARD_COLUMNS)
    )
    return Composition(
        mode=mode,
        records=records,
        cards=cards.reset_index(drop=True),
        season_sources=dict(season_sources),
        inputs={name: inputs[name] for name in used_sources},
    )


def write_composition(
    composition: Composition, silver_dir: Path, corrections: Sequence[ManualCorrection] = ()
) -> pd.DataFrame:
    matches_data = write_silver_frames(
        matches_to_frame(composition.records), composition.cards, silver_dir, corrections
    )
    (silver_dir / "sources.json").write_text(
        json.dumps(composition.sources_document(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return matches_data


def read_sources_document(silver_dir: Path) -> dict[str, object]:
    document: dict[str, object] = json.loads((silver_dir / "sources.json").read_text(encoding="utf-8"))
    return document


def latest_ingestion(raw_root: Path, source_name: str) -> Path:
    """Pasta raw mais recente da fonte (pela `retrieved_at` do manifesto); falha se não houver."""
    manifests = [
        (SourceManifest.model_validate_json(path.read_text(encoding="utf-8")).retrieved_at, path.parent)
        for path in (raw_root / source_name).glob("*/manifest.json")
    ]
    if not manifests:
        raise CompositionError(f"nenhuma ingestão raw de {source_name} em {raw_root / source_name}")
    return max(manifests)[1]


def load_source_input(raw_dir: Path, awarded_results: Mapping[str, tuple[int, int]] | None = None) -> SourceInput:
    """Lê uma ingestão raw (manifesto + arquivos) com o parser da fonte declarada no manifesto."""
    manifest = SourceManifest.model_validate_json((raw_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.source_name == AdaoDuqueSource.source_name:
        matches = AdaoDuqueSource.parse_matches(raw_dir / "matches.csv")
        cards_path = raw_dir / "cards.csv"
        cards = AdaoDuqueSource.parse_cards(cards_path, matches) if cards_path.exists() else []
        return SourceInput(raw_dir, manifest, matches, cards)
    if manifest.source_name == FootballDataOrgSource.source_name:
        return SourceInput(raw_dir, manifest, FootballDataOrgSource.parse_raw_dir(raw_dir, None, awarded_results))
    if manifest.source_name == BrasileiraoDatasetSource.source_name:
        return SourceInput(
            raw_dir,
            manifest,
            BrasileiraoDatasetSource.parse_matches(raw_dir / "matches.json"),
            BrasileiraoDatasetSource.parse_cards(raw_dir / "cards.json"),
        )
    raise CompositionError(f"fonte sem parser: {manifest.source_name}")


def normalized_frame(source_input: SourceInput, registry: ClubRegistry) -> pd.DataFrame:
    """Todas as temporadas de uma fonte, normalizadas com `match_id` estável (para conferência)."""
    return matches_to_frame(normalize_matches(source_input.matches, registry, source_label_of(source_input.manifest)))
