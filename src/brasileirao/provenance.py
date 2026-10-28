"""Proveniência do snapshot a partir da composição da silver (ADR-0008, passo 10).

`data/silver/sources.json` diz qual fonte e qual manifesto compõem cada temporada. Daqui sai o
`DataInfo` do snapshot: uma entrada por fonte, versão composta (o `data_version`) e o status de
licença mais restritivo. Em modo publicação, composição ausente ou de pesquisa faz a simulação falhar
(achado N8 do 06); o modo pesquisa só vale quando pedido explicitamente.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from brasileirao.contracts import LicenseStatus, SourceManifest, most_restrictive_license
from brasileirao.data_pipeline.composition import CompositionMode
from brasileirao.data_pipeline.ingest import sha256_of
from brasileirao.storage.schema import DataInfo, DataSourceInfo

SOURCES_FILE = "sources.json"
RESEARCH_WARNING = (
    "Composição de PESQUISA (fonte sem licença de publicação): snapshot só para uso local, nunca publicável."
)


class ProvenanceError(RuntimeError):
    """A composição ou os manifestos das fontes não sustentam o snapshot pedido."""


def read_composition(silver_dir: Path) -> dict[str, Any]:
    path = silver_dir / SOURCES_FILE
    if not path.exists():
        raise ProvenanceError(f"{path} ausente: rode `brasileirao ingest` (a composição de fontes é obrigatória)")
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


def composition_mode_of(document: dict[str, Any]) -> CompositionMode:
    try:
        return CompositionMode(str(document.get("mode")))
    except ValueError as error:
        raise ProvenanceError(f"modo de composição desconhecido em sources.json: {document.get('mode')!r}") from error


def _source_info(entry: dict[str, Any], raw_root: Path) -> DataSourceInfo:
    source_name = str(entry["source_name"])
    manifest_path = raw_root / str(entry["manifest"])
    if not manifest_path.exists():
        raise ProvenanceError(f"{source_name}: manifesto {entry['manifest']} da composição não existe em {raw_root}")
    if sha256_of(manifest_path) != entry["manifest_sha256"]:
        raise ProvenanceError(f"{source_name}: manifesto {entry['manifest']} mudou depois da composição")
    manifest = SourceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if manifest.source_name != source_name or manifest.version != entry["version"]:
        raise ProvenanceError(
            f"{source_name}: manifesto declara {manifest.source_name}@{manifest.version}, "
            f"a composição esperava {source_name}@{entry['version']}"
        )
    return DataSourceInfo(
        source_name=manifest.source_name,
        origin=manifest.origin,
        version=manifest.version,
        seasons=sorted(int(season) for season in entry["seasons"]),
        retrieved_at=manifest.retrieved_at.isoformat(),
        license_status=manifest.license_status.value,
        allowed_uses=[use.value for use in manifest.allowed_uses],
        attribution=manifest.attribution,
        license_name=manifest.license_name,
        terms_url=manifest.terms_url,
    )


def load_data_sources(
    silver_dir: Path, raw_root: Path, mode: CompositionMode = CompositionMode.PUBLICATION
) -> list[DataSourceInfo]:
    """Fontes da composição, conferidas contra os manifestos raw (SHA-256, nome e versão).

    Em `mode=publication`, a composição tem de ser de publicação. Em `mode=research`, aceita as duas.
    """
    document = read_composition(silver_dir)
    found_mode = composition_mode_of(document)
    if mode == CompositionMode.PUBLICATION and found_mode != CompositionMode.PUBLICATION:
        raise ProvenanceError(
            f"sources.json tem mode={found_mode.value}; o modo publicação exige mode=publication "
            "(use o modo pesquisa explicitamente para simular com essa composição)"
        )
    entries = document.get("sources") or []
    if not entries:
        raise ProvenanceError("sources.json sem fontes")
    sources = [_source_info(entry, raw_root) for entry in entries]
    return sorted(sources, key=lambda source: (min(source.seasons, default=0), source.source_name))


def _retrieved_at(source: DataSourceInfo) -> datetime:
    moment = datetime.fromisoformat(source.retrieved_at)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def build_data_info(sources: list[DataSourceInfo], composition_mode: CompositionMode, warnings: list[str]) -> DataInfo:
    if not sources:
        raise ProvenanceError("snapshot sem fontes")
    mode_warnings = [RESEARCH_WARNING] if composition_mode == CompositionMode.RESEARCH else []
    return DataInfo(
        source=" + ".join(f"{source.source_name} ({source.origin})" for source in sources),
        version="+".join(f"{source.source_name}@{source.version}" for source in sources),
        license_status=most_restrictive_license(LicenseStatus(source.license_status) for source in sources).value,
        retrieved_at=max(sources, key=_retrieved_at).retrieved_at,
        warnings=[*mode_warnings, *warnings],
        composition_mode=composition_mode.value,
        sources=sources,
    )


def load_data_info(silver_dir: Path, raw_root: Path, mode: CompositionMode, warnings: list[str]) -> DataInfo:
    sources = load_data_sources(silver_dir, raw_root, mode)
    found_mode = composition_mode_of(read_composition(silver_dir))
    return build_data_info(sources, found_mode, warnings)
