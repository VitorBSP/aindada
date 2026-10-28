"""Horário do jogo no silver e no gold (ADR-0009, Decisão 2). Só fixtures SINTÉTICAS."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError

from brasileirao.contracts import MatchRecord, MatchStatus
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.data_pipeline.football_data_org import FootballDataOrgSource, kickoff_of
from brasileirao.data_pipeline.ingest import (
    confirmed_kickoff_utc,
    detect_changes,
    matches_to_frame,
    normalize_matches,
    read_matches,
    write_gold,
    write_silver_frames,
)
from brasileirao.data_pipeline.sources import RawMatch
from brasileirao.data_pipeline.validation import kickoff_issues

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "football_data_org_synthetic.json"
NIGHT_KICKOFF = datetime(2032, 11, 2, 0, 30, tzinfo=UTC)


def _parsed() -> dict[str, RawMatch]:
    payload: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {match.source_match_id: match for match in FootballDataOrgSource.parse_matches(payload, 2032)}


def _record(**overrides: Any) -> MatchRecord:
    fields: dict[str, Any] = {
        "match_id": "2032-a-b",
        "season": 2032,
        "match_date": date(2032, 11, 1),
        "home_id": "a",
        "away_id": "b",
        "status": MatchStatus.SCHEDULED,
        "source": "synthetic",
        "source_match_id": "1",
        "kickoff_utc": NIGHT_KICKOFF,
        "kickoff_time_confirmed": True,
    }
    return MatchRecord(**{**fields, **overrides})


def _frame(synthetic_registry: ClubRegistry) -> pd.DataFrame:
    return matches_to_frame(normalize_matches(list(_parsed().values()), synthetic_registry, "synthetic"))


def test_timed_night_match_keeps_utc_kickoff() -> None:
    assert _parsed()["105"].kickoff_utc == NIGHT_KICKOFF


def test_timed_night_match_is_dated_on_brasilia_previous_day() -> None:
    assert _parsed()["105"].match_date == date(2032, 11, 1)


def test_timed_kickoff_is_confirmed() -> None:
    assert _parsed()["105"].kickoff_time_confirmed is True


def test_finished_kickoff_is_confirmed() -> None:
    assert _parsed()["101"].kickoff_time_confirmed is True


def test_in_play_keeps_kickoff_without_partial_score() -> None:
    match = _parsed()["102"]
    assert (match.kickoff_time_confirmed, match.home_goals) == (True, None)


def test_scheduled_date_only_has_no_kickoff() -> None:
    assert _parsed()["106"].kickoff_utc is None


def test_scheduled_date_only_keeps_source_date() -> None:
    assert _parsed()["106"].match_date == date(2032, 11, 10)


def test_scheduled_date_only_is_not_confirmed() -> None:
    assert _parsed()["106"].kickoff_time_confirmed is False


def test_scheduled_with_provisional_time_is_not_confirmed() -> None:
    match = _parsed()["107"]
    assert (match.kickoff_utc, match.kickoff_time_confirmed) == (datetime(2032, 11, 11, 19, 0, tzinfo=UTC), False)


def test_postponed_keeps_original_time_as_unconfirmed() -> None:
    assert _parsed()["104"].kickoff_time_confirmed is False


def test_timed_midnight_utc_is_a_real_kickoff() -> None:
    assert kickoff_of("2032-11-02T00:00:00Z", "TIMED").match_date == date(2032, 11, 1)


def test_record_rejects_kickoff_outside_match_date() -> None:
    with pytest.raises(ValidationError):
        _record(match_date=date(2032, 11, 2))


def test_record_rejects_naive_kickoff() -> None:
    with pytest.raises(ValidationError):
        _record(kickoff_utc=datetime(2032, 11, 1, 21, 30))


def test_record_rejects_kickoff_without_confirmation_flag() -> None:
    with pytest.raises(ValidationError):
        _record(kickoff_time_confirmed=None)


def test_record_rejects_confirmed_flag_without_kickoff() -> None:
    with pytest.raises(ValidationError):
        _record(kickoff_utc=None)


def test_record_converts_kickoff_offset_to_utc() -> None:
    brasilia_offset = timezone(timedelta(hours=-3))
    assert _record(kickoff_utc=datetime(2032, 11, 1, 21, 30, tzinfo=brasilia_offset)).kickoff_utc == NIGHT_KICKOFF


def test_record_without_kickoff_stays_valid() -> None:
    assert _record(kickoff_utc=None, kickoff_time_confirmed=None).kickoff_utc is None


def test_silver_writes_kickoff_in_iso_utc(tmp_path: Path, synthetic_registry: ClubRegistry) -> None:
    write_silver_frames(_frame(synthetic_registry), pd.DataFrame(), tmp_path)
    silver = pd.read_csv(tmp_path / "matches.csv", dtype=str)
    assert silver.loc[silver["source_match_id"] == "105", "kickoff_utc"].item() == "2032-11-02T00:30:00Z"


def test_silver_rewrite_is_byte_identical(tmp_path: Path, synthetic_registry: ClubRegistry) -> None:
    write_silver_frames(_frame(synthetic_registry), pd.DataFrame(), tmp_path)
    first = (tmp_path / "matches.csv").read_bytes()
    write_silver_frames(_frame(synthetic_registry), pd.DataFrame(), tmp_path)
    assert (tmp_path / "matches.csv").read_bytes() == first


def test_rewrite_logs_no_kickoff_change(tmp_path: Path, synthetic_registry: ClubRegistry) -> None:
    write_silver_frames(_frame(synthetic_registry), pd.DataFrame(), tmp_path)
    write_silver_frames(_frame(synthetic_registry), pd.DataFrame(), tmp_path)
    assert not (tmp_path / "changes.jsonl").exists()


def test_gold_keeps_kickoff_columns(tmp_path: Path, synthetic_registry: ClubRegistry) -> None:
    write_silver_frames(_frame(synthetic_registry), pd.DataFrame(), tmp_path / "silver")
    write_gold(tmp_path / "silver", tmp_path / "gold")
    gold = pd.read_csv(tmp_path / "gold" / "matches_model.csv", dtype=str)
    row = gold.loc[gold["source_match_id"] == "105"]
    assert (row["kickoff_utc"].item(), row["kickoff_time_confirmed"].item()) == ("2032-11-02T00:30:00Z", "True")


def test_old_silver_without_kickoff_reads_as_missing(tmp_path: Path, synthetic_registry: ClubRegistry) -> None:
    _frame(synthetic_registry).drop(columns=["kickoff_utc", "kickoff_time_confirmed"]).to_csv(
        tmp_path / "matches.csv", index=False
    )
    assert read_matches(tmp_path / "matches.csv")["kickoff_utc"].isna().all()


def test_first_ingestion_with_kickoff_logs_no_change(synthetic_registry: ClubRegistry) -> None:
    current = _frame(synthetic_registry)
    previous = current.drop(columns=["kickoff_utc", "kickoff_time_confirmed"])
    assert detect_changes(previous, current) == []


def test_kickoff_change_is_logged(synthetic_registry: ClubRegistry) -> None:
    previous = _frame(synthetic_registry)
    current = previous.copy()
    position = current.index[current["source_match_id"] == "105"][0]
    current.loc[position, "kickoff_utc"] = "2032-11-01T22:00:00Z"
    assert [change["change"] for change in detect_changes(previous, current)] == ["kickoff_utc"]


def test_confirmation_change_is_logged(synthetic_registry: ClubRegistry) -> None:
    previous = _frame(synthetic_registry)
    current = previous.copy()
    position = current.index[current["source_match_id"] == "107"][0]
    current.loc[position, "kickoff_time_confirmed"] = True
    assert [change["change"] for change in detect_changes(previous, current)] == ["kickoff_time_confirmed"]


def test_quality_check_accepts_consistent_kickoffs(synthetic_registry: ClubRegistry) -> None:
    assert kickoff_issues(_frame(synthetic_registry)) == []


def test_quality_check_flags_kickoff_outside_match_date(synthetic_registry: ClubRegistry) -> None:
    matches_data = _frame(synthetic_registry)
    position = matches_data.index[matches_data["source_match_id"] == "105"][0]
    matches_data.loc[position, "match_date"] = pd.Timestamp("2032-11-02")
    assert [issue.code for issue in kickoff_issues(matches_data)] == ["kickoff_date_mismatch"]


def test_quality_check_ignores_frames_without_kickoff(synthetic_matches: pd.DataFrame) -> None:
    assert kickoff_issues(synthetic_matches) == []


def test_export_kickoff_only_when_confirmed() -> None:
    assert confirmed_kickoff_utc("2032-11-11T19:00:00Z", False) is None


def test_export_kickoff_when_confirmed() -> None:
    assert confirmed_kickoff_utc("2032-11-02T00:30:00Z", True) == "2032-11-02T00:30:00Z"


def test_export_kickoff_missing_values_are_none() -> None:
    assert confirmed_kickoff_utc(pd.NA, pd.NA) is None
