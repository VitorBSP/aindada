"""Linhas enviadas ao Supabase do simulador (ADR-0015). Jogos e clubes SINTÉTICOS."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from brasileirao import cli
from brasileirao.storage.supabase_sync import build_rows, match_lock_utc, push

NOW = datetime(2032, 11, 7, 12, 0, tzinfo=UTC)


def _predictions(statuses: tuple[str, str] = ("finished", "scheduled")) -> dict[str, Any]:
    def match(match_id: str, status: str, kickoff: str | None) -> dict[str, Any]:
        finished = status == "finished"
        return {
            "match_id": match_id,
            "round": 1,
            "match_date": "2032-11-08",
            "home_id": "sintetico-01",
            "away_id": "sintetico-02",
            "status": status,
            "home_goals": 2 if finished else None,
            "away_goals": 1 if finished else None,
            "kickoff_utc": kickoff,
        }

    return {
        "season": 2032,
        "matches": [match("syn-1", statuses[0], "2032-11-01T22:00:00+00:00"), match("syn-2", statuses[1], None)],
        "standings": [{"club_id": "sintetico-01", "position": 1}, {"club_id": "sintetico-02", "position": 2}],
    }


def test_missing_kickoff_locks_at_brasilia_midnight() -> None:
    assert match_lock_utc({"match_date": "2032-11-08", "kickoff_utc": None}) == datetime(2032, 11, 8, 3, 0, tzinfo=UTC)


def test_scheduled_match_never_carries_a_score() -> None:
    rows = build_rows(_predictions(), "serie-a", None, NOW)
    assert (rows.matches[1]["home_goals"], rows.matches[1]["away_goals"]) == (None, None)


def test_finished_match_keeps_score() -> None:
    rows = build_rows(_predictions(), "serie-a", None, NOW)
    assert (rows.matches[0]["home_goals"], rows.matches[0]["away_goals"]) == (2, 1)


def test_table_lock_defaults_to_first_kickoff() -> None:
    rows = build_rows(_predictions(), "serie-a", None, NOW)
    assert rows.season["classificacao_locks_at"] == "2032-11-01T22:00:00+00:00"


def test_open_season_has_no_final_date() -> None:
    assert "final_at" not in build_rows(_predictions(), "serie-a", None, NOW).season


def test_finished_season_gets_final_date() -> None:
    rows = build_rows(_predictions(("finished", "finished")), "serie-a", None, NOW)
    assert rows.season["final_at"] == NOW.isoformat()


def test_unknown_status_is_sent_as_scheduled() -> None:
    rows = build_rows(_predictions(("finished", "awaiting_result")), "serie-a", None, NOW)
    assert rows.matches[1]["status"] == "scheduled"


@dataclass
class _Response:
    status_code: int
    text: str = ""


@dataclass
class _FakeClient:
    status_code: int = 201
    calls: list[tuple[str, dict[str, str], Any]] = field(default_factory=list)

    def post(self, url: str, *, headers: dict[str, str], json: Any) -> _Response:
        self.calls.append((url, headers, json))
        return _Response(self.status_code)


def test_push_sends_season_before_matches() -> None:
    client = _FakeClient()
    push(build_rows(_predictions(), "serie-a", None, NOW), "https://example.supabase.co/", "service", client)
    assert [url.split("/rest/v1/")[1].split("?")[0] for url, _, _ in client.calls] == [
        "sim_seasons",
        "sim_matches",
        "sim_standings",
    ]


def test_push_raises_on_http_error() -> None:
    with pytest.raises(RuntimeError):
        push(
            build_rows(_predictions(), "serie-a", None, NOW), "https://example.supabase.co", "service", _FakeClient(401)
        )


def test_cli_default_predictions_path_is_the_web_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem --predictions, o comando lê o mesmo predictions.json que o export-web escreve."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    monkeypatch.setattr(cli, "PATHS", SimpleNamespace(web_static_data=tmp_path))
    with pytest.raises(FileNotFoundError) as error:
        cli.command_sync_simulator(
            argparse.Namespace(season=2032, competition="serie-a", predictions=None, classificacao_lock=None)
        )
    assert Path(error.value.filename) == tmp_path / "api" / "seasons" / "2032" / "predictions.json"
