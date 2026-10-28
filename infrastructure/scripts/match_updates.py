"""Acompanha os jogos do dia e pede o `publish-site` depois de cada um (ADR-0009, Decisão 1).

Rodado pelo `atualizar-rodada.yml` com `python -I`, só com a biblioteca padrão:

1. uma chamada ao football-data.org pelos jogos do dia em Brasília (o filtro da API é por data UTC; o
   pedido cobre de `dia` a `dia + 2` e o script filtra pela data em `America/Sao_Paulo`);
2. `check_at = início + 2 h 10` para os jogos com horário confirmado da janela (tarde: `check_at` antes
   de 18:30; noite: o dia inteiro, o que recolhe os jogos da tarde ainda não publicados);
3. dorme até cada grupo de `check_at`; no horário, uma chamada à API e a leitura do `predictions.json`
   público decidem: publicar, já publicado, nova tentativa em 30 min ou deixar para a publicação diária.

Prazo interno: início da execução + 5 h 50. `MATCH_UPDATES`: `off` não faz nada; `on` dispara o
`publish-site.yml`; qualquer outro valor (ausente, `dry-run`) só registra o que faria. O log e o resumo
têm IDs, horários e decisões, nunca placares nem o token.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time as time_module
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

BRASILIA = ZoneInfo("America/Sao_Paulo")
CHECK_DELAY = timedelta(hours=2, minutes=10)
RETRY_DELAY = timedelta(minutes=30)
RUN_BUDGET = timedelta(hours=5, minutes=50)
EVENING_CUTOFF = time(18, 30)
REUSE_FETCH = timedelta(minutes=1)
API_URL = "https://api.football-data.org/v4/competitions/BSA/matches"
TIMEOUT_SECONDS = 30

PENDING_STATUSES = frozenset({"SCHEDULED", "TIMED", "IN_PLAY", "PAUSED", "LIVE"})
DROPPED_STATUSES = frozenset({"POSTPONED", "SUSPENDED", "CANCELLED", "AWARDED"})
MODES = ("off", "dry-run", "on")
SCHEDULE_WINDOWS = {"37 15 * * *": "tarde", "37 21 * * *": "noite"}
WINDOWS = ("tarde", "noite")


@dataclass(frozen=True)
class ApiMatch:
    source_id: str
    kickoff_utc: datetime
    status: str


@dataclass(frozen=True)
class Check:
    source_id: str
    check_at: datetime


@dataclass(frozen=True)
class Entry:
    at: datetime
    source_id: str
    decision: str


@dataclass(frozen=True)
class Outcome:
    publish: tuple[str, ...] = ()
    retry: tuple[Check, ...] = ()
    entries: tuple[Entry, ...] = ()


@dataclass
class RunReport:
    mode: str
    window: str
    started_at: datetime
    deadline: datetime
    entries: list[Entry] = field(default_factory=list)
    dispatches: list[tuple[datetime, tuple[str, ...]]] = field(default_factory=list)


def resolve_mode(raw: str | None) -> str:
    """`off` e `on` só quando escritos assim; o resto (inclusive ausente) é `dry-run`."""
    value = (raw or "").strip().lower()
    return value if value in MODES else "dry-run"


def resolve_window(schedule: str | None, requested: str | None, started_at: datetime) -> str:
    if schedule and schedule.strip() in SCHEDULE_WINDOWS:
        return SCHEDULE_WINDOWS[schedule.strip()]
    if requested in WINDOWS:
        return requested
    return "tarde" if started_at.astimezone(BRASILIA).time() < time(18) else "noite"


def brasilia_day(moment: datetime) -> date:
    return moment.astimezone(BRASILIA).date()


def api_params(day: date) -> dict[str, str]:
    """Datas UTC que cobrem o dia inteiro em Brasília, valha o `dateTo` inclusivo ou exclusivo."""
    return {"dateFrom": day.isoformat(), "dateTo": (day + timedelta(days=2)).isoformat()}


def parse_api_matches(payload: Mapping[str, Any]) -> list[ApiMatch]:
    """Só `id`, `utcDate` e `status`; o placar nunca é lido."""
    matches: list[ApiMatch] = []
    for raw in payload.get("matches") or []:
        kickoff = datetime.fromisoformat(str(raw["utcDate"]).replace("Z", "+00:00"))
        matches.append(ApiMatch(str(raw["id"]), kickoff.astimezone(UTC), str(raw["status"])))
    return matches


def plan(matches: Iterable[ApiMatch], started_at: datetime, window: str) -> tuple[list[Check], list[Entry]]:
    """Fila inicial de checagens da janela e o registro do que ficou de fora."""
    day = brasilia_day(started_at)
    deadline = started_at + RUN_BUDGET
    queue: list[Check] = []
    entries: list[Entry] = []
    for match in sorted(matches, key=lambda item: (item.kickoff_utc, item.source_id)):
        if brasilia_day(match.kickoff_utc) != day:
            continue
        check_at = match.kickoff_utc + CHECK_DELAY
        if match.status in DROPPED_STATUSES:
            entries.append(Entry(started_at, match.source_id, f"{match.status}; fica para a publicação diária"))
        elif match.status == "SCHEDULED" and match.kickoff_utc > started_at:
            entries.append(Entry(started_at, match.source_id, "sem horário confirmado; fica para a publicação diária"))
        elif window == "tarde" and _local_time(check_at, day) >= EVENING_CUTOFF:
            continue
        elif check_at > deadline:
            entries.append(Entry(check_at, match.source_id, "depois do prazo; fica para a publicação diária"))
        else:
            queue.append(Check(match.source_id, check_at))
            entries.append(Entry(check_at, match.source_id, "checagem agendada"))
    return queue, entries


def _local_time(moment: datetime, day: date) -> time:
    local = moment.astimezone(BRASILIA)
    return local.time() if local.date() == day else time.max


def evaluate(
    due: Iterable[Check],
    api_status: Mapping[str, str] | None,
    site_status: Mapping[str, str] | None,
    now: datetime,
    deadline: datetime,
) -> Outcome:
    """Decide cada jogo do grupo. `api_status` None = consulta falhou; `site_status` None = site sem estado legível."""
    publish: list[str] = []
    retry: list[Check] = []
    entries: list[Entry] = []
    for check in due:
        status = None if api_status is None else api_status.get(check.source_id)
        if status == "FINISHED":
            if site_status is not None and site_status.get(check.source_id) == "finished":
                entries.append(Entry(now, check.source_id, "já publicado"))
            else:
                publish.append(check.source_id)
                note = "" if site_status is not None else " (estado do site desconhecido)"
                entries.append(Entry(now, check.source_id, f"publicar{note}"))
        elif status in DROPPED_STATUSES:
            entries.append(Entry(now, check.source_id, f"{status}; fica para a publicação diária"))
        else:
            reason = "falha na consulta" if api_status is None else f"{status or 'ausente na API'}"
            retry_at = now + RETRY_DELAY
            if retry_at <= deadline:
                retry.append(Check(check.source_id, retry_at))
                entries.append(Entry(now, check.source_id, f"{reason}; nova tentativa"))
            else:
                entries.append(Entry(now, check.source_id, f"{reason}; sem tempo, fica para a publicação diária"))
    return Outcome(tuple(publish), tuple(retry), tuple(entries))


def run(
    *,
    mode: str,
    window: str,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
    fetch_matches: Callable[[date], list[ApiMatch]],
    fetch_site: Callable[[], Mapping[str, str] | None],
    dispatch: Callable[[tuple[str, ...]], None],
    emit: Callable[[Entry], None] = lambda entry: None,
) -> RunReport:
    """Laço da execução, com relógio, sono e chamadas externas injetados (testável sem rede)."""
    started_at = clock()
    report = RunReport(mode, window, started_at, started_at + RUN_BUDGET)

    def record(*entries: Entry) -> None:
        for entry in entries:
            report.entries.append(entry)
            emit(entry)

    if mode == "off":
        record(Entry(started_at, "-", "MATCH_UPDATES=off; nada a fazer"))
        return report
    day = brasilia_day(started_at)
    matches = fetch_matches(day)
    fetched_at = started_at
    queue, entries = plan(matches, started_at, window)
    record(*entries)
    if not queue:
        record(Entry(started_at, "-", "nenhum jogo a acompanhar nesta janela"))
    latest: dict[str, str] | None = {match.source_id: match.status for match in matches}
    while queue:
        next_at = min(check.check_at for check in queue)
        now = clock()
        if next_at > now:
            sleep((next_at - now).total_seconds())
            now = clock()
        due = [check for check in queue if check.check_at <= now]
        queue = [check for check in queue if check.check_at > now]
        if now - fetched_at >= REUSE_FETCH:
            try:
                latest = {match.source_id: match.status for match in fetch_matches(day)}
            except (OSError, ValueError, KeyError):
                latest = None
            fetched_at = now
        needs_site = latest is not None and any(latest.get(check.source_id) == "FINISHED" for check in due)
        outcome = evaluate(due, latest, fetch_site() if needs_site else {}, now, report.deadline)
        record(*outcome.entries)
        queue.extend(outcome.retry)
        if outcome.publish:
            report.dispatches.append((now, outcome.publish))
            if mode == "on":
                try:
                    dispatch(outcome.publish)
                except (OSError, subprocess.CalledProcessError):
                    record(Entry(now, ",".join(outcome.publish), "falha ao disparar o publish-site"))
    return report


def fetch_api_matches(token: str, day: date) -> list[ApiMatch]:
    url = f"{API_URL}?{urllib.parse.urlencode(api_params(day))}"
    request = urllib.request.Request(url, headers={"X-Auth-Token": token})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return parse_api_matches(json.loads(response.read()))


def site_statuses(document: Any) -> dict[str, str] | None:
    """`source_match_id` → status no `predictions.json`; None se o export ainda não traz o campo."""
    matches = document.get("matches") if isinstance(document, dict) else None
    statuses = {
        str(match["source_match_id"]): str(match.get("status"))
        for match in matches or []
        if isinstance(match, dict) and match.get("source_match_id")
    }
    return statuses or None


def fetch_site_statuses(url: str) -> dict[str, str] | None:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            return site_statuses(json.loads(response.read()))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def dispatch_publish(repository: str, match_ids: tuple[str, ...]) -> None:
    subprocess.run(
        [
            "gh",
            "workflow",
            "run",
            "publish-site.yml",
            "--repo",
            repository,
            "--ref",
            "main",
            "-f",
            "trigger=match",
            "-f",
            f"match_ids={','.join(match_ids)}",
        ],
        check=True,
    )


def _brt(moment: datetime) -> str:
    return moment.astimezone(BRASILIA).strftime("%d/%m %H:%M")


def summary(report: RunReport) -> str:
    action = {"on": "disparado", "dry-run": "teria disparado (dry-run)", "off": "-"}[report.mode]
    lines = [
        "### atualizar-rodada",
        f"- MATCH_UPDATES: `{report.mode}`; janela: {report.window}",
        f"- início: {_brt(report.started_at)} BRT; prazo: {_brt(report.deadline)} BRT",
        "",
        "| horário (BRT) | jogo (football-data.org) | decisão |",
        "|---|---|---|",
        *(f"| {_brt(entry.at)} | {entry.source_id} | {entry.decision} |" for entry in report.entries),
        "",
        "Publicações:",
        "",
        *(f"- {_brt(at)} BRT: {action} `publish-site` para {', '.join(ids)}" for at, ids in report.dispatches),
    ]
    if not report.dispatches:
        lines.append("- nenhuma")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site-url", required=True, help="URL pública do predictions.json")
    parser.add_argument("--summary", default=None, help="arquivo do resumo (GITHUB_STEP_SUMMARY)")
    args = parser.parse_args(argv)

    mode = resolve_mode(os.environ.get("MATCH_UPDATES"))
    started_at = datetime.now(UTC)
    window = resolve_window(os.environ.get("SCHEDULE"), os.environ.get("WINDOW_INPUT"), started_at)
    token = os.environ.get("FOOTBALL_DATA_ORG_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if mode != "off" and not token:
        print("FOOTBALL_DATA_ORG_TOKEN ausente", file=sys.stderr)
        return 1

    def log_sleep(seconds: float) -> None:
        print(f"dormindo {seconds / 60:.0f} min", flush=True)
        time_module.sleep(max(seconds, 0.0))

    try:
        report = run(
            mode=mode,
            window=window,
            clock=lambda: datetime.now(UTC),
            sleep=log_sleep,
            fetch_matches=lambda day: fetch_api_matches(token, day),
            fetch_site=lambda: fetch_site_statuses(args.site_url),
            dispatch=lambda ids: dispatch_publish(repository, ids),
            emit=lambda entry: print(f"{_brt(entry.at)} BRT | {entry.source_id} | {entry.decision}", flush=True),
        )
    except (OSError, ValueError, KeyError) as error:
        print(f"falha na consulta inicial ao football-data.org: {type(error).__name__}", file=sys.stderr)
        return 1
    text = summary(report)
    print(text)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as handle:
            handle.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
