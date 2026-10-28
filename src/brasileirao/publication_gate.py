"""Gate de publicação do ADR-0008 (G1 a G5), chamado pelo workflow do 07 antes do deploy.

Cada checagem devolve uma lista de achados; lista vazia é aprovação. As mensagens só levam contagens,
nomes de fonte e até 5 `match_id` (sem placar), para poderem sair em log público.

- G1: cada linha do gold vem da fonte de publicação da temporada, com `public_display_derived` e
  licença publicável; a composição é de publicação (N8).
- G2: linha com correção manual traz evidência (URL) e data.
- G3: `data.sources` do snapshot exportado cobre as temporadas de treino e a exibida, com licença
  agregada publicável.
- G4: o texto exato de atribuição de cada fonte `licensed_with_attribution` está no export
  (`data.sources`) e no HTML servido.
- G5: o artefato só tem o site estático e o export; nada de SQLite, CSV, raw, silver ou gold.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from brasileirao.contracts import PUBLISHABLE_LICENSE_STATUSES, AllowedUse, LicenseStatus
from brasileirao.data_pipeline.composition import CompositionMode
from brasileirao.data_pipeline.ingest import read_matches

MANUAL_CORRECTION_MARKER = "+manual_correction@"
FORBIDDEN_SUFFIXES = frozenset({".sqlite", ".sqlite3", ".db", ".csv", ".parquet", ".jsonl", ".env"})
FORBIDDEN_DIRECTORIES = frozenset({"raw", "silver", "gold", "snapshots", "editorial"})
MAX_LISTED = 5


@dataclass(frozen=True)
class GateFinding:
    rule: str
    detail: str


def _listed(items: Iterable[str]) -> str:
    values = sorted(set(items))
    suffix = f" (+{len(values) - MAX_LISTED})" if len(values) > MAX_LISTED else ""
    return ", ".join(values[:MAX_LISTED]) + suffix


def base_source_of(source_label: str) -> str:
    """`football_data_org@v4-...+manual_correction@<url>:<data>` → `football_data_org`."""
    return source_label.split("+", 1)[0].split("@", 1)[0]


def _publishable_entry(entry: dict[str, Any]) -> bool:
    return str(entry.get("license_status")) in {
        status.value for status in PUBLISHABLE_LICENSE_STATUSES
    } and AllowedUse.PUBLIC_DISPLAY_DERIVED.value in (entry.get("allowed_uses") or [])


def check_g1_gold_sources(matches_data: pd.DataFrame, composition: dict[str, Any]) -> list[GateFinding]:
    findings: list[GateFinding] = []
    if composition.get("mode") != CompositionMode.PUBLICATION.value:
        findings.append(GateFinding("G1", f"sources.json com mode={composition.get('mode')!r}, exigido publication"))
    entries = {str(entry["source_name"]): entry for entry in composition.get("sources") or []}
    season_sources = {
        int(season): str(item["source_name"]) for season, item in (composition.get("seasons") or {}).items()
    }
    if not len(matches_data):
        return [*findings, GateFinding("G1", "gold sem partidas")]
    base_sources = matches_data["source"].astype(str).map(base_source_of)
    seasons = matches_data["season"].astype(int)
    unknown = matches_data.loc[~base_sources.isin(list(entries)), "match_id"].astype(str)
    if len(unknown):
        findings.append(GateFinding("G1", f"{len(unknown)} linhas de fonte fora da composição: {_listed(unknown)}"))
    blocked_sources = sorted(name for name, entry in entries.items() if not _publishable_entry(entry))
    blocked = matches_data.loc[base_sources.isin(blocked_sources), "match_id"].astype(str)
    if len(blocked):
        findings.append(
            GateFinding(
                "G1",
                f"{len(blocked)} linhas de fonte sem public_display_derived ({', '.join(blocked_sources)}): "
                f"{_listed(blocked)}",
            )
        )
    expected = seasons.map(season_sources)
    misplaced = matches_data.loc[expected.notna() & (expected != base_sources), "match_id"].astype(str)
    if len(misplaced):
        findings.append(
            GateFinding(
                "G1", f"{len(misplaced)} linhas com fonte diferente da composição da temporada: {_listed(misplaced)}"
            )
        )
    uncovered = sorted(set(seasons) - set(season_sources))
    if uncovered:
        findings.append(GateFinding("G1", f"temporadas do gold sem fonte na composição: {uncovered}"))
    return findings


def _has_evidence(source_label: str) -> bool:
    evidence = source_label.split(MANUAL_CORRECTION_MARKER, 1)[1]
    url, _, checked_on = evidence.rpartition(":")
    return url.startswith(("https://", "http://")) and bool(checked_on.strip())


def check_g2_manual_corrections(matches_data: pd.DataFrame) -> list[GateFinding]:
    labels = matches_data["source"].astype(str)
    corrected = matches_data.loc[labels.str.contains(MANUAL_CORRECTION_MARKER, regex=False)]
    without_evidence = corrected.loc[~corrected["source"].astype(str).map(_has_evidence), "match_id"].astype(str)
    if not len(without_evidence):
        return []
    return [
        GateFinding("G2", f"{len(without_evidence)} correções sem URL de evidência e data: {_listed(without_evidence)}")
    ]


def check_g3_snapshot_sources(snapshot: dict[str, Any]) -> list[GateFinding]:
    findings: list[GateFinding] = []
    data = snapshot.get("data") or {}
    if data.get("composition_mode") != CompositionMode.PUBLICATION.value:
        findings.append(GateFinding("G3", f"snapshot com composition_mode={data.get('composition_mode')!r}"))
    if data.get("license_status") not in {status.value for status in PUBLISHABLE_LICENSE_STATUSES}:
        findings.append(GateFinding("G3", f"data.license_status={data.get('license_status')!r} não publicável"))
    covered = {int(season) for source in data.get("sources") or [] for season in source.get("seasons") or []}
    required = {int(season) for season in (snapshot.get("model") or {}).get("training_seasons") or []}
    required.add(int(snapshot["season"]))
    missing = sorted(required - covered)
    if missing:
        findings.append(GateFinding("G3", f"temporadas de treino ou exibida sem fonte em data.sources: {missing}"))
    return findings


def required_attributions(snapshot: dict[str, Any]) -> dict[str, str | None]:
    return {
        str(source.get("source_name")): source.get("attribution")
        for source in (snapshot.get("data") or {}).get("sources") or []
        if source.get("license_status") == LicenseStatus.LICENSED_WITH_ATTRIBUTION.value
    }


def _visible_text(markup: str) -> str:
    """Texto sem marcação, com entidades resolvidas e espaços colapsados (para comparar a atribuição)."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def check_g4_attribution(snapshot: dict[str, Any], html_texts: Iterable[str]) -> list[GateFinding]:
    """G4 no export e no HTML. O rodapé é dos Agentes 05/08; até lá a parte do HTML reprova."""
    findings: list[GateFinding] = []
    pages = _visible_text("\n".join(html_texts))
    for source_name, attribution in sorted(required_attributions(snapshot).items()):
        if not attribution or not attribution.strip():
            findings.append(GateFinding("G4", f"{source_name}: sem texto de atribuição em data.sources"))
        elif _visible_text(attribution) not in pages:
            findings.append(GateFinding("G4", f"{source_name}: atribuição exata ausente do HTML servido"))
    return findings


