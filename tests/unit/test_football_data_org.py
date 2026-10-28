"""Adaptador football-data.org (ADR-0008, passo 2). Só fixtures SINTÉTICAS; nenhuma chamada real."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from brasileirao.contracts import LicenseStatus, MatchStatus
from brasileirao.data_pipeline.football_data_org import (
    TOKEN_ENVIRONMENT_VARIABLE,
    AwardedMatchError,
    FootballDataOrgError,
    FootballDataOrgSource,
    MissingTokenError,
    brasilia_date,
)
from brasileirao.data_pipeline.ingest import ingest_raw, load_manifest, sha256_of
from brasileirao.logging_utils import JsonFormatter

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "football_data_org_synthetic.json"
SYNTHETIC_TOKEN = "synthetic-token-never-real-0123456789"


def _payload() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return payload


def _parsed(awarded: Mapping[str, tuple[int, int]] | None = None) -> dict[str, Any]:
    return {match.source_match_id: match for match in FootballDataOrgSource.parse_matches(_payload(), 2032, awarded)}


@dataclass
class FakeResponse:
    status_code: int
    content: bytes = b'{"matches": []}'
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class FakeApi:
    responses: list[FakeResponse]
    calls: list[tuple[str, dict[str, Any], dict[str, str]]] = field(default_factory=list)
    sleeps: list[float] = field(default_factory=list)
    clock: float = 0.0

    def get(self, url: str, params: Mapping[str, Any], headers: Mapping[str, str]) -> FakeResponse:
        self.calls.append((url, dict(params), dict(headers)))
        return self.responses.pop(0)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.clock += seconds

    def monotonic(self) -> float:
        return self.clock

    def source(self) -> FootballDataOrgSource:
        moments = iter(datetime(2032, 10, 27, 12, tzinfo=UTC) + timedelta(seconds=step) for step in range(100))
        return FootballDataOrgSource(
            SYNTHETIC_TOKEN,
            http_get=self.get,
            sleep=self.sleep,
            monotonic=self.monotonic,
            now=lambda: next(moments),
        )


def _ok(payload: dict[str, Any] | None = None) -> FakeResponse:
    return FakeResponse(200, json.dumps(payload or _payload()).encode("utf-8"))


def test_late_kickoff_utc_falls_on_brasilia_previous_day() -> None:
    assert brasilia_date("2026-10-27T00:30:00Z") == date(2026, 10, 26)


def test_evening_kickoff_stays_on_same_day() -> None:
    assert brasilia_date("2026-10-26T23:00:00Z") == date(2026, 10, 26)


def test_historical_daylight_saving_offset_is_utc_minus_two() -> None:
    assert brasilia_date("2018-11-11T02:30:00Z") == date(2018, 11, 11)


def test_same_instant_without_daylight_saving_is_utc_minus_three() -> None:
    assert brasilia_date("2026-11-11T02:30:00Z") == date(2026, 11, 10)


def test_parser_uses_brasilia_date() -> None:
    assert _parsed()["101"].match_date == date(2032, 10, 26)


def test_finished_match_keeps_full_time_score() -> None:
    match = _parsed()["101"]
    assert (match.status, match.home_goals, match.away_goals) == (MatchStatus.FINISHED, 2, 1)


def test_in_play_partial_score_is_dropped() -> None:
    match = _parsed()["102"]
    assert (match.status, match.home_goals, match.away_goals) == (MatchStatus.SCHEDULED, None, None)


def test_paused_partial_score_is_dropped() -> None:
    match = _parsed()["103"]
    assert (match.status, match.home_goals) == (MatchStatus.SCHEDULED, None)


def test_postponed_stays_without_score() -> None:
    match = _parsed()["104"]
    assert (match.status, match.home_goals) == (MatchStatus.POSTPONED, None)


def _awarded_payload() -> dict[str, Any]:
    payload = _payload()
    payload["matches"][0] = {**payload["matches"][0], "status": "AWARDED"}
    return payload


def test_awarded_without_known_exception_fails() -> None:
    with pytest.raises(AwardedMatchError):
        FootballDataOrgSource.parse_matches(_awarded_payload(), 2032)


def test_awarded_with_known_exception_uses_decided_score() -> None:
    parsed = FootballDataOrgSource.parse_matches(_awarded_payload(), 2032, {"101": (3, 0)})
    assert (parsed[0].status, parsed[0].home_goals, parsed[0].away_goals) == (MatchStatus.FINISHED, 3, 0)


def test_unknown_status_fails() -> None:
    payload = _payload()
    payload["matches"][0] = {**payload["matches"][0], "status": "SOMETHING_NEW"}
    with pytest.raises(FootballDataOrgError):
        FootballDataOrgSource.parse_matches(payload, 2032)


def test_extra_time_result_is_rejected() -> None:
    payload = _payload()
    payload["matches"][0] = {**payload["matches"][0], "score": {"duration": "EXTRA_TIME", "fullTime": {}}}
    with pytest.raises(FootballDataOrgError):
        FootballDataOrgSource.parse_matches(payload, 2032)


def test_token_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENVIRONMENT_VARIABLE, SYNTHETIC_TOKEN)
    assert isinstance(FootballDataOrgSource.from_environment(), FootballDataOrgSource)


def test_missing_token_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_ENVIRONMENT_VARIABLE, raising=False)
    with pytest.raises(MissingTokenError):
        FootballDataOrgSource.from_environment()


def test_repr_hides_token() -> None:
    assert SYNTHETIC_TOKEN not in repr(FakeApi([]).source())


def test_token_is_sent_only_in_header() -> None:
    api = FakeApi([_ok()])
    api.source().fetch_season_payload(2032)
    assert api.calls[0][2] == {"X-Auth-Token": SYNTHETIC_TOKEN}


def test_token_never_reaches_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    api = FakeApi([FakeResponse(429, headers={"X-RequestCounter-Reset": "3"}), _ok()])
    with caplog.at_level(logging.DEBUG):
        ingest_raw(api.source().fetch([2032], tmp_path), tmp_path)
    formatter = JsonFormatter()
    assert SYNTHETIC_TOKEN not in "\n".join(formatter.format(record) for record in caplog.records)


def test_http_error_message_hides_token() -> None:
    api = FakeApi([FakeResponse(500)])
    with pytest.raises(FootballDataOrgError) as error:
        api.source().fetch_season_payload(2032)
    assert SYNTHETIC_TOKEN not in str(error.value)


def test_consecutive_calls_wait_six_seconds() -> None:
    api = FakeApi([_ok(), _ok()])
    source = api.source()
    source.fetch_season_payload(2031)
    source.fetch_season_payload(2032)
    assert api.sleeps == [6.0]


def test_rate_limit_waits_for_counter_reset() -> None:
    api = FakeApi([FakeResponse(429, headers={"X-RequestCounter-Reset": "17"}), _ok()])
    api.source().fetch_season_payload(2032)
    assert api.sleeps[0] == 17.0


def test_persistent_rate_limit_fails() -> None:
    api = FakeApi([FakeResponse(429, headers={"X-RequestCounter-Reset": "1"}) for _ in range(4)])
    with pytest.raises(FootballDataOrgError):
        api.source().fetch_season_payload(2032)


def test_fetch_keeps_raw_payload_byte_for_byte(tmp_path: Path) -> None:
    response = _ok()
    raw_dir = ingest_raw(FakeApi([response]).source().fetch([2032], tmp_path), tmp_path)
    assert (raw_dir / "matches_2032.json").read_bytes() == response.content


def test_manifest_records_sha256_of_payload(tmp_path: Path) -> None:
    raw_dir = ingest_raw(FakeApi([_ok()]).source().fetch([2032], tmp_path), tmp_path)
    assert load_manifest(raw_dir).files["matches_2032.json"] == sha256_of(raw_dir / "matches_2032.json")


def test_manifest_is_licensed_with_exact_attribution(tmp_path: Path) -> None:
    manifest = load_manifest(ingest_raw(FakeApi([_ok()]).source().fetch([2032], tmp_path), tmp_path))
    assert (manifest.license_status, manifest.attribution) == (
        LicenseStatus.LICENSED_WITH_ATTRIBUTION,
        "Football data provided by the Football-Data.org API",
    )


def test_retrieved_at_is_recorded_per_request(tmp_path: Path) -> None:
    raw_dir = ingest_raw(FakeApi([_ok(), _ok()]).source().fetch([2031, 2032], tmp_path), tmp_path)
    requests = json.loads((raw_dir / "requests.json").read_text(encoding="utf-8"))
    assert len({request["retrieved_at"] for request in requests}) == 2


def test_awarded_without_exception_writes_nothing(tmp_path: Path) -> None:
    with pytest.raises(AwardedMatchError):
        FakeApi([_ok(_awarded_payload())]).source().fetch([2032], tmp_path)
    assert not (tmp_path / "football_data_org").exists()


def test_raw_dir_round_trip_parses_payload(tmp_path: Path) -> None:
    raw_dir = ingest_raw(FakeApi([_ok()]).source().fetch([2032], tmp_path), tmp_path)
    assert len(FootballDataOrgSource.parse_raw_dir(raw_dir)) == len(_payload()["matches"])
