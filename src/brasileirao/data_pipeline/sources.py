"""Adaptadores de fontes de dados.

Cada adaptador entrega registros brutos e metadados de proveniência. A normalização para
os contratos da camada silver acontece em `ingest.py`.
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from brasileirao.contracts import LicenseStatus, MatchStatus

BRASILEIRAO_DATASET_REPO = "https://github.com/leeofernandes1980/brasileirao-dataset.git"
BRASILEIRAO_DATASET_MATCHES = "dashboard/public/data/json/partidas_resumo.json"
BRASILEIRAO_DATASET_CARDS = "dashboard/public/data/json/cartoes.json"


@dataclass(frozen=True)
class RawMatch:
    source_match_id: str
    season: int
    round: int | None
    match_date: date
    home_name: str
    away_name: str
    home_goals: int | None
    away_goals: int | None
    status: MatchStatus


@dataclass(frozen=True)
class RawCard:
    source_match_id: str
    season: int
    club_name: str
    card_color: str


@dataclass(frozen=True)
class SourceSnapshot:
    source_name: str
    origin: str
    version: str
    retrieved_at: datetime
    files: dict[str, Path]
    license_status: LicenseStatus
    license_notes: str
    allowed_uses: tuple[str, ...]


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return int(value)


class BrasileiraoDatasetSource:
    """Repositório público leeofernandes1980/brasileirao-dataset (2003–2026).

    2003–2023: dataset histórico de Adão Duque. 2024–2026: coletado pelo mantenedor via
    API não oficial do Sofascore. O repositório não declara licença; uso restrito a
    pesquisa local até verificação (ver docs/data-sources/catalog.md).
    """

    source_name = "brasileirao_dataset"
    license_status = LicenseStatus.RESEARCH_ONLY_UNVERIFIED
    license_notes = (
        "Repositório sem arquivo LICENSE. Dados 2024+ derivados do Sofascore, cujos termos "
        "restringem coleta automatizada e uso comercial. Uso permitido aqui: pesquisa e "
        "protótipo local. Bloqueado para publicação comercial até acordo de licença."
    )
    allowed_uses = ("research_local", "prototype_local")

    def __init__(self, checkout_dir: Path, repo_url: str = BRASILEIRAO_DATASET_REPO) -> None:
        self.checkout_dir = checkout_dir
        self.repo_url = repo_url

    def fetch(self, revision: str | None = None) -> SourceSnapshot:
        if not (self.checkout_dir / ".git").exists():
            self.checkout_dir.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--quiet", self.repo_url, str(self.checkout_dir)],
                check=True,
            )
        elif revision is None:
            subprocess.run(["git", "-C", str(self.checkout_dir), "pull", "--quiet"], check=True)
        if revision is not None:
            subprocess.run(["git", "-C", str(self.checkout_dir), "checkout", "--quiet", revision], check=True)
        return self.snapshot_from_checkout()

    def snapshot_from_checkout(self) -> SourceSnapshot:
        commit = subprocess.run(
            ["git", "-C", str(self.checkout_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return SourceSnapshot(
            source_name=self.source_name,
            origin=self.repo_url,
            version=commit,
            retrieved_at=datetime.now(tz=UTC),
            files={
                "matches": self.checkout_dir / BRASILEIRAO_DATASET_MATCHES,
                "cards": self.checkout_dir / BRASILEIRAO_DATASET_CARDS,
            },
            license_status=self.license_status,
            license_notes=self.license_notes,
            allowed_uses=self.allowed_uses,
        )

    @staticmethod
    def parse_matches(matches_path: Path) -> list[RawMatch]:
        records = json.loads(matches_path.read_text(encoding="utf-8"))
        parsed_matches: list[RawMatch] = []
        for record in records:
            home_goals = _optional_int(record.get("gols_mandante"))
            away_goals = _optional_int(record.get("gols_visitante"))
            has_score = home_goals is not None and away_goals is not None
            parsed_matches.append(
                RawMatch(
                    source_match_id=str(record["partida_id"]),
                    season=int(record["temporada"]),
                    round=_optional_int(record.get("rodada")),
                    match_date=datetime.fromisoformat(str(record["data"])).date(),
                    home_name=str(record["mandante"]),
                    away_name=str(record["visitante"]),
                    home_goals=home_goals if has_score else None,
                    away_goals=away_goals if has_score else None,
                    status=MatchStatus.FINISHED if has_score else MatchStatus.SCHEDULED,
                )
            )
        return parsed_matches

    @staticmethod
    def parse_cards(cards_path: Path) -> list[RawCard]:
        records = json.loads(cards_path.read_text(encoding="utf-8"))
        return [
            RawCard(
                source_match_id=str(record["partida_id"]),
                season=int(record["temporada"]),
                club_name=str(record["clube"]),
                card_color=str(record["cartao"]),
            )
            for record in records
            if record.get("temporada") is not None and record.get("clube")
        ]


_FOOTBALL_DATA_ORG_STATUS = {
    "FINISHED": MatchStatus.FINISHED,
    "AWARDED": MatchStatus.FINISHED,
    "SCHEDULED": MatchStatus.SCHEDULED,
    "TIMED": MatchStatus.SCHEDULED,
    "IN_PLAY": MatchStatus.SCHEDULED,
    "PAUSED": MatchStatus.SCHEDULED,
    "POSTPONED": MatchStatus.POSTPONED,
    "SUSPENDED": MatchStatus.POSTPONED,
    "CANCELLED": MatchStatus.CANCELLED,
}


class FootballDataOrgSource:
    """API football-data.org v4, competição BSA (Série A). Requer token gratuito.

    Pronto para uso, ainda não validado contra a API real neste ambiente (rede bloqueada).
    """

    source_name = "football_data_org"
    base_url = "https://api.football-data.org/v4"
    license_status = LicenseStatus.REQUIRES_AGREEMENT
    license_notes = (
        "Uso conforme termos da football-data.org (plano gratuito com atribuição e limites de "
        "requisições). Verificar cláusulas de uso comercial antes de publicação."
    )

    def __init__(self, api_token: str) -> None:
        self.api_token = api_token

    def fetch_season_payload(self, season: int) -> dict[str, Any]:
        import httpx  # noqa: PLC0415

        response = httpx.get(
            f"{self.base_url}/competitions/BSA/matches",
            params={"season": season},
            headers={"X-Auth-Token": self.api_token},
            timeout=30.0,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload

    @staticmethod
    def parse_matches(payload: dict[str, Any], season: int) -> list[RawMatch]:
        parsed_matches: list[RawMatch] = []
        for match in payload.get("matches", []):
            status = _FOOTBALL_DATA_ORG_STATUS.get(str(match.get("status")), MatchStatus.SCHEDULED)
            full_time = (match.get("score") or {}).get("fullTime") or {}
            home_goals = _optional_int(full_time.get("home"))
            away_goals = _optional_int(full_time.get("away"))
            if status != MatchStatus.FINISHED or home_goals is None or away_goals is None:
                home_goals, away_goals = None, None
                if status == MatchStatus.FINISHED:
                    status = MatchStatus.SCHEDULED
            parsed_matches.append(
                RawMatch(
                    source_match_id=str(match["id"]),
                    season=season,
                    round=_optional_int(match.get("matchday")),
                    match_date=datetime.fromisoformat(str(match["utcDate"]).replace("Z", "+00:00")).date(),
                    home_name=str(match["homeTeam"]["name"]),
                    away_name=str(match["awayTeam"]["name"]),
                    home_goals=home_goals,
                    away_goals=away_goals,
                    status=status,
                )
            )
        return parsed_matches
