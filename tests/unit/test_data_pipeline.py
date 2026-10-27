from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from brasileirao.contracts import MatchRecord, MatchStatus
from brasileirao.data_pipeline.clubs import ClubRegistry, UnknownClubError
from brasileirao.data_pipeline.ingest import detect_changes
from brasileirao.data_pipeline.sources import FootballDataOrgSource
from brasileirao.data_pipeline.validation import Severity, run_quality_checks

SYNTHETIC_FOOTBALL_DATA_PAYLOAD = {
    "note": "synthetic fixture shaped like football-data.org v4; not real results",
    "matches": [
        {
            "id": 1,
            "utcDate": "2032-05-01T19:00:00Z",
            "status": "FINISHED",
            "matchday": 1,
            "homeTeam": {"name": "Sintetico 01"},
            "awayTeam": {"name": "Sintetico 02"},
            "score": {"fullTime": {"home": 2, "away": 1}},
        },
        {
            "id": 2,
            "utcDate": "2032-05-02T19:00:00Z",
            "status": "POSTPONED",
            "matchday": 1,
            "homeTeam": {"name": "Sintetico 03"},
            "awayTeam": {"name": "Sintetico 04"},
            "score": {"fullTime": {"home": None, "away": None}},
        },
    ],
}


def test_registry_resolves_source_alias(real_registry: ClubRegistry) -> None:
    assert real_registry.resolve("Botafogo-RJ") == "botafogo"


def test_registry_merges_barueri_and_prudente(real_registry: ClubRegistry) -> None:
    assert real_registry.resolve("Barueri") == real_registry.resolve("Gremio Prudente")


def test_registry_rejects_unknown_club(real_registry: ClubRegistry) -> None:
    with pytest.raises(UnknownClubError):
        real_registry.resolve_many(["Clube Inexistente FC"])


def test_finished_match_requires_score() -> None:
    with pytest.raises(ValidationError):
        MatchRecord(
            match_id="x",
            season=2030,
            match_date=date(2030, 5, 1),
            home_id="a",
            away_id="b",
            status=MatchStatus.FINISHED,
            source="s",
            source_match_id="1",
        )


def test_scheduled_match_cannot_carry_score() -> None:
    with pytest.raises(ValidationError):
        MatchRecord(
            match_id="x",
            season=2030,
            match_date=date(2030, 5, 1),
            home_id="a",
            away_id="b",
            home_goals=0,
            away_goals=0,
            status=MatchStatus.SCHEDULED,
            source="s",
            source_match_id="1",
        )


def test_football_data_parser_keeps_postponed_without_score() -> None:
    parsed = FootballDataOrgSource.parse_matches(SYNTHETIC_FOOTBALL_DATA_PAYLOAD, 2032)
    assert (parsed[1].status, parsed[1].home_goals) == (MatchStatus.POSTPONED, None)


def test_football_data_parser_reads_full_time_score() -> None:
    parsed = FootballDataOrgSource.parse_matches(SYNTHETIC_FOOTBALL_DATA_PAYLOAD, 2032)
    assert (parsed[0].home_goals, parsed[0].away_goals) == (2, 1)


def test_quality_checks_accept_complete_synthetic_seasons(synthetic_matches: pd.DataFrame) -> None:
    complete = synthetic_matches[synthetic_matches["season"] < 2032]
    report = run_quality_checks(complete, date(2040, 1, 1))
    assert not report.has_errors


def test_quality_checks_flag_duplicate_pair(synthetic_matches: pd.DataFrame) -> None:
    season = synthetic_matches[synthetic_matches["season"] == 2030].copy()
    season.loc[season.index[1], ["home_id", "away_id"]] = season.loc[season.index[0], ["home_id", "away_id"]].to_numpy()
    codes = {issue.code for issue in run_quality_checks(season, date(2040, 1, 1)).issues}
    assert "duplicate_pair" in codes


def test_quality_checks_warn_overdue_matches(synthetic_matches: pd.DataFrame) -> None:
    report = run_quality_checks(synthetic_matches, date(2040, 1, 1))
    assert any(
        issue.code == "past_date_without_result" and issue.severity == Severity.WARNING for issue in report.issues
    )


def test_known_exception_downgrades_issue(synthetic_matches: pd.DataFrame) -> None:
    report = run_quality_checks(synthetic_matches, date(2040, 1, 1), {(2032, "past_date_without_result"): "ok"})
    assert all(issue.severity == Severity.INFO for issue in report.issues)


def test_detect_changes_reports_new_result(synthetic_matches: pd.DataFrame) -> None:
    previous = synthetic_matches.copy()
    current = synthetic_matches.copy()
    pending = current.index[current["status"] == "scheduled"][0]
    current.loc[pending, ["home_goals", "away_goals", "status"]] = [1, 0, "finished"]
    changed = {change["change"] for change in detect_changes(previous, current)}
    assert {"status", "home_goals"} <= changed
