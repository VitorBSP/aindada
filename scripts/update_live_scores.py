"""Atualiza os placares do modo Ao vivo (`live_round_scores`, migração 0007) durante a rodada.

Lê SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY do ambiente ou do `.env` da raiz do repositório. A chave de serviço
fica só na máquina do dono: nunca vai para o navegador nem para o repositório.

Exemplos:
  python scripts/update_live_scores.py --init-round 38 --predictions https://vitorbsp.github.io/aindada/data/api/seasons/2026/predictions.json
  python scripts/update_live_scores.py --match 2026-palmeiras-flamengo --score 1-0 --status live --minute 34
  python scripts/update_live_scores.py --match 2026-palmeiras-flamengo --score 1-0 --status ht
  python scripts/update_live_scores.py --match 2026-palmeiras-flamengo --score 2-1 --status finished
  python scripts/update_live_scores.py --from-json placares.json
  python scripts/update_live_scores.py --list
  python scripts/update_live_scores.py --watch          # placares automáticos da football-data.org (Ctrl+C para parar)

--watch lê também FOOTBALL_DATA_ORG_TOKEN e confere a fonte a cada 30 s (o plano gratuito aceita 10 chamadas por
minuto). Jogo da fonte vira linha pelo `source_match_id` do predictions.json publicado. O minuto vem da fonte quando
ela informa; senão é estimado pelo horário do pontapé (1º tempo até 48', depois 15 min de intervalo).

JSON aceito: {"round": 38, "matches": [{"match_id": "...", "score": "1-0", "status": "live", "minute": 34}, ...]}
ou uma lista desses objetos, cada um com "round". Jogo que não começou vai como "scheduled", sem placar.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TABLE = "live_round_scores"
STATUSES = ("scheduled", "live", "ht", "finished")
MATCH_ID = re.compile(r"^(\d{4})-[a-z0-9-]+$")
SCORE = re.compile(r"^\s*(\d{1,2})\s*[-x×:]\s*(\d{1,2})\s*$", re.IGNORECASE)
MAX_GOALS = 30
MAX_MINUTE = 130
MAX_ROUND = 38
HALF_TIME_MINUTE = 45
BRASILIA_OFFSET = timezone(timedelta(hours=-3))
TIMEOUT_SECONDS = 15
FOOTBALL_DATA_URL = "https://api.football-data.org/v4/competitions/BSA/matches"
PREDICTIONS_URL = "https://vitorbsp.github.io/aindada/data/api/seasons/2026/predictions.json"
SOURCE_STATUS = {"IN_PLAY": "live", "LIVE": "live", "PAUSED": "ht", "FINISHED": "finished"}
FIRST_HALF_END = 48
HALF_TIME_BREAK = 15
LAST_MINUTE = 95


class LiveScoreError(ValueError):
    """Entrada inválida: a mensagem diz o que corrigir."""


@dataclass(frozen=True)
class LiveScore:
    match_id: str
    status: str
    home_goals: int | None = None
    away_goals: int | None = None
    minute: int | None = None
    round: int | None = None

    @property
    def season(self) -> int:
        return int(self.match_id[:4])

    def as_row(self) -> dict[str, Any]:
        """Linha para o PostgREST; sem `round` quando ele não foi informado (atualização de linha existente)."""
        row: dict[str, Any] = {
            "season": self.season,
            "match_id": self.match_id,
            "status": self.status,
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "minute": self.minute,
        }
        if self.round is not None:
            row["round"] = self.round
        return row


def parse_score(text: str) -> tuple[int, int]:
    match = SCORE.match(text)
    if not match:
        raise LiveScoreError(f"placar inválido: {text!r} (use 1-0)")
    home, away = int(match.group(1)), int(match.group(2))
    if home > MAX_GOALS or away > MAX_GOALS:
        raise LiveScoreError(f"placar fora do limite: {text!r}")
    return home, away


def build_score(
    match_id: str,
    status: str,
    score: str | None = None,
    minute: int | None = None,
    round_number: int | None = None,
) -> LiveScore:
    """Valida como o banco (0007): sem placar antes do jogo, placar obrigatório depois do início, minuto ao vivo."""
    if not MATCH_ID.match(match_id):
        raise LiveScoreError(f"match_id inválido: {match_id!r} (ex.: 2026-palmeiras-flamengo)")
    if status not in STATUSES:
        raise LiveScoreError(f"status inválido: {status!r} (use {', '.join(STATUSES)})")
    if round_number is not None and not 1 <= round_number <= MAX_ROUND:
        raise LiveScoreError(f"rodada fora de 1–{MAX_ROUND}: {round_number}")
    if minute is not None and not 0 <= minute <= MAX_MINUTE:
        raise LiveScoreError(f"minuto fora de 0–{MAX_MINUTE}: {minute}")
    if status == "scheduled":
        if score is not None:
            raise LiveScoreError("jogo que não começou não tem placar (status scheduled sem --score)")
        return LiveScore(match_id, status, round=round_number)
    if score is None:
        raise LiveScoreError(f"status {status} precisa de --score")
    home, away = parse_score(score)
    if status == "live" and minute is None:
        raise LiveScoreError("status live precisa de --minute")
    if status == "ht" and minute is None:
        minute = HALF_TIME_MINUTE
    return LiveScore(match_id, status, home, away, minute, round_number)


def scores_from_document(document: Any) -> list[LiveScore]:
    """Lê o JSON local: objeto com `round` e `matches`, ou lista de jogos com `round` em cada um."""
    if isinstance(document, Mapping):
        default_round = document.get("round")
        items = document.get("matches")
    else:
        default_round, items = None, document
    if not isinstance(items, list) or not items:
        raise LiveScoreError("o JSON precisa de uma lista de jogos (ou {'round': N, 'matches': [...]})")
    scores = []
    for position, item in enumerate(items, start=1):
        if not isinstance(item, Mapping) or "match_id" not in item:
            raise LiveScoreError(f"jogo {position}: objeto sem match_id")
        score = item.get("score")
        if score is None and item.get("home_goals") is not None and item.get("away_goals") is not None:
            score = f"{item['home_goals']}-{item['away_goals']}"
        round_number = item.get("round", default_round)
        if round_number is None:
            raise LiveScoreError(f"jogo {position} ({item['match_id']}): falta a rodada (round)")
        try:
            scores.append(
                build_score(
                    str(item["match_id"]),
                    str(item.get("status", "scheduled")),
                    None if score is None else str(score),
                    None if item.get("minute") is None else int(item["minute"]),
                    int(round_number),
                )
            )
        except LiveScoreError as error:
            raise LiveScoreError(f"jogo {position} ({item['match_id']}): {error}") from error
    if len({score.match_id for score in scores}) != len(scores):
        raise LiveScoreError("o JSON repete um match_id")
    return scores


def round_from_predictions(predictions: Mapping[str, Any], round_number: int) -> list[LiveScore]:
    """Linhas iniciais (scheduled, sem placar) dos jogos da rodada que ainda não terminaram no snapshot."""
    pending = [
        match
        for match in predictions.get("matches", [])
        if match.get("round") == round_number and match.get("status") not in ("finished", "cancelled")
    ]
    if not pending:
        raise LiveScoreError(f"nenhum jogo pendente da rodada {round_number} no predictions.json")
    return [build_score(str(match["match_id"]), "scheduled", round_number=round_number) for match in pending]


def load_env_file(path: Path, environ: dict[str, str]) -> None:
    """`.env` simples (CHAVE=valor); não sobrescreve o que já está no ambiente."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in environ:
            environ[key] = value


