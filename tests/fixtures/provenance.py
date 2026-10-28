"""Composição e manifestos SINTÉTICOS (synthetic) para os testes de proveniência e do gate.

Os nomes de fonte e os textos de atribuição são os reais (são contrato, não dados); origem, versões,
datas e temporadas (2030–2032) são sintéticos.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from brasileirao.contracts import AllowedUse, LicenseStatus, SourceManifest
from brasileirao.data_pipeline.adaoduque import AdaoDuqueSource
from brasileirao.data_pipeline.composition import Composition, CompositionMode, SourceInput
from brasileirao.data_pipeline.football_data_org import FootballDataOrgSource

HISTORY_SOURCE = AdaoDuqueSource.source_name
CURRENT_SOURCE = FootballDataOrgSource.source_name
RESEARCH_SOURCE = "brasileirao_dataset"
SYNTHETIC_PLAN = {2030: HISTORY_SOURCE, 2031: HISTORY_SOURCE, 2032: CURRENT_SOURCE}


def synthetic_manifest(source_name: str, retrieved_at: datetime) -> SourceManifest:
    if source_name == RESEARCH_SOURCE:
        return SourceManifest(
            source_name=source_name,
            origin="https://example.org/synthetic-research",
            version="synthetic-research-v1",
            retrieved_at=retrieved_at,
            files={},
            license_status=LicenseStatus.RESEARCH_ONLY_UNVERIFIED,
            license_notes="synthetic",
            allowed_uses=[AllowedUse.RESEARCH_LOCAL, AllowedUse.PROTOTYPE_LOCAL],
        )
    attribution = AdaoDuqueSource.attribution if source_name == HISTORY_SOURCE else FootballDataOrgSource.attribution
    return SourceManifest(
        source_name=source_name,
        origin=f"https://example.org/synthetic-{source_name}",
        version=f"synthetic-{source_name}-v1",
        retrieved_at=retrieved_at,
        files={},
        license_status=LicenseStatus.LICENSED_WITH_ATTRIBUTION,
        license_notes="synthetic",
        allowed_uses=[AllowedUse.RESEARCH_LOCAL, AllowedUse.PUBLIC_DISPLAY_DERIVED],
        license_name="Synthetic license",
        terms_url="https://example.org/synthetic-terms",
        terms_checked_at=date(2032, 1, 1),
        attribution=attribution,
    )


def write_synthetic_composition(
    root: Path,
    plan: dict[int, str] | None = None,
    mode: CompositionMode = CompositionMode.PUBLICATION,
) -> dict[str, object]:
    """Grava `data/raw/<fonte>/<versão>/manifest.json` e `data/silver/sources.json` sob `root`."""
    season_sources = plan or SYNTHETIC_PLAN
    inputs: dict[str, SourceInput] = {}
    for offset, source_name in enumerate(sorted(set(season_sources.values()))):
        manifest = synthetic_manifest(source_name, datetime(2032, 10, 20 + offset, 12, tzinfo=UTC))
        raw_dir = root / "data" / "raw" / source_name / manifest.version
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        inputs[source_name] = SourceInput(raw_dir, manifest, ())
    composition = Composition(mode, [], pd.DataFrame(), dict(season_sources), inputs)
    document = composition.sources_document()
    silver_dir = root / "data" / "silver"
    silver_dir.mkdir(parents=True, exist_ok=True)
    (silver_dir / "sources.json").write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
    return document


def label_gold_sources(matches_data: pd.DataFrame, plan: dict[int, str] | None = None) -> pd.DataFrame:
    """Coluna `source` do gold como a ingestão grava (`<fonte>@<versão[:12]>`), pela composição."""
    season_sources = plan or SYNTHETIC_PLAN
    labelled = matches_data.copy()
    labelled["source"] = labelled["season"].map(lambda season: f"{season_sources[int(season)]}@synthetic-v1")
    return labelled
