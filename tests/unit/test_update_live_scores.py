"""Script do modo Ao vivo (scripts/update_live_scores.py). Sem rede: o envio HTTP é trocado por um falso.

Jogos e IDs SINTÉTICOS (synthetic), temporada 2099; nada aqui é placar real.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "update_live_scores.py"
MATCH = "2099-sintetico-01-sintetico-02"
ENVIRON = {"SUPABASE_URL": "https://exemplo.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "chave-sintetica"}


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("update_live_scores", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


live = _load_script()


class FakeSender:
    def __init__(self, response: Any, status: int = 200) -> None:
        self.calls: list[tuple[str, str, dict[str, str], Any]] = []
        self.response = response
        self.status = status

    def __call__(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, str]:
        self.calls.append((method, url, headers, None if body is None else json.loads(body)))
        return self.status, json.dumps(self.response)


def _run(argv: list[str], sender: FakeSender) -> list[str]:
    result: list[str] = live.run(live.build_parser().parse_args(argv), ENVIRON, sender)
    return result


def _row(**values: Any) -> dict[str, Any]:
    return {"round": 38, "match_id": MATCH, "status": "live", "home_goals": 1, "away_goals": 0, "minute": 34, **values}


def test_score_accepts_x_separator() -> None:
    assert live.parse_score("2 x 1") == (2, 1)


def test_scheduled_never_gets_a_score() -> None:
    with pytest.raises(live.LiveScoreError):
        live.build_score(MATCH, "scheduled", "0-0")


def test_scheduled_row_has_no_goals() -> None:
    row = live.build_score(MATCH, "scheduled", round_number=38).as_row()
    assert (row["home_goals"], row["away_goals"]) == (None, None)


def test_live_needs_minute() -> None:
    with pytest.raises(live.LiveScoreError):
        live.build_score(MATCH, "live", "1-0")


def test_half_time_defaults_to_minute_45() -> None:
    assert live.build_score(MATCH, "ht", "1-0").minute == 45


def test_started_match_needs_score() -> None:
    with pytest.raises(live.LiveScoreError):
        live.build_score(MATCH, "finished")


def test_invalid_match_id_rejected() -> None:
    with pytest.raises(live.LiveScoreError):
        live.build_score("Palmeiras x Flamengo", "live", "1-0", 10)


def test_season_comes_from_match_id() -> None:
    assert live.build_score(MATCH, "live", "1-0", 10).as_row()["season"] == 2099


def test_single_update_without_round_uses_patch() -> None:
    sender = FakeSender([_row()])
    _run(["--match", MATCH, "--score", "1-0", "--status", "live", "--minute", "34"], sender)
    assert sender.calls[0][0] == "PATCH"


def test_patch_filters_by_match_id() -> None:
    sender = FakeSender([_row()])
    _run(["--match", MATCH, "--score", "1-0", "--status", "live", "--minute", "34"], sender)
    assert f"match_id=eq.{MATCH}" in sender.calls[0][1]


def test_service_key_sent_as_bearer() -> None:
    sender = FakeSender([_row()])
    _run(["--match", MATCH, "--score", "1-0", "--status", "live", "--minute", "34"], sender)
    assert sender.calls[0][2]["Authorization"] == "Bearer chave-sintetica"


def test_unknown_match_without_round_explains_fix() -> None:
    with pytest.raises(live.LiveScoreError, match="--round"):
        _run(["--match", MATCH, "--score", "1-0", "--status", "live", "--minute", "3"], FakeSender([]))


def test_update_with_round_upserts() -> None:
    sender = FakeSender([_row()])
    _run(["--match", MATCH, "--score", "1-0", "--status", "live", "--minute", "34", "--round", "38"], sender)
    assert "resolution=merge-duplicates" in sender.calls[0][2]["Prefer"]


def test_json_document_with_round_and_matches(tmp_path: Path) -> None:
    document = {"round": 38, "matches": [{"match_id": MATCH, "score": "2-2", "status": "finished"}]}
    path = tmp_path / "placares.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    sender = FakeSender([_row(status="finished", home_goals=2, away_goals=2, minute=None)])
    _run(["--from-json", str(path)], sender)
    assert sender.calls[0][3][0]["home_goals"] == 2


def test_json_list_needs_round() -> None:
    with pytest.raises(live.LiveScoreError, match="rodada"):
        live.scores_from_document([{"match_id": MATCH, "status": "scheduled"}])


def test_json_rejects_repeated_match() -> None:
    item = {"match_id": MATCH, "status": "scheduled"}
    with pytest.raises(live.LiveScoreError, match="repete"):
        live.scores_from_document({"round": 38, "matches": [item, item]})


def test_init_round_keeps_existing_rows(tmp_path: Path) -> None:
    predictions = {"matches": [{"match_id": MATCH, "round": 38, "status": "scheduled"}]}
    path = tmp_path / "predictions.json"
    path.write_text(json.dumps(predictions), encoding="utf-8")
    sender = FakeSender([])
    _run(["--init-round", "38", "--predictions", str(path)], sender)
    assert "resolution=ignore-duplicates" in sender.calls[0][2]["Prefer"]


def test_init_round_skips_finished_matches() -> None:
    predictions = {
        "matches": [
            {"match_id": MATCH, "round": 38, "status": "scheduled"},
            {"match_id": "2099-sintetico-03-sintetico-04", "round": 38, "status": "finished"},
        ]
    }
    assert [score.match_id for score in live.round_from_predictions(predictions, 38)] == [MATCH]


def test_dry_run_sends_nothing() -> None:
    sender = FakeSender([])
    _run(["--match", MATCH, "--score", "1-0", "--status", "live", "--minute", "3", "--dry-run"], sender)
    assert sender.calls == []


def test_http_error_is_reported() -> None:
    with pytest.raises(RuntimeError, match="HTTP 401"):
        _run(["--list"], FakeSender({"message": "invalid"}, status=401))


def test_missing_credentials_rejected() -> None:
    arguments = live.build_parser().parse_args(["--list"])
    with pytest.raises(live.LiveScoreError, match="SUPABASE_URL"):
        live.run(arguments, {}, FakeSender([]))


def test_env_file_does_not_override_environment(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "SUPABASE_URL=https://do-arquivo\n# comentário\nSUPABASE_SERVICE_ROLE_KEY='chave'\n", encoding="utf-8"
    )
    environ = {"SUPABASE_URL": "https://do-ambiente"}
    live.load_env_file(path, environ)
    assert environ == {"SUPABASE_URL": "https://do-ambiente", "SUPABASE_SERVICE_ROLE_KEY": "chave"}


SOURCE_NOW = datetime(2099, 11, 27, 23, 30, tzinfo=UTC)
SYNTHETIC_PREDICTIONS = {
    "matches": [
        {"match_id": MATCH, "round": 37, "status": "scheduled", "source_match_id": "900"},
        {"match_id": "2099-sintetico-03-sintetico-04", "round": 37, "status": "finished", "source_match_id": "901"},
    ]
}


def _source_match(status: str, score: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    return {
        "id": extra.pop("match_id", 900),
        "status": status,
        "utcDate": "2099-11-27T23:00:00Z",
        "homeTeam": {"name": "Sintético 1"},
        "awayTeam": {"name": "Sintético 2"},
        "score": {"fullTime": score or {"home": None, "away": None}},
        **extra,
    }


def _source_scores(*matches: dict[str, Any]) -> list[Any]:
    scores, _ = live.football_data_scores({"matches": list(matches)}, SYNTHETIC_PREDICTIONS, SOURCE_NOW)
    return list(scores)


def test_first_half_minute_from_kickoff() -> None:
    assert live.estimate_minute(datetime(2099, 1, 1, 20, 0, tzinfo=UTC), datetime(2099, 1, 1, 20, 23, tzinfo=UTC)) == 24


def test_second_half_minute_discounts_break() -> None:
    assert live.estimate_minute(datetime(2099, 1, 1, 20, 0, tzinfo=UTC), datetime(2099, 1, 1, 21, 20, tzinfo=UTC)) == 63


def test_source_in_play_becomes_live_row() -> None:
    score = _source_scores(_source_match("IN_PLAY", {"home": 1, "away": 0}))[0]
    assert (score.match_id, score.status, score.home_goals, score.round) == (MATCH, "live", 1, 37)


def test_source_minute_preferred_over_estimate() -> None:
    assert _source_scores(_source_match("IN_PLAY", {"home": 0, "away": 0}, minute="45+2"))[0].minute == 45


def test_source_paused_is_half_time() -> None:
    assert _source_scores(_source_match("PAUSED", {"home": 0, "away": 0}))[0].status == "ht"


def test_source_without_score_is_skipped() -> None:
    assert _source_scores(_source_match("IN_PLAY", None)) == []


def test_source_not_started_is_skipped() -> None:
    assert _source_scores(_source_match("TIMED", None)) == []


def test_source_match_already_official_is_skipped() -> None:
    assert _source_scores(_source_match("FINISHED", {"home": 2, "away": 2}, match_id=901)) == []


def test_watch_reads_source_then_writes_supabase() -> None:
    source = {"matches": [_source_match("IN_PLAY", {"home": 1, "away": 0}, minute=30)]}

    def sender(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, str]:
        calls.append(method)
        return 200, json.dumps(source if "football-data" in url else [])

    calls: list[str] = []
    arguments = live.build_parser().parse_args(["--watch", "--once", "--predictions", "unused"])
    environ = {**ENVIRON, "FOOTBALL_DATA_ORG_TOKEN": "token-sintetico"}
    original = live.read_json
    live.read_json = lambda source_path: SYNTHETIC_PREDICTIONS
    try:
        live.watch(arguments, environ, sender, clock=lambda: SOURCE_NOW, output=lambda line: None)
    finally:
        live.read_json = original
    assert calls == ["GET", "POST"]
