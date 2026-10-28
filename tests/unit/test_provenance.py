"""Proveniência do snapshot por várias fontes (ADR-0008, passo 10). Dados SINTÉTICOS."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brasileirao.config import SNAPSHOT_SCHEMA_VERSION
from brasileirao.data_pipeline.composition import CompositionMode
from brasileirao.data_pipeline.football_data_org import FootballDataOrgSource
from brasileirao.provenance import (
    RESEARCH_WARNING,
    ProvenanceError,
    build_data_info,
    load_data_info,
    load_data_sources,
)
from brasileirao.storage.schema import DataInfo, DataSourceInfo
from tests.fixtures.provenance import (
    CURRENT_SOURCE,
    HISTORY_SOURCE,
    RESEARCH_SOURCE,
    write_synthetic_composition,
)

LEGACY_DATA_INFO = {
    "source": "brasileirao_dataset (https://example.org/synthetic)",
    "version": "synthetic-legacy",
    "license_status": "research_only_unverified",
    "retrieved_at": "2032-10-01T00:00:00+00:00",
    "warnings": [],
}


def _paths(root: Path) -> tuple[Path, Path]:
    return root / "data" / "silver", root / "data" / "raw"


@pytest.fixture
def publication_root(tmp_path: Path) -> Path:
    write_synthetic_composition(tmp_path)
    return tmp_path


def _info(root: Path, mode: CompositionMode = CompositionMode.PUBLICATION) -> DataInfo:
    silver, raw = _paths(root)
    return load_data_info(silver, raw, mode, [])


def test_schema_version_bumped_for_sources() -> None:
    assert SNAPSHOT_SCHEMA_VERSION == "1.2"


def test_one_entry_per_source(publication_root: Path) -> None:
    assert [source.source_name for source in _info(publication_root).sources] == [HISTORY_SOURCE, CURRENT_SOURCE]


def test_sources_carry_their_seasons(publication_root: Path) -> None:
    assert {source.source_name: source.seasons for source in _info(publication_root).sources} == {
        HISTORY_SOURCE: [2030, 2031],
        CURRENT_SOURCE: [2032],
    }


def test_exact_attribution_reaches_data_info(publication_root: Path) -> None:
    attributions = {source.source_name: source.attribution for source in _info(publication_root).sources}
    assert attributions[CURRENT_SOURCE] == "Football data provided by the Football-Data.org API"


def test_composite_version_names_each_source(publication_root: Path) -> None:
    assert _info(publication_root).version == (
        f"{HISTORY_SOURCE}@synthetic-{HISTORY_SOURCE}-v1+{CURRENT_SOURCE}@synthetic-{CURRENT_SOURCE}-v1"
    )


def test_aggregate_license_of_publishable_sources(publication_root: Path) -> None:
    assert _info(publication_root).license_status == "licensed_with_attribution"


def test_retrieved_at_is_latest_collection(publication_root: Path) -> None:
    assert _info(publication_root).retrieved_at.startswith("2032-10-21")


def test_publication_mode_recorded(publication_root: Path) -> None:
    assert _info(publication_root).composition_mode == "publication"


def test_missing_sources_json_fails(tmp_path: Path) -> None:
    silver, raw = _paths(tmp_path)
    with pytest.raises(ProvenanceError, match=r"sources.json"):
        load_data_sources(silver, raw)


def test_research_composition_fails_in_publication_mode(tmp_path: Path) -> None:
    write_synthetic_composition(tmp_path, {2032: RESEARCH_SOURCE}, CompositionMode.RESEARCH)
    with pytest.raises(ProvenanceError, match="mode=research"):
        _info(tmp_path)


def test_research_composition_allowed_explicitly(tmp_path: Path) -> None:
    write_synthetic_composition(tmp_path, {2032: RESEARCH_SOURCE}, CompositionMode.RESEARCH)
    assert _info(tmp_path, CompositionMode.RESEARCH).license_status == "research_only_unverified"


def test_research_snapshot_warns_it_is_not_publishable(tmp_path: Path) -> None:
    write_synthetic_composition(tmp_path, {2032: RESEARCH_SOURCE}, CompositionMode.RESEARCH)
    assert RESEARCH_WARNING in _info(tmp_path, CompositionMode.RESEARCH).warnings


def test_mixed_composition_takes_most_restrictive_license(tmp_path: Path) -> None:
    write_synthetic_composition(tmp_path, {2031: HISTORY_SOURCE, 2032: RESEARCH_SOURCE}, CompositionMode.RESEARCH)
    assert _info(tmp_path, CompositionMode.RESEARCH).license_status == "research_only_unverified"


def test_manifest_changed_after_composition_fails(publication_root: Path) -> None:
    manifest_path = next((publication_root / "data" / "raw" / CURRENT_SOURCE).glob("*/manifest.json"))
    manifest_path.write_text(manifest_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ProvenanceError, match="mudou depois da composição"):
        _info(publication_root)


def test_missing_manifest_fails(publication_root: Path) -> None:
    next((publication_root / "data" / "raw" / HISTORY_SOURCE).glob("*/manifest.json")).unlink()
    with pytest.raises(ProvenanceError, match="não existe"):
        _info(publication_root)


def test_unknown_mode_fails(publication_root: Path) -> None:
    sources_path = publication_root / "data" / "silver" / "sources.json"
    document = json.loads(sources_path.read_text(encoding="utf-8"))
    sources_path.write_text(json.dumps({**document, "mode": "draft"}), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="desconhecido"):
        _info(publication_root)


def test_build_data_info_requires_sources() -> None:
    with pytest.raises(ProvenanceError):
        build_data_info([], CompositionMode.PUBLICATION, [])


def test_legacy_data_info_gets_single_source_entry() -> None:
    assert len(DataInfo.model_validate(LEGACY_DATA_INFO).sources) == 1


def test_legacy_source_name_parsed_from_label() -> None:
    assert DataInfo.model_validate(LEGACY_DATA_INFO).sources[0].source_name == "brasileirao_dataset"


def test_legacy_source_has_no_seasons() -> None:
    assert DataInfo.model_validate(LEGACY_DATA_INFO).sources[0].seasons == []


def test_legacy_data_info_has_no_composition_mode() -> None:
    assert DataInfo.model_validate(LEGACY_DATA_INFO).composition_mode is None


def test_aggregate_license_must_match_sources() -> None:
    source = DataSourceInfo(
        source_name=FootballDataOrgSource.source_name,
        origin="https://example.org/synthetic",
        version="synthetic",
        seasons=[2032],
        retrieved_at="2032-10-01T00:00:00+00:00",
        license_status="research_only_unverified",
        allowed_uses=["research_local"],
    )
    with pytest.raises(ValueError, match="mais restritivo"):
        DataInfo(
            source="synthetic",
            version="synthetic",
            license_status="licensed_with_attribution",
            retrieved_at="2032-10-01T00:00:00+00:00",
            warnings=[],
            composition_mode="publication",
            sources=[source],
        )