def check_g5_artifact(artifact_dir: Path) -> list[GateFinding]:
    forbidden = [
        path.relative_to(artifact_dir).as_posix()
        for path in artifact_dir.rglob("*")
        if path.is_file()
        and (
            path.suffix.lower() in FORBIDDEN_SUFFIXES
            or FORBIDDEN_DIRECTORIES.intersection(part.lower() for part in path.relative_to(artifact_dir).parts[:-1])
        )
    ]
    if not forbidden:
        return []
    return [GateFinding("G5", f"{len(forbidden)} arquivos proibidos no artefato: {_listed(forbidden)}")]


@dataclass(frozen=True)
class GateInputs:
    gold_matches: Path
    composition: Path
    predictions: Path
    artifact_dir: Path


def run_publication_gate(inputs: GateInputs) -> list[GateFinding]:
    matches_data = read_matches(inputs.gold_matches)
    composition: dict[str, Any] = json.loads(inputs.composition.read_text(encoding="utf-8"))
    snapshot: dict[str, Any] = json.loads(inputs.predictions.read_text(encoding="utf-8"))
    html_texts = [path.read_text(encoding="utf-8") for path in sorted(inputs.artifact_dir.rglob("*.html"))]
    return [
        *check_g1_gold_sources(matches_data, composition),
        *check_g2_manual_corrections(matches_data),
        *check_g3_snapshot_sources(snapshot),
        *check_g4_attribution(snapshot, html_texts),
        *check_g5_artifact(inputs.artifact_dir),
    ]
