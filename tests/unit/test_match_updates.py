"""Decisão do `match_updates.py` (ADR-0009, Decisão 1) com relógio injetado e jogos sintéticos, sem rede."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "infrastructure" / "scripts" / "match_updates.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("match_updates", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MU = _load_script()

# Dia sintético (não é calendário real). Brasília = UTC-3.
TARDE_START = datetime(2099, 3, 4, 15, 37, tzinfo=UTC)  # 12:37 BRT
NOITE_START = datetime(2099, 3, 4, 21, 37, tzinfo=UTC)  # 18:37 BRT


def _kickoff(hour: int, minute: int = 0) -> datetime:
    """Horário de início em Brasília (dia sintético) convertido para UTC."""
    return datetime(2099, 3, 4, hour, minute, tzinfo=MU.BRASILIA).astimezone(UTC)


def _match(source_id: str, hour: int, minute: int = 0, status: str = "TIMED") -> Any:
    return MU.ApiMatch(source_id, _kickoff(hour, minute), status)


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakeWorld:
    """API e site sintéticos: o status de cada jogo muda em horários dados."""

    def __init__(self, timelines: Mapping[str, list[tuple[datetime, str]]], kickoffs: Mapping[str, datetime]) -> None:
        self.timelines = timelines
        self.kickoffs = kickoffs
        self.site: dict[str, str] | None = {}
        self.api_calls = 0
        self.dispatched: list[tuple[str, ...]] = []
        self.clock: FakeClock | None = None

    def fetch_matches(self, day: date) -> list[Any]:
        assert self.clock is not None
        self.api_calls += 1
        now = self.clock()
        matches = []
        for source_id, timeline in self.timelines.items():
            status = [value for at, value in timeline if at <= now][-1]
            matches.append(MU.ApiMatch(source_id, self.kickoffs[source_id], status))
        return matches

    def fetch_site(self) -> dict[str, str] | None:
        return self.site

    def dispatch(self, match_ids: tuple[str, ...]) -> None:
        self.dispatched.append(match_ids)


def _world(**specs: tuple[int, int, list[tuple[int, str]]]) -> FakeWorld:
    """Cada jogo: (hora, minuto, [(minutos após o início, status)])."""
    kickoffs = {source_id: _kickoff(hour, minute) for source_id, (hour, minute, _) in specs.items()}
    timelines = {
        source_id: [(datetime.min.replace(tzinfo=UTC), "TIMED")]
        + [(kickoffs[source_id] + timedelta(minutes=offset), status) for offset, status in changes]
        for source_id, (_, _, changes) in specs.items()
    }
    return FakeWorld(timelines, kickoffs)


def _run(world: FakeWorld, start: datetime, mode: str = "on", window: str | None = None) -> Any:
    clock = FakeClock(start)
    world.clock = clock
    return MU.run(
        mode=mode,
        window=window or MU.resolve_window(None, None, start),
        clock=clock,
        sleep=clock.sleep,
        fetch_matches=world.fetch_matches,
        fetch_site=world.fetch_site,
        dispatch=world.dispatch,
    )


FINISHED_AT_115 = [(1, "IN_PLAY"), (115, "FINISHED")]


# --- plano: janela, agrupamento e dia em Brasília ---------------------------------------------------


def test_api_dates_cover_the_whole_brasilia_day() -> None:
    assert MU.api_params(date(2099, 3, 4)) == {"dateFrom": "2099-03-04", "dateTo": "2099-03-06"}


def test_night_match_that_turns_the_utc_day_belongs_to_the_brasilia_day() -> None:
    queue, _ = MU.plan([_match("late", 21, 45)], NOITE_START, "noite")
    assert [check.source_id for check in queue] == ["late"]


def test_match_of_the_next_brasilia_day_is_ignored() -> None:
    next_day = MU.ApiMatch("tomorrow", datetime(2099, 3, 5, 16, 0, tzinfo=UTC), "TIMED")
    queue, _ = MU.plan([next_day], NOITE_START, "noite")
    assert queue == []


def test_check_at_is_kickoff_plus_two_hours_ten() -> None:
    queue, _ = MU.plan([_match("a", 16)], TARDE_START, "tarde")
    assert queue[0].check_at == _kickoff(18, 10)


def test_afternoon_window_keeps_only_check_at_before_18_30() -> None:
    matches = [_match("a", 16), _match("b", 16, 30), _match("c", 19, 30)]
    queue, _ = MU.plan(matches, TARDE_START, "tarde")
    assert [check.source_id for check in queue] == ["a"]


def test_evening_window_takes_the_whole_day() -> None:
    matches = [_match("a", 16), _match("b", 19, 30), _match("c", 21, 30)]
    queue, _ = MU.plan(matches, NOITE_START, "noite")
    assert [check.source_id for check in queue] == ["a", "b", "c"]


def test_unconfirmed_kickoff_is_left_for_the_daily_publication() -> None:
    queue, _ = MU.plan([_match("a", 19, 30, status="SCHEDULED")], NOITE_START, "noite")
    assert queue == []


def test_check_after_the_deadline_is_left_for_the_daily_publication() -> None:
    queue, _ = MU.plan([_match("a", 22, 30)], NOITE_START, "noite")
    assert queue == []


def test_postponed_at_start_is_left_for_the_daily_publication() -> None:
    queue, _ = MU.plan([_match("a", 19, 30, status="POSTPONED")], NOITE_START, "noite")
    assert queue == []


@pytest.mark.parametrize(
    ("schedule", "requested", "start", "expected"),
    [
        ("37 15 * * *", None, NOITE_START, "tarde"),
        ("37 21 * * *", None, TARDE_START, "noite"),
        (None, "noite", TARDE_START, "noite"),
        (None, "auto", TARDE_START, "tarde"),
        (None, None, NOITE_START, "noite"),
    ],
)
def test_window_comes_from_cron_then_input_then_clock(
    schedule: str | None, requested: str | None, start: datetime, expected: str
) -> None:
    assert MU.resolve_window(schedule, requested, start) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, "dry-run"), ("", "dry-run"), ("dry-run", "dry-run"), ("ON", "on"), ("off", "off"), ("sim", "dry-run")],
)
def test_mode_defaults_to_dry_run(raw: str | None, expected: str) -> None:
    assert MU.resolve_mode(raw) == expected


# --- decisão no check_at ---------------------------------------------------------------------------


NOW = _kickoff(21, 40)
DEADLINE = NOITE_START + MU.RUN_BUDGET


def _evaluate(api_status: str | None, site: Mapping[str, str] | None = None, now: datetime = NOW) -> Any:
    due = [MU.Check("a", now)]
    statuses = None if api_status is None else {"a": api_status}
    return MU.evaluate(due, statuses, {} if site is None else site, now, DEADLINE)


def test_finished_and_not_on_site_is_published() -> None:
    assert _evaluate("FINISHED", {"a": "scheduled"}).publish == ("a",)


def test_finished_and_already_on_site_is_not_published() -> None:
    assert _evaluate("FINISHED", {"a": "finished"}).publish == ()


def test_finished_with_unknown_site_state_is_published() -> None:
    outcome = MU.evaluate([MU.Check("a", NOW)], {"a": "FINISHED"}, None, NOW, DEADLINE)
    assert outcome.publish == ("a",)


@pytest.mark.parametrize("status", ["IN_PLAY", "PAUSED", "LIVE", "TIMED", "SCHEDULED"])
def test_unfinished_match_is_retried_in_30_minutes(status: str) -> None:
    assert _evaluate(status).retry == (MU.Check("a", NOW + timedelta(minutes=30)),)


def test_no_retry_after_the_deadline() -> None:
    assert _evaluate("IN_PLAY", now=DEADLINE - timedelta(minutes=10)).retry == ()


def test_failed_api_call_is_retried() -> None:
    assert _evaluate(None).retry == (MU.Check("a", NOW + timedelta(minutes=30)),)


@pytest.mark.parametrize("status", ["POSTPONED", "SUSPENDED", "CANCELLED", "AWARDED"])
def test_dropped_status_leaves_the_queue_without_publishing(status: str) -> None:
    outcome = _evaluate(status)
    assert (outcome.publish, outcome.retry) == ((), ())


# --- execução completa com relógio injetado --------------------------------------------------------


def test_day_without_matches_makes_a_single_call_and_no_sleep() -> None:
    world = _world()
    report = _run(world, TARDE_START)
    assert (world.api_calls, report.dispatches, MU.brasilia_day(report.started_at)) == (1, [], date(2099, 3, 4))


def test_matches_with_the_same_kickoff_are_checked_in_one_call_and_one_dispatch() -> None:
    world = _world(a=(19, 30, FINISHED_AT_115), b=(19, 30, FINISHED_AT_115))
    _run(world, NOITE_START)
    assert (world.api_calls, world.dispatched) == (2, [("a", "b")])


def test_each_kickoff_group_gets_its_own_dispatch() -> None:
    world = _world(a=(19, 30, FINISHED_AT_115), b=(21, 30, FINISHED_AT_115))
    _run(world, NOITE_START)
    assert world.dispatched == [("a",), ("b",)]


def test_dispatch_happens_at_check_at() -> None:
    world = _world(a=(19, 30, FINISHED_AT_115))
    report = _run(world, NOITE_START)
    assert report.dispatches[0][0] == _kickoff(21, 40)


def test_late_finish_is_dispatched_on_the_retry() -> None:
    world = _world(a=(19, 30, [(1, "IN_PLAY"), (140, "FINISHED")]))
    report = _run(world, NOITE_START)
    assert report.dispatches == [(_kickoff(22, 10), ("a",))]


def test_match_already_published_is_not_dispatched() -> None:
    world = _world(a=(19, 30, FINISHED_AT_115))
    world.site = {"a": "finished"}
    _run(world, NOITE_START)
    assert world.dispatched == []


def test_postponed_during_the_day_is_not_dispatched() -> None:
    world = _world(a=(19, 30, [(-60, "POSTPONED")]))
    _run(world, NOITE_START)
    assert world.dispatched == []


def test_evening_collects_unpublished_afternoon_match_without_extra_call() -> None:
    world = _world(a=(16, 0, FINISHED_AT_115))
    world.site = {"a": "scheduled"}
    report = _run(world, NOITE_START)
    assert (world.api_calls, report.dispatches) == (1, [(NOITE_START, ("a",))])


def test_afternoon_run_ignores_evening_matches() -> None:
    world = _world(a=(19, 30, FINISHED_AT_115))
    report = _run(world, TARDE_START)
    assert (world.api_calls, report.dispatches) == (1, [])


def test_afternoon_run_ends_within_the_budget() -> None:
    world = _world(a=(16, 0, [(1, "IN_PLAY")]))
    clock = FakeClock(TARDE_START)
    world.clock = clock
    MU.run(
        mode="on",
        window="tarde",
        clock=clock,
        sleep=clock.sleep,
        fetch_matches=world.fetch_matches,
        fetch_site=world.fetch_site,
        dispatch=world.dispatch,
    )
    assert clock.now <= TARDE_START + MU.RUN_BUDGET


def test_dry_run_records_but_does_not_dispatch() -> None:
    world = _world(a=(19, 30, FINISHED_AT_115))
    report = _run(world, NOITE_START, mode="dry-run")
    assert (world.dispatched, len(report.dispatches)) == ([], 1)


def test_dry_run_summary_says_it_would_dispatch() -> None:
    world = _world(a=(19, 30, FINISHED_AT_115))
    report = _run(world, NOITE_START, mode="dry-run")
    assert "teria disparado (dry-run) `publish-site` para a" in MU.summary(report)


def test_off_makes_no_call() -> None:
    world = _world(a=(19, 30, FINISHED_AT_115))
    _run(world, NOITE_START, mode="off")
    assert (world.api_calls, world.dispatched) == (0, [])


def test_failed_dispatch_is_recorded_and_the_run_continues() -> None:
    world = _world(a=(19, 30, FINISHED_AT_115), b=(21, 30, FINISHED_AT_115))
    calls: list[tuple[str, ...]] = []

    def failing_dispatch(match_ids: tuple[str, ...]) -> None:
        calls.append(match_ids)
        raise OSError("sintético")

    clock = FakeClock(NOITE_START)
    world.clock = clock
    MU.run(
        mode="on",
        window="noite",
        clock=clock,
        sleep=clock.sleep,
        fetch_matches=world.fetch_matches,
        fetch_site=world.fetch_site,
        dispatch=failing_dispatch,
    )
    assert calls == [("a",), ("b",)]


# --- leitura da API e do site ----------------------------------------------------------------------


def test_api_parsing_reads_only_id_kickoff_and_status() -> None:
    payload = {
        "matches": [
            {
                "id": 99,
                "utcDate": "2099-03-05T00:30:00Z",
                "status": "TIMED",
                "score": {"fullTime": {"home": 9, "away": 9}},
            }
        ]
    }
    assert MU.parse_api_matches(payload) == [MU.ApiMatch("99", datetime(2099, 3, 5, 0, 30, tzinfo=UTC), "TIMED")]


def test_site_without_source_match_id_is_unknown() -> None:
    assert MU.site_statuses({"synthetic": True, "matches": [{"match_id": "x", "status": "finished"}]}) is None


def test_site_statuses_by_source_match_id() -> None:
    document = {"synthetic": True, "matches": [{"source_match_id": "99", "status": "finished"}]}
    assert MU.site_statuses(document) == {"99": "finished"}


def _export_document() -> dict[str, Any]:
    """`predictions.json` sintético com os campos do schema 1.3: `match_id` interno, `source_match_id` da fonte."""
    match = {"home_goals": None, "away_goals": None, "kickoff_utc": "2099-03-04T22:00:00Z"}
    return {
        "synthetic": True,
        "schema_version": "1.3",
        "matches": [
            match | {"match_id": "2099-001", "source_match_id": "101", "status": "finished", "home_goals": 1},
            match | {"match_id": "2099-002", "source_match_id": "102", "status": "scheduled"},
            match | {"match_id": "2099-003", "source_match_id": "103", "status": "postponed"},
            match | {"match_id": "2099-004", "source_match_id": None, "status": "scheduled", "kickoff_utc": None},
        ],
    }


def test_site_statuses_from_export_use_source_match_id() -> None:
    assert MU.site_statuses(_export_document()) == {"101": "finished", "102": "scheduled", "103": "postponed"}


def test_api_finished_match_already_finished_on_site_is_not_published() -> None:
    due = [MU.Check("101", NOW), MU.Check("102", NOW)]
    api_status = {"101": "FINISHED", "102": "FINISHED"}
    outcome = MU.evaluate(due, api_status, MU.site_statuses(_export_document()), NOW, DEADLINE)
    assert outcome.publish == ("102",)
