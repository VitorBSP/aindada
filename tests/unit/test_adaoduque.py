"""Adaptador Adão Duque v18 (ADR-0008, passo 3). Só a fixture SINTÉTICA de tests/fixtures/."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from brasileirao.contracts import AllowedUse, LicenseStatus, MatchStatus
from brasileirao.data_pipeline.adaoduque import (
    CARDS_FILE,
    MATCHES_FILE,
    AdaoDuqueFilesError,
    AdaoDuqueSource,
    season_of,
)
from brasileirao.data_pipeline.clubs import load_club_registry
from brasileirao.data_pipeline.ingest import ingest_raw, load_manifest, normalize_matches
from brasileirao.data_pipeline.sources import RawMatch
from tests.fixtures.synthetic import SYNTHETIC_CLUBS_CSV

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "adaoduque_synthetic"


@pytest.fixture
def landing_dir(tmp_path: Path) -> Path:
    target = tmp_path / "adaoduque" / "v18"
    target.mkdir(parents=True)
    for name in (MATCHES_FILE, CARDS_FILE):
        shutil.copyfile(FIXTURE_DIR / name, target / name)
    return target


@pytest.fixture
def pinned_source(landing_dir: Path, tmp_path: Path) -> AdaoDuqueSource:
    source = AdaoDuqueSource(landing_dir, tmp_path / "source_pins.json")
    source.pin_current_files()
    return source


def _matches() -> dict[str, RawMatch]:
    return {match.source_match_id: match for match in AdaoDuqueSource.parse_matches(FIXTURE_DIR / MATCHES_FILE)}


def test_fixture_is_marked_synthetic() -> None:
    assert "synthetic" in (FIXTURE_DIR / MATCHES_FILE).read_text(encoding="utf-8")


def test_date_is_read_as_brasilia_day_without_conversion() -> None:
    assert _matches()["2"].match_date == date(2020, 8, 9)


def test_season_2020_extends_into_february_2021() -> None:
    assert season_of(date(2021, 2, 20)) == 2020


def test_season_2021_starts_after_the_2020_window() -> None:
    assert season_of(date(2021, 5, 29)) == 2021


def test_regular_season_is_the_calendar_year() -> None:
    assert season_of(date(2003, 3, 29)) == 2003


def test_missing_score_stays_scheduled() -> None:
    match = _matches()["4"]
    assert (match.status, match.home_goals) == (MatchStatus.SCHEDULED, None)


def test_score_is_read() -> None:
    match = _matches()["1"]
    assert (match.home_goals, match.away_goals) == (2, 1)


def test_cards_of_unknown_match_are_skipped() -> None:
    matches = AdaoDuqueSource.parse_matches(FIXTURE_DIR / MATCHES_FILE)
    cards = AdaoDuqueSource.parse_cards(FIXTURE_DIR / CARDS_FILE, matches)
    assert {card.source_match_id for card in cards} == {"1"}


def test_missing_files_fail_with_clear_message(tmp_path: Path) -> None:
    with pytest.raises(AdaoDuqueFilesError, match="ausentes"):
        AdaoDuqueSource(tmp_path / "adaoduque" / "v18", tmp_path / "source_pins.json").snapshot()


def test_unpinned_hashes_fail(landing_dir: Path, tmp_path: Path) -> None:
    pins = tmp_path / "source_pins.json"
    pins.write_text(json.dumps({"adaoduque_kaggle": {"version": "kaggle-v18", "files": {}}}), encoding="utf-8")
    with pytest.raises(AdaoDuqueFilesError, match="não fixados"):
        AdaoDuqueSource(landing_dir, pins).snapshot()


def test_changed_file_fails_hash_check(pinned_source: AdaoDuqueSource, landing_dir: Path) -> None:
    with (landing_dir / MATCHES_FILE).open("a", encoding="utf-8") as matches_file:
        matches_file.write('"7","1","01/09/2021","16:00","Sintetico 05","Sintetico 06",,,,,,,"1","0","XX","XX"\n')
    with pytest.raises(AdaoDuqueFilesError, match="SHA-256"):
        pinned_source.snapshot()


def test_project_pins_target_kaggle_version_18() -> None:
    pins_path = Path(__file__).resolve().parents[2] / "data" / "reference" / "source_pins.json"
    assert json.loads(pins_path.read_text(encoding="utf-8"))["adaoduque_kaggle"]["version"] == "kaggle-v18"


def test_manifest_carries_decision_2_values(pinned_source: AdaoDuqueSource, tmp_path: Path) -> None:
    manifest = load_manifest(ingest_raw(pinned_source.snapshot(), tmp_path / "raw"))
    assert (manifest.license_status, set(manifest.allowed_uses)) == (
        LicenseStatus.LICENSED_WITH_ATTRIBUTION,
        set(AllowedUse),
    )


def test_manifest_records_sha256_per_file(pinned_source: AdaoDuqueSource, tmp_path: Path) -> None:
    manifest = load_manifest(ingest_raw(pinned_source.snapshot(), tmp_path / "raw"))
    assert set(manifest.files) == {"matches.csv", "cards.csv"}


def test_reingesting_same_files_keeps_manifest(pinned_source: AdaoDuqueSource, tmp_path: Path) -> None:
    raw_dir = ingest_raw(pinned_source.snapshot(), tmp_path / "raw")
    first = (raw_dir / "manifest.json").read_bytes()
    ingest_raw(pinned_source.snapshot(), tmp_path / "raw")
    assert (raw_dir / "manifest.json").read_bytes() == first


def test_duplicate_pair_gets_round_suffix() -> None:
    registry = load_club_registry(SYNTHETIC_CLUBS_CSV)
    records = normalize_matches(AdaoDuqueSource.parse_matches(FIXTURE_DIR / MATCHES_FILE), registry, "synthetic")
    assert {record.match_id for record in records if record.season == 2021} == {
        "2021-sintetico-01-sintetico-02-r01",
        "2021-sintetico-01-sintetico-02-r05",
    }
