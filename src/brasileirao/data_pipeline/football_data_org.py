"""Adaptador da API football-data.org v4, competição BSA (Série A). Fonte de publicação de 2026+.

Regras do ADR-0008:
- `match_date` é o `utcDate` convertido para America/Sao_Paulo antes de `.date()`;
- o token vem só de `FOOTBALL_DATA_ORG_TOKEN` e nunca aparece em log, `repr` ou mensagem de erro;
- intervalo mínimo de 6 s entre chamadas e espera de `X-RequestCounter-Reset` em HTTP 429;
- `IN_PLAY`, `PAUSED` e `LIVE` viram `scheduled` (placar parcial nunca entra);
- `AWARDED` só vira `finished` com o placar decidido registrado em `known_exceptions.csv`;
- o payload bruto é gravado sem modificação, com `requests.json` (hora de cada requisição) e manifesto.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from brasileirao.contracts import AllowedUse, LicenseStatus, MatchStatus
from brasileirao.data_pipeline.sources import RawMatch, SourceSnapshot
from brasileirao.logging_utils import get_logger

LOGGER = get_logger(__name__)

BRASILIA = ZoneInfo("America/Sao_Paulo")
TOKEN_ENVIRONMENT_VARIABLE = "FOOTBALL_DATA_ORG_TOKEN"
MIN_SECONDS_BETWEEN_CALLS = 6.0
DEFAULT_RATE_LIMIT_WAIT_SECONDS = 60.0
HTTP_OK = 200
HTTP_TOO_MANY_REQUESTS = 429

_STATUS_MAP = {
    "FINISHED": MatchStatus.FINISHED,
    "SCHEDULED": MatchStatus.SCHEDULED,
    "TIMED": MatchStatus.SCHEDULED,
    "IN_PLAY": MatchStatus.SCHEDULED,
    "PAUSED": MatchStatus.SCHEDULED,
    "LIVE": MatchStatus.SCHEDULED,
    "POSTPONED": MatchStatus.POSTPONED,
    "SUSPENDED": MatchStatus.POSTPONED,
    "CANCELLED": MatchStatus.CANCELLED,
}
AWARDED_STATUS = "AWARDED"


class MissingTokenError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            f"variável de ambiente {TOKEN_ENVIRONMENT_VARIABLE} ausente: defina-a no .env local ou no segredo do "
            "Actions (o token nunca vai para o repositório)"
        )


class AwardedMatchError(ValueError):
    """Partida decidida fora de campo (W.O.) sem placar registrado em `known_exceptions.csv`."""


class FootballDataOrgError(RuntimeError):
    """Resposta inesperada da API. A mensagem nunca contém o token."""


class HttpResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def headers(self) -> Mapping[str, str]: ...

    @property
    def content(self) -> bytes: ...


HttpGet = Callable[[str, Mapping[str, Any], Mapping[str, str]], HttpResponse]


def _httpx_get(url: str, params: Mapping[str, Any], headers: Mapping[str, str]) -> HttpResponse:
    import httpx  # noqa: PLC0415

    response: HttpResponse = httpx.get(url, params=dict(params), headers=dict(headers), timeout=30.0)
    return response


def brasilia_date(utc_text: str) -> date:
    """Dia de Brasília de um instante ISO 8601 em UTC (`2026-10-27T00:30:00Z` → 2026-10-26)."""
    instant = datetime.fromisoformat(utc_text.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError(f"utcDate sem fuso: {utc_text}")
    return instant.astimezone(BRASILIA).date()


def _optional_goals(value: Any) -> int | None:
    return None if value is None else int(value)


@dataclass(frozen=True)
class SeasonPayload:
    season: int
    content: bytes
    retrieved_at: datetime

    @property
    def file_name(self) -> str:
        return f"matches_{self.season}.json"


class FootballDataOrgSource:
    source_name = "football_data_org"
    origin = "https://api.football-data.org/v4/competitions/BSA/matches"
    base_url = "https://api.football-data.org/v4"
    license_status = LicenseStatus.LICENSED_WITH_ATTRIBUTION
    allowed_uses = (AllowedUse.RESEARCH_LOCAL, AllowedUse.PROTOTYPE_LOCAL, AllowedUse.PUBLIC_DISPLAY_DERIVED)
    license_name = "football-data.org Terms and Conditions (em vigor desde 2018-06-01)"
    terms_url = "https://www.football-data.org/client/register"
    terms_checked_at = date(2026, 10, 27)
    attribution = "Football data provided by the Football-Data.org API"
    license_notes = (
        "Plano gratuito, competição BSA. Atribuição obrigatória (cláusula 7.1). Uma chave por aplicação/domínio "
        "(2.3); credencial fora de repositório (6.1); cancelada a conta, o site não pode mais referenciar os dados "
        "(9.1); termos mudam sem aviso (11.1), reler a cada temporada. Redistribuição em lote não autorizada "
        "expressamente. ADR-0008."
    )

    def __init__(
        self,
        api_token: str,
        http_get: HttpGet = _httpx_get,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
        min_interval_seconds: float = MIN_SECONDS_BETWEEN_CALLS,
        max_rate_limit_retries: int = 3,
    ) -> None:
        if not api_token.strip():
            raise MissingTokenError
        self._api_token = api_token
        self._http_get = http_get
        self._sleep = sleep
        self._monotonic = monotonic
        self._now = now
        self._min_interval_seconds = min_interval_seconds
        self._max_rate_limit_retries = max_rate_limit_retries
        self._last_call: float | None = None

    @classmethod
    def from_environment(cls, **options: Any) -> FootballDataOrgSource:
        token = os.environ.get(TOKEN_ENVIRONMENT_VARIABLE, "")
        if not token.strip():
            raise MissingTokenError
        return cls(token, **options)

    def __repr__(self) -> str:
        return f"FootballDataOrgSource(base_url={self.base_url!r}, token=***)"

    def _wait_for_slot(self) -> None:
        if self._last_call is None:
            return
        remaining = self._min_interval_seconds - (self._monotonic() - self._last_call)
        if remaining > 0:
            self._sleep(remaining)

    def fetch_season_payload(self, season: int) -> SeasonPayload:
        url = f"{self.base_url}/competitions/BSA/matches"
        for attempt in range(self._max_rate_limit_retries + 1):
            self._wait_for_slot()
            retrieved_at = self._now()
            response = self._http_get(url, {"season": season}, {"X-Auth-Token": self._api_token})
            self._last_call = self._monotonic()
            if response.status_code == HTTP_TOO_MANY_REQUESTS:
                wait_seconds = _reset_seconds(response.headers)
                LOGGER.warning(
                    "football_data_rate_limited",
                    extra={"season": season, "attempt": attempt + 1, "wait_seconds": wait_seconds},
                )
                self._sleep(wait_seconds)
                continue
            if response.status_code != HTTP_OK:
                raise FootballDataOrgError(
                    f"football-data.org devolveu HTTP {response.status_code} para season={season}"
                )
            LOGGER.info("football_data_fetched", extra={"season": season, "bytes": len(response.content)})
            return SeasonPayload(season=season, content=response.content, retrieved_at=retrieved_at)
        raise FootballDataOrgError(f"limite de requisições persistente para season={season}")

    def fetch(
        self,
        seasons: Sequence[int],
        raw_root: Path,
        awarded_results: Mapping[str, tuple[int, int]] | None = None,
    ) -> SourceSnapshot:
        """Baixa as temporadas, valida o parse e só então grava o payload bruto em `raw_root/<fonte>/<versão>/`."""
        payloads = [self.fetch_season_payload(season) for season in sorted(set(seasons))]
        for payload in payloads:
            self.parse_matches(json.loads(payload.content), payload.season, awarded_results)
        first_request = min(payload.retrieved_at for payload in payloads)
        version = "v4-" + first_request.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        target_dir = raw_root / self.source_name / version
        target_dir.mkdir(parents=True, exist_ok=False)
        files: dict[str, Path] = {}
        for payload in payloads:
            path = target_dir / payload.file_name
            path.write_bytes(payload.content)
            files[f"matches_{payload.season}"] = path
        requests_path = target_dir / "requests.json"
        requests_path.write_text(
            json.dumps(
                [
                    {
                        "endpoint": "/v4/competitions/BSA/matches",
                        "season": payload.season,
                        "retrieved_at": payload.retrieved_at.isoformat(),
                        "file": payload.file_name,
                    }
                    for payload in payloads
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
        files["requests"] = requests_path
        return self.snapshot(version, max(payload.retrieved_at for payload in payloads), files)

    def snapshot(self, version: str, retrieved_at: datetime, files: dict[str, Path]) -> SourceSnapshot:
        return SourceSnapshot(
            source_name=self.source_name,
            origin=self.origin,
            version=version,
            retrieved_at=retrieved_at,
            files=files,
            license_status=self.license_status,
            license_notes=self.license_notes,
            allowed_uses=self.allowed_uses,
            license_name=self.license_name,
            terms_url=self.terms_url,
            terms_checked_at=self.terms_checked_at,
            attribution=self.attribution,
            raw_dir_name=version,
        )

    @staticmethod
    def parse_matches(
        payload: Mapping[str, Any],
        season: int,
        awarded_results: Mapping[str, tuple[int, int]] | None = None,
    ) -> list[RawMatch]:
        awarded = awarded_results or {}
        parsed_matches: list[RawMatch] = []
        for match in payload.get("matches", []):
            source_match_id = str(match["id"])
            raw_status = str(match.get("status"))
            home_name = str(match["homeTeam"]["name"])
            away_name = str(match["awayTeam"]["name"])
            home_goals: int | None = None
            away_goals: int | None = None
            if raw_status == AWARDED_STATUS:
                if source_match_id not in awarded:
                    raise AwardedMatchError(
                        f"partida {source_match_id} ({season}, {home_name} x {away_name}) está AWARDED na "
                        "football-data.org e não tem placar decidido em data/reference/known_exceptions.csv "
                        "(code=awarded, source_name=football_data_org); registre-o com evidência antes de ingerir"
                    )
                status = MatchStatus.FINISHED
                home_goals, away_goals = awarded[source_match_id]
            elif raw_status in _STATUS_MAP:
                status = _STATUS_MAP[raw_status]
            else:
                raise FootballDataOrgError(f"status desconhecido {raw_status!r} na partida {source_match_id}")
            if status == MatchStatus.FINISHED and raw_status != AWARDED_STATUS:
                score = match.get("score") or {}
                duration = score.get("duration", "REGULAR")
                if duration != "REGULAR":
                    raise FootballDataOrgError(f"partida {source_match_id} com duração {duration}; esperado REGULAR")
                full_time = score.get("fullTime") or {}
                home_goals = _optional_goals(full_time.get("home"))
                away_goals = _optional_goals(full_time.get("away"))
                if home_goals is None or away_goals is None:
                    home_goals, away_goals, status = None, None, MatchStatus.SCHEDULED
            parsed_matches.append(
                RawMatch(
                    source_match_id=source_match_id,
                    season=season,
                    round=None if match.get("matchday") is None else int(match["matchday"]),
                    match_date=brasilia_date(str(match["utcDate"])),
                    home_name=home_name,
                    away_name=away_name,
                    home_goals=home_goals,
                    away_goals=away_goals,
                    status=status,
                )
            )
        return parsed_matches

    @staticmethod
    def parse_raw_dir(
        raw_dir: Path,
        seasons: Sequence[int] | None = None,
        awarded_results: Mapping[str, tuple[int, int]] | None = None,
    ) -> list[RawMatch]:
        parsed: list[RawMatch] = []
        for path in sorted(raw_dir.glob("matches_*.json")):
            season = int(path.stem.removeprefix("matches_"))
            if seasons is not None and season not in seasons:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            parsed.extend(FootballDataOrgSource.parse_matches(payload, season, awarded_results))
        return parsed


def _reset_seconds(headers: Mapping[str, str]) -> float:
    for name, value in headers.items():
        if name.lower() == "x-requestcounter-reset":
            try:
                return max(float(value), 1.0)
            except ValueError:
                break
    return DEFAULT_RATE_LIMIT_WAIT_SECONDS