Sender = Callable[[str, str, dict[str, str], bytes | None], tuple[int, str]]


def urllib_sender(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return int(response.status), response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return int(error.code), error.read().decode("utf-8", "replace")


@dataclass(frozen=True)
class LiveClient:
    base_url: str
    service_key: str
    send: Sender = urllib_sender

    def _headers(self, prefer: str) -> dict[str, str]:
        return {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": prefer,
        }

    def _url(self, query: Mapping[str, str]) -> str:
        return f"{self.base_url.rstrip('/')}/rest/v1/{TABLE}?{urllib.parse.urlencode(query)}"

    def _call(self, method: str, query: Mapping[str, str], prefer: str, payload: Any = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        status, text = self.send(method, self._url(query), self._headers(prefer), body)
        if status >= 300:
            raise RuntimeError(f"{TABLE}: HTTP {status}: {text[:300]}")
        return json.loads(text) if text.strip() else None

    def upsert(self, scores: Sequence[LiveScore], keep_existing: bool = False) -> list[dict[str, Any]]:
        """Grava linhas completas (com rodada). `keep_existing` não mexe em jogo que já está na tabela."""
        if any(score.round is None for score in scores):
            raise LiveScoreError("gravar linha nova exige a rodada (--round)")
        resolution = "ignore-duplicates" if keep_existing else "merge-duplicates"
        rows = self._call(
            "POST",
            {"on_conflict": "match_id"},
            f"resolution={resolution},return=representation",
            [score.as_row() for score in scores],
        )
        return list(rows or [])

    def update(self, score: LiveScore) -> dict[str, Any]:
        """Atualiza um jogo já na tabela (sem precisar repetir a rodada)."""
        row = {key: value for key, value in score.as_row().items() if key not in ("season", "match_id")}
        rows = self._call("PATCH", {"match_id": f"eq.{score.match_id}"}, "return=representation", row)
        if not rows:
            raise LiveScoreError(
                f"{score.match_id} ainda não está na tabela: informe --round N (ou rode --init-round antes)"
            )
        return dict(rows[0])

    def list(self, season: int) -> list[dict[str, Any]]:
        query = {"season": f"eq.{season}", "select": "*", "order": "round.asc,match_id.asc"}
        return list(self._call("GET", query, "count=none") or [])


def read_json(source: str) -> Any:
    if source.startswith(("https://", "http://")):
        with urllib.request.urlopen(source, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    return json.loads(Path(source).read_text(encoding="utf-8"))


def describe(row: Mapping[str, Any]) -> str:
    score = "—" if row.get("home_goals") is None else f"{row['home_goals']}-{row['away_goals']}"
    minute = f" {row['minute']}'" if row.get("minute") is not None else ""
    return f"r{row.get('round')} {row['match_id']}: {score} {row['status']}{minute} ({row.get('updated_at', '')})"


def estimate_minute(kickoff: datetime, now: datetime) -> int:
    """Minuto aproximado de um jogo em andamento pelo horário do pontapé (sem o minuto da fonte)."""
    elapsed = max(1, int((now - kickoff).total_seconds() // 60) + 1)
    if elapsed <= FIRST_HALF_END:
        return elapsed
    return max(HALF_TIME_MINUTE + 1, min(elapsed - HALF_TIME_BREAK - (FIRST_HALF_END - HALF_TIME_MINUTE), LAST_MINUTE))


def _source_minute(match: Mapping[str, Any]) -> int | None:
    value = match.get("minute")
    try:
        minute = int(str(value).split("+", 1)[0])
    except (TypeError, ValueError):
        return None
    return minute if 0 <= minute <= MAX_MINUTE else None


def football_data_scores(
    payload: Mapping[str, Any], predictions: Mapping[str, Any], now: datetime
) -> tuple[list[LiveScore], list[str]]:
    """Jogos em andamento ou encerrados da fonte, já com o `match_id` e a rodada do snapshot publicado.

    Jogo que não começou não vira linha; jogo sem placar na fonte é pulado (nunca 0 x 0 inventado).
    """
    by_source = {
        str(match["source_match_id"]): match
        for match in predictions.get("matches", [])
        if match.get("source_match_id") is not None
    }
    scores: list[LiveScore] = []
    notes: list[str] = []
    for match in payload.get("matches", []):
        status = SOURCE_STATUS.get(str(match.get("status")))
        if status is None:
            continue
        known = by_source.get(str(match.get("id")))
        label = f"{(match.get('homeTeam') or {}).get('name')} x {(match.get('awayTeam') or {}).get('name')}"
        if known is None or known.get("round") is None:
            notes.append(f"fonte {match.get('id')} ({label}): fora do snapshot publicado, ignorado")
            continue
        if known.get("status") == "finished":
            continue
        full_time = (match.get("score") or {}).get("fullTime") or {}
        home, away = full_time.get("home"), full_time.get("away")
        if home is None or away is None:
            notes.append(f"{known['match_id']}: fonte ainda sem placar, aguardando")
            continue
        minute = None
        if status == "live":
            minute = _source_minute(match)
            if minute is None and match.get("utcDate"):
                kickoff = datetime.fromisoformat(str(match["utcDate"]).replace("Z", "+00:00"))
                minute = estimate_minute(kickoff, now)
            minute = 1 if minute is None else minute
        scores.append(build_score(str(known["match_id"]), status, f"{home}-{away}", minute, int(known["round"])))
    return scores, notes


def fetch_football_data(token: str, now: datetime, send: Sender = urllib_sender) -> dict[str, Any]:
    window = {"dateFrom": (now - timedelta(days=1)).date(), "dateTo": (now + timedelta(days=1)).date()}
    query = urllib.parse.urlencode({key: day.isoformat() for key, day in window.items()})
    headers = {"X-Auth-Token": token, "Accept": "application/json"}
    status, text = send("GET", f"{FOOTBALL_DATA_URL}?{query}", headers, None)
    if status >= 300:
        raise RuntimeError(f"football-data.org: HTTP {status}: {text[:200]}")
    payload: dict[str, Any] = json.loads(text)
    return payload


def watch(
    arguments: argparse.Namespace,
    environ: Mapping[str, str],
    send: Sender = urllib_sender,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    output: Callable[[str], None] = print,
) -> None:
    """Confere a fonte a cada `--interval` segundos e grava só o que mudou. `--once` faz uma volta só."""
    token = environ.get("FOOTBALL_DATA_ORG_TOKEN", "")
    if not token:
        raise LiveScoreError("--watch precisa de FOOTBALL_DATA_ORG_TOKEN (ambiente ou .env)")
    base_url = environ.get("SUPABASE_URL", "")
    service_key = environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not (base_url and service_key) and not arguments.dry_run:
        raise LiveScoreError("defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY (ambiente ou .env)")
    client = LiveClient(base_url, service_key, send)
    predictions = read_json(arguments.predictions or PREDICTIONS_URL)
    sent: dict[str, dict[str, Any]] = {}
    seen_notes: set[str] = set()
    while True:
        now = clock()
        try:
            scores, notes = football_data_scores(fetch_football_data(token, now, send), predictions, now)
            for note in notes:
                if note not in seen_notes:
                    seen_notes.add(note)
                    output(f"aviso: {note}")
            changed = [score for score in scores if sent.get(score.match_id) != score.as_row()]
            if changed and not arguments.dry_run:
                client.upsert(changed)
            for score in changed:
                sent[score.match_id] = score.as_row()
                output(f"{now.astimezone(BRASILIA_OFFSET):%H:%M:%S} {describe(score.as_row())}")
            if not scores:
                output(f"{now.astimezone(BRASILIA_OFFSET):%H:%M:%S} nenhum jogo da Série A em andamento na fonte")
        except (RuntimeError, OSError, json.JSONDecodeError) as error:
            output(f"erro (tento de novo em {arguments.interval} s): {error}")
        if arguments.once:
            return
        sleep(arguments.interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Placares do modo Ao vivo (live_round_scores).")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--match", help="match_id do snapshot, ex.: 2026-palmeiras-flamengo")
    action.add_argument("--from-json", help="arquivo JSON local com vários jogos")
    action.add_argument(
        "--init-round", type=int, help="cria a rodada inteira como scheduled (precisa de --predictions)"
    )
    action.add_argument("--list", action="store_true", help="mostra o que está na tabela")
    action.add_argument("--watch", action="store_true", help="placares automáticos da football-data.org")
    parser.add_argument("--interval", type=int, default=30, help="segundos entre consultas no --watch (mín. 15)")
    parser.add_argument("--once", action="store_true", help="no --watch, faz uma consulta só")
    parser.add_argument("--score", help="placar mandante-visitante, ex.: 1-0")
    parser.add_argument("--status", choices=STATUSES, help="scheduled, live, ht (intervalo) ou finished")
    parser.add_argument("--minute", type=int, help="minuto do jogo (obrigatório com live)")
    parser.add_argument("--round", type=int, help="rodada (só para criar a linha do jogo)")
    parser.add_argument("--predictions", help="predictions.json (arquivo ou URL); padrão no --watch: o publicado")
    parser.add_argument("--season", type=int, default=2026, help="temporada para --list")
    parser.add_argument("--dry-run", action="store_true", help="mostra o que seria enviado, sem enviar")
    return parser


def planned_scores(arguments: argparse.Namespace) -> tuple[list[LiveScore], bool]:
    """Jogos a gravar e se a gravação preserva linhas existentes (só no --init-round)."""
    if arguments.match:
        if not arguments.status:
            raise LiveScoreError("--match precisa de --status")
        return [
            build_score(arguments.match, arguments.status, arguments.score, arguments.minute, arguments.round)
        ], False
    if arguments.from_json:
        return scores_from_document(read_json(arguments.from_json)), False
    if not arguments.predictions:
        raise LiveScoreError("--init-round precisa de --predictions (arquivo ou URL do predictions.json)")
    return round_from_predictions(read_json(arguments.predictions), arguments.init_round), True


def run(arguments: argparse.Namespace, environ: Mapping[str, str], send: Sender = urllib_sender) -> list[str]:
    scores: list[LiveScore] = []
    keep_existing = False
    if not arguments.list:
        scores, keep_existing = planned_scores(arguments)
        if arguments.dry_run:
            return [json.dumps(score.as_row(), ensure_ascii=False) for score in scores]
    base_url = environ.get("SUPABASE_URL", "")
    service_key = environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base_url or not service_key:
        raise LiveScoreError("defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY (ambiente ou .env)")
    client = LiveClient(base_url, service_key, send)
    if arguments.list:
        return [describe(row) for row in client.list(arguments.season)] or ["(tabela vazia)"]
    if len(scores) == 1 and scores[0].round is None:
        return [describe(client.update(scores[0]))]
    written = client.upsert(scores, keep_existing=keep_existing)
    lines = [describe(row) for row in written]
    if keep_existing and len(written) < len(scores):
        lines.append(f"{len(scores) - len(written)} jogo(s) já estavam na tabela e não foram alterados")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    environ = dict(os.environ)
    load_env_file(ROOT / ".env", environ)
    try:
        if arguments.watch:
            arguments.interval = max(15, arguments.interval)
            watch(arguments, environ)
            return 0
        for line in run(arguments, environ):
            print(line)
    except KeyboardInterrupt:
        print("parado")
    except (LiveScoreError, RuntimeError, OSError, json.JSONDecodeError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
