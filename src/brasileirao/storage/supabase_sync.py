"""Envia jogos, tabela e trava da temporada ao Supabase do simulador do usuário (ADR-0015, fase 2).

Lê o `predictions.json` exportado, não o banco de snapshots: o servidor recebe exatamente o que o site publica.
Só a chave de serviço escreve nessas tabelas; o navegador lê com a chave pública.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from brasileirao.contracts import MatchStatus

BRASILIA = ZoneInfo("America/Sao_Paulo")
SYNC_STATUSES = {"scheduled", "finished", "postponed", "cancelled"}


@dataclass(frozen=True)
class SyncRows:
    season: dict[str, Any]
    matches: list[dict[str, Any]]
    standings: list[dict[str, Any]]


def match_lock_utc(match: dict[str, Any]) -> datetime:
    """Horário em que o palpite trava: o do pontapé ou, sem ele, 00:00 de Brasília do dia do jogo (o mais cedo)."""
    kickoff = match.get("kickoff_utc")
    if kickoff:
        return datetime.fromisoformat(str(kickoff).replace("Z", "+00:00")).astimezone(UTC)
    return datetime.combine(date.fromisoformat(match["match_date"]), time(0, 0), BRASILIA).astimezone(UTC)


def build_rows(
    predictions: dict[str, Any], competition: str, classificacao_lock: datetime | None, now: datetime
) -> SyncRows:
    season = int(predictions["season"])
    matches = predictions["matches"]
    match_rows = []
    for match in matches:
        finished = match["status"] == MatchStatus.FINISHED.value
        status = match["status"] if match["status"] in SYNC_STATUSES else "scheduled"
        match_rows.append(
            {
                "competition": competition,
                "season": season,
                "match_id": match["match_id"],
                "round": match.get("round"),
                "home_id": match["home_id"],
                "away_id": match["away_id"],
                "kickoff_utc": match_lock_utc(match).isoformat(),
                "status": status,
                "home_goals": match["home_goals"] if finished else None,
                "away_goals": match["away_goals"] if finished else None,
            }
        )
    first_kickoff = min(match_lock_utc(match) for match in matches)
    season_row: dict[str, Any] = {
        "competition": competition,
        "season": season,
        "classificacao_locks_at": (classificacao_lock or first_kickoff).astimezone(UTC).isoformat(),
    }
    if matches and all(match["status"] == MatchStatus.FINISHED.value for match in matches):
        season_row["final_at"] = now.astimezone(UTC).isoformat()
    standings_rows = [
        {"competition": competition, "season": season, "club_id": row["club_id"], "position": int(row["position"])}
        for row in predictions["standings"]
    ]
    return SyncRows(season=season_row, matches=match_rows, standings=standings_rows)


class HttpClient(Protocol):
    def post(self, url: str, *, headers: dict[str, str], json: Any) -> Any: ...


UPSERT_KEYS = {
    "sim_seasons": "competition,season",
    "sim_matches": "competition,season,match_id",
    "sim_standings": "competition,season,club_id",
}


def push(rows: SyncRows, base_url: str, service_key: str, client: HttpClient) -> dict[str, int]:
    """Upsert via PostgREST. A temporada vai primeiro (as simulações dependem dela)."""
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    sent: dict[str, int] = {}
    for table, payload in (
        ("sim_seasons", [rows.season]),
        ("sim_matches", rows.matches),
        ("sim_standings", rows.standings),
    ):
        url = f"{base_url.rstrip('/')}/rest/v1/{table}?on_conflict={UPSERT_KEYS[table]}"
        response = client.post(url, headers=headers, json=payload)
        if response.status_code >= 300:
            raise RuntimeError(f"{table}: HTTP {response.status_code}: {str(response.text)[:300]}")
        sent[table] = len(payload)
    return sent
