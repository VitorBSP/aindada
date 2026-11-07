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
POINTS_PER_WIN = 3
# Mesma regra do site (app.js, isPostponed): sem placar mais de 7 dias depois da data marcada = adiado, data a definir.
POSTPONED_AFTER_DAYS = 7


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


def is_postponed(match: dict[str, Any], reference_date: date | None) -> bool:
    """Jogo adiado sem data nova: vai ao banco sem horário, para o palpite continuar aberto (ADR-0015, versão 5)."""
    if match["status"] == "postponed":
        return True
    if reference_date is None or match["status"] != MatchStatus.SCHEDULED.value:
        return False
    return (reference_date - date.fromisoformat(match["match_date"])).days > POSTPONED_AFTER_DAYS


def build_rows(
    predictions: dict[str, Any], competition: str, classificacao_lock: datetime | None, now: datetime
) -> SyncRows:
    season = int(predictions["season"])
    matches = predictions["matches"]
    reference = predictions.get("reference_date")
    reference_date = date.fromisoformat(str(reference)) if reference else None
    match_rows = []
    for match in matches:
        finished = match["status"] == MatchStatus.FINISHED.value
        postponed = is_postponed(match, reference_date)
        status = "postponed" if postponed else match["status"] if match["status"] in SYNC_STATUSES else "scheduled"
        match_rows.append(
            {
                "competition": competition,
                "season": season,
                "match_id": match["match_id"],
                "round": match.get("round"),
                "home_id": match["home_id"],
                "away_id": match["away_id"],
                "kickoff_utc": None if postponed else match_lock_utc(match).isoformat(),
                "status": status,
                "home_goals": match["home_goals"] if finished else None,
                "away_goals": match["away_goals"] if finished else None,
            }
        )
    dated = [match for match in matches if not is_postponed(match, reference_date)] or matches
    first_kickoff = min(match_lock_utc(match) for match in dated)
    season_row: dict[str, Any] = {
        "competition": competition,
        "season": season,
        "classificacao_locks_at": (classificacao_lock or first_kickoff).astimezone(UTC).isoformat(),
    }
    # Jogo cancelado não tem placar e nunca termina: não impede o fim da temporada.
    if matches and all(match["status"] in (MatchStatus.FINISHED.value, "cancelled") for match in matches):
        season_row["final_at"] = now.astimezone(UTC).isoformat()
    # Pontos e máximo ainda alcançável: o banco recusa uma Classificação em que um clube fica acima de outro que
    # ele não alcança mais (sim_valid_order).
    remaining: dict[str, int] = {}
    for match in matches:
        if match["status"] not in (MatchStatus.FINISHED.value, "cancelled"):
            for club_id in (match["home_id"], match["away_id"]):
                remaining[club_id] = remaining.get(club_id, 0) + 1
    standings_rows = [
        {
            "competition": competition,
            "season": season,
            "club_id": row["club_id"],
            "position": int(row["position"]),
            "points": int(row["points"]),
            "max_points": int(row["points"]) + POINTS_PER_WIN * remaining.get(row["club_id"], 0),
        }
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


def fetch_notification_list(
    base_url: str, service_key: str, competition: str, season: int, client: HttpClient
) -> list[dict[str, Any]]:
    """Lista de avisos (e-mail, apelido e pontos de cada simulação); só a chave de serviço chama a função."""
    headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}", "Content-Type": "application/json"}
    response = client.post(
        f"{base_url.rstrip('/')}/rest/v1/rpc/sim_notification_list",
        headers=headers,
        json={"p_competition": competition, "p_season": season},
    )
    if response.status_code >= 300:
        raise RuntimeError(f"sim_notification_list: HTTP {response.status_code}: {str(response.text)[:300]}")
    rows: list[dict[str, Any]] = response.json()
    return rows
