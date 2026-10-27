"""Composição por temporada com precedência e sem fallback (ADR-0008, passos 5 e 6). Dados SINTÉTICOS."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from brasileirao.config import PUBLICATION_SOURCE_BY_SEASON
from brasileirao.contracts import AllowedUse, LicenseStatus, MatchStatus, SourceManifest
from brasileirao.data_pipeline.clubs import ClubRegistry, load_club_registry
from brasileirao.data_pipeline.composition import (
    CompositionError,
    CompositionMode,
    SourceInput,
    compose,
    publication_plan,
    publication_source_for,
    write_composition,
)
from brasileirao.data_pipeline.corrections import ManualCorrection
from brasileirao.data_pipeline.sources import RawMatch
from tests.fixtures.synthetic import SYNTHETIC_CLUBS_CSV

COLLECTED_AT = datetime(2032, 10, 27, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def registry() -> ClubRegistry:
    return load_club_registry(SYNTHETIC_CLUBS_CSV)


def _match(match_id: str, season: int, home: int, away: int, goals: tuple[int, int] | None, day: date) -> RawMatch:
    return RawMatch(
        source_match_id=match_id,
        season=season,
        round=1,
        match_date=day,
        home_name=f"Sintetico {home:02d}",
        away_name=f"Sintetico {away:02d}",
        home_goals=None if goals is None else goals[0],
        away_goals=None if goals is None else goals[1],
        status=MatchStatus.SCHEDULED if goals is None else MatchStatus.FINISHED,
    )


def _input(
    tmp_path: Path,
    source_name: str,
    matches: Sequence[RawMatch],
    status: LicenseStatus = LicenseStatus.LICENSED_WITH_ATTRIBUTION,
) -> SourceInput:
    publishable = status == LicenseStatus.LICENSED_WITH_ATTRIBUTION
    manifest = SourceManifest(
        source_name=source_name,
        origin="https://example.org/synthetic",
        version="synthetic-v1",
        retrieved_at=COLLECTED_AT,
        files={},
        license_status=status,
        license_notes="synthetic",
        allowed_uses=[AllowedUse.RESEARCH_LOCAL, AllowedUse.PUBLIC_DISPLAY_DERIVED]
        if publishable
        else [AllowedUse.RESEARCH_LOCAL],
        license_name="Synthetic" if publishable else None,
        terms_url="https://example.org/terms" if publishable else None,
        terms_checked_at=date(2032, 1, 1) if publishable else None,
        attribution=f"Synthetic attribution {source_name}" if publishable else None,
    )
    raw_dir = tmp_path / source_name / "synthetic-v1"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return SourceInput(raw_dir, manifest, matches)


def _history(tmp_path: Path) -> dict[str, SourceInput]:
    return {
        "synthetic_history": _input(
            tmp_path,
            "synthetic_history",
            [
                _match("h1", 2030, 1, 2, (1, 0), date(2030, 5, 1)),
                _match("h2", 2031, 2, 1, (2, 2), date(2031, 5, 1)),
                _match("h3", 2032, 3, 4, (5, 5), date(2032, 5, 1)),
            ],
        ),
        "synthetic_current": _input(
            tmp_path,
            "synthetic_current",
            [
                _match("c1", 2032, 1, 2, (0, 1), date(2032, 10, 26)),
                _match("c2", 2032, 3, 4, None, date(2032, 11, 2)),
                _match("c3", 2031, 1, 2, (4, 4), date(2031, 5, 1)),
            ],
        ),
    }


PLAN = {2030: "synthetic_history", 2031: "synthetic_history", 2032: "synthetic_current"}


def test_config_precedence_matches_adr_0008() -> None:
    assert PUBLICATION_SOURCE_BY_SEASON == ((2003, 2025, "adaoduque_kaggle"), (2026, None, "football_data_org"))


def test_history_until_2025_comes_from_adaoduque() -> None:
    assert publication_source_for(2025) == "adaoduque_kaggle"


def test_current_season_comes_from_football_data_org() -> None:
    assert publication_source_for(2026) == "football_data_org"


def test_future_seasons_stay_with_football_data_org() -> None:
    assert publication_source_for(2030) == "football_data_org"


def test_season_before_coverage_has_no_source() -> None:
    with pytest.raises(CompositionError):
        publication_source_for(2002)


def test_publication_plan_never_uses_research_source() -> None:
    assert "brasileirao_dataset" not in set(publication_plan(2026).values())


def test_publication_plan_covers_every_season() -> None:
    assert sorted(publication_plan(2026)) == list(range(2003, 2027))


def test_each_season_comes_only_from_its_source(tmp_path: Path, registry: ClubRegistry) -> None:
    composition = compose(_history(tmp_path), PLAN, registry)
    assert {(record.season, record.source.split("@")[0]) for record in composition.records} == {
        (2030, "synthetic_history"),
        (2031, "synthetic_history"),
        (2032, "synthetic_current"),
    }


def test_match_id_is_stable_across_sources(tmp_path: Path, registry: ClubRegistry) -> None:
    composition = compose(_history(tmp_path), PLAN, registry)
    assert "2032-sintetico-01-sintetico-02" in {record.match_id for record in composition.records}


def test_season_without_data_in_its_source_fails(tmp_path: Path, registry: ClubRegistry) -> None:
    with pytest.raises(CompositionError, match="sem fallback"):
        compose(_history(tmp_path), {**PLAN, 2029: "synthetic_history"}, registry)


def test_missing_source_ingestion_fails(tmp_path: Path, registry: ClubRegistry) -> None:
    inputs = _history(tmp_path)
    del inputs["synthetic_current"]
    with pytest.raises(CompositionError):
        compose(inputs, PLAN, registry)


def test_research_source_cannot_compose_publication(tmp_path: Path, registry: ClubRegistry) -> None:
    inputs = {
        "research": _input(
            tmp_path, "research", [_match("r1", 2030, 1, 2, (1, 1), date(2030, 5, 1))],
            LicenseStatus.RESEARCH_ONLY_UNVERIFIED,
        )
    }  # fmt: skip
    with pytest.raises(CompositionError, match="G1"):
        compose(inputs, {2030: "research"}, registry)


def test_research_mode_accepts_research_source(tmp_path: Path, registry: ClubRegistry) -> None:
    inputs = {
        "research": _input(
            tmp_path, "research", [_match("r1", 2030, 1, 2, (1, 1), date(2030, 5, 1))],
            LicenseStatus.RESEARCH_ONLY_UNVERIFIED,
        )
    }  # fmt: skip
    assert len(compose(inputs, {2030: "research"}, registry, CompositionMode.RESEARCH).records) == 1


def test_finished_match_after_collection_day_fails(tmp_path: Path, registry: ClubRegistry) -> None:
    inputs = {"late": _input(tmp_path, "late", [_match("l1", 2032, 1, 2, (1, 0), date(2032, 10, 28))])}
    with pytest.raises(CompositionError, match="posterior à coleta"):
        compose(inputs, {2032: "late"}, registry)


def test_sources_document_maps_season_to_source_and_version(tmp_path: Path, registry: ClubRegistry) -> None:
    document = compose(_history(tmp_path), PLAN, registry).sources_document()
    assert document["seasons"]["2032"] == {  # type: ignore[index]
        "source_name": "synthetic_current",
        "version": "synthetic-v1",
        "n_matches": 2,
    }


def test_sources_document_carries_attribution(tmp_path: Path, registry: ClubRegistry) -> None:
    document = compose(_history(tmp_path), PLAN, registry).sources_document()
    assert [source["attribution"] for source in document["sources"]] == [  # type: ignore[attr-defined]
        "Synthetic attribution synthetic_current",
        "Synthetic attribution synthetic_history",
    ]


def test_reingesting_same_input_writes_identical_files(tmp_path: Path, registry: ClubRegistry) -> None:
    silver_dir = tmp_path / "silver"
    write_composition(compose(_history(tmp_path), PLAN, registry), silver_dir)
    first = {name: (silver_dir / name).read_bytes() for name in ("matches.csv", "sources.json", "cards_by_match.csv")}
    write_composition(compose(_history(tmp_path), PLAN, registry), silver_dir)
    assert {name: (silver_dir / name).read_bytes() for name in first} == first


def _correction(home_goals: int, away_goals: int, source_goals: tuple[int, int]) -> ManualCorrection:
    return ManualCorrection(
        match_id="2032-sintetico-01-sintetico-02",
        home_id="sintetico-01",
        away_id="sintetico-02",
        source_status=MatchStatus.FINISHED,
        source_home_goals=source_goals[0],
        source_away_goals=source_goals[1],
        status=MatchStatus.FINISHED,
        home_goals=home_goals,
        away_goals=away_goals,
        evidence_name="synthetic",
        evidence_url="https://example.org/synthetic-match",
        checked_at=date(2032, 10, 27),
    )


def test_redundant_correction_is_logged_in_changes(tmp_path: Path, registry: ClubRegistry) -> None:
    silver_dir = tmp_path / "silver"
    write_composition(compose(_history(tmp_path), PLAN, registry), silver_dir, [_correction(0, 1, (0, 0))])
    entries = [json.loads(line) for line in (silver_dir / "changes.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [entry["change"] for entry in entries] == ["manual_correction_redundant"]


def test_applied_correction_keeps_base_source_in_source_column(tmp_path: Path, registry: ClubRegistry) -> None:
    silver_dir = tmp_path / "silver"
    matches_data = write_composition(
        compose(_history(tmp_path), PLAN, registry), silver_dir, [_correction(1, 1, (0, 1))]
    )
    corrected = matches_data.loc[matches_data["match_id"] == "2032-sintetico-01-sintetico-02", "source"].iloc[0]
    assert corrected == "synthetic_current+manual_correction@synthetic:2032-10-27"
