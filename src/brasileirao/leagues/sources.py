"""Fontes das ligas europeias (ADR-0011): openfootball (histórico, CC0) e football-data.org (temporada corrente).

Os parsers não acessam a rede; `fetch_*` baixa, grava o arquivo bruto e o manifesto. O token do
football-data.org só vem de `FOOTBALL_DATA_ORG_TOKEN` e nunca é impresso.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from brasileirao.contracts import AllowedUse, LicenseStatus, MatchStatus, SourceManifest
from brasileirao.data_pipeline.football_data_org import MissingTokenError, parse_utc_instant
from brasileirao.serie_b.sources import sha256_bytes

OPENFOOTBALL_SOURCE = "openfootball"
FOOTBALL_DATA_SOURCE = "football_data_org"
FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
FOOTBALL_DATA_ATTRIBUTION = "Football data provided by the Football-Data.org API"
TERMS_CHECKED_AT = date(2026, 10, 29)
MIN_SECONDS_BETWEEN_CALLS = 6.5

MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTHS = {name: index for index, name in enumerate(MONTH_NAMES, start=1)}
ROUND_PATTERN = re.compile(r"^\s*▪\s*(?:Matchday|Regular Season\s*-|Round)\s*(\d+)\s*$")
DATE_PATTERN = re.compile(
    r"^\s*\[?(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.?\s+([A-Z][a-z]{2})/?\s*(\d{1,2})(?:\s+(\d{4}))?\]?\s*$"
)
TIME_PREFIX = r"(?:\d{1,2}[:.]\d{2}(?:\s*\([^)]*\))?\s+)?"
SCORE_MIDDLE_PATTERN = re.compile(
    rf"^\s+{TIME_PREFIX}(?P<home>\S.*?)\s+(?P<home_goals>\d+)-(?P<away_goals>\d+)"
    rf"(?:\s+\(\d+-\d+\))?(?:\s+(?P<note>\[[a-z ]+\]))?\s+(?P<away>\S.*?)\s*(?:@.*)?$"
)
VERSUS_PATTERN = re.compile(
    rf"^\s+{TIME_PREFIX}(?P<home>\S.*?)\s+v\s+(?P<away>\S.*?)"
    rf"(?:\s+(?P<home_goals>\d+)-(?P<away_goals>\d+)(?:\s+\(\d+-\d+\))?)?(?:\s+(?P<note>\[[a-z ]+\]))?\s*(?:@.*)?$"
)
KNOWN_NOTES = frozenset({"", "[awarded]"})
# Jogo cancelado não foi disputado: sai da lista (nunca vira placar).
SKIPPED_NOTES = frozenset({"[cancelled]"})


class SourceFormatError(ValueError):
    pass


@dataclass(frozen=True)
class FixtureRow:
    season: int
    round: int | None
    match_date: date
    home_name: str
    away_name: str
    home_goals: int | None
    away_goals: int | None


def _openfootball_date(line: str) -> tuple[str, int, int | None] | None:
    found = DATE_PATTERN.match(line)
    if found is None:
        return None
    return found.group(1), int(found.group(2)), int(found.group(3)) if found.group(3) else None


def parse_openfootball(text: str, season: int) -> list[FixtureRow]:
    """Football.TXT: "Casa 2-1 (1-0) Fora" (formato novo) ou "Casa v Fora 2-1" (antigo). Linhas de gols
    entre parênteses são ignoradas. Ano herdado da última data com ano; virada de ano detectada."""
    year = season
    current_round: int | None = None
    current_date: date | None = None
    scorer_depth = 0
    rows: list[FixtureRow] = []
    for line in text.splitlines():
        stripped = line.strip()
        if scorer_depth > 0 or stripped.startswith("("):
            scorer_depth += stripped.count("(") - stripped.count(")")
            scorer_depth = max(scorer_depth, 0)
            continue
        if not stripped or stripped.startswith(("#", "=")):
            continue
        round_found = ROUND_PATTERN.match(line)
        if round_found:
            current_round = int(round_found.group(1))
            continue
        if stripped.startswith("▪"):
            current_round = None
            continue
        day = _openfootball_date(line)
        if day:
            month_name, day_number, explicit_year = day
            if explicit_year:
                year = explicit_year
            candidate = date(year, MONTHS[month_name], day_number)
            if current_date is not None and (current_date - candidate).days > 180:
                year += 1
                candidate = date(year, MONTHS[month_name], day_number)
            current_date = candidate
            continue
        fixture = VERSUS_PATTERN.match(line) or SCORE_MIDDLE_PATTERN.match(line)
        if fixture is None or current_date is None:
            raise SourceFormatError(f"{season}: linha não reconhecida: {stripped!r}")
        note = (fixture.group("note") or "").strip()
        if note in SKIPPED_NOTES:
            continue
        if note not in KNOWN_NOTES:
            raise SourceFormatError(f"{season}: anotação desconhecida {note!r}")
        has_score = fixture.group("home_goals") is not None
        rows.append(
            FixtureRow(
                season=season,
                round=current_round,
                match_date=current_date,
                home_name=fixture.group("home").strip(),
                away_name=fixture.group("away").strip(),
                home_goals=int(fixture.group("home_goals")) if has_score else None,
                away_goals=int(fixture.group("away_goals")) if has_score else None,
            )
        )
    return rows


@dataclass(frozen=True)
class ApiMatch:
    source_match_id: str
    season: int
    round: int | None
    match_date: date
    kickoff_utc: datetime | None
    home_name: str
    away_name: str
    status: MatchStatus
    home_goals: int | None
    away_goals: int | None


API_FINISHED = frozenset({"FINISHED"})
API_PENDING = {
    "SCHEDULED": MatchStatus.SCHEDULED,
    "TIMED": MatchStatus.SCHEDULED,
    "IN_PLAY": MatchStatus.SCHEDULED,
    "PAUSED": MatchStatus.SCHEDULED,
    "LIVE": MatchStatus.SCHEDULED,
    "SUSPENDED": MatchStatus.SCHEDULED,
    "POSTPONED": MatchStatus.POSTPONED,
    "CANCELLED": MatchStatus.CANCELLED,
}


def parse_football_data(payload: dict[str, Any], season: int, timezone: str) -> list[ApiMatch]:
    """`IN_PLAY`/`PAUSED` viram `scheduled` (nunca placar parcial); `AWARDED` falha (sem decisão registrada)."""
    zone = ZoneInfo(timezone)
    rows: list[ApiMatch] = []
    for match in payload["matches"]:
        raw_status = str(match["status"])
        if raw_status == "AWARDED":
            raise SourceFormatError(f"jogo {match['id']} com resultado dado pela organização; registrar exceção")
        if raw_status not in API_FINISHED and raw_status not in API_PENDING:
            raise SourceFormatError(f"status desconhecido {raw_status!r} no jogo {match['id']}")
        instant = parse_utc_instant(str(match["utcDate"]))
        finished = raw_status in API_FINISHED
        full_time = match["score"]["fullTime"]
        if finished and (full_time["home"] is None or full_time["away"] is None):
            raise SourceFormatError(f"jogo {match['id']} encerrado sem placar")
        confirmed = raw_status != "SCHEDULED"
        rows.append(
            ApiMatch(
                source_match_id=str(match["id"]),
                season=season,
                round=int(match["matchday"]) if match.get("matchday") else None,
                match_date=instant.astimezone(zone).date(),
                kickoff_utc=instant if confirmed else None,
                home_name=str(match["homeTeam"]["name"]),
                away_name=str(match["awayTeam"]["name"]),
                status=MatchStatus.FINISHED if finished else API_PENDING[raw_status],
                home_goals=int(full_time["home"]) if finished else None,
                away_goals=int(full_time["away"]) if finished else None,
            )
        )
    return rows


def openfootball_manifest(repo: str, commit: str, files: dict[str, str], retrieved_at: datetime) -> SourceManifest:
    return SourceManifest(
        source_name=OPENFOOTBALL_SOURCE,
        origin=f"https://github.com/openfootball/{repo}/tree/{commit}",
        version=f"{repo}-{commit[:12]}",
        retrieved_at=retrieved_at,
        files=files,
        license_status=LicenseStatus.LICENSED_WITH_ATTRIBUTION,
        license_notes=(
            "CC0-1.0 declarada no repositório. Procedência dos resultados não informada (risco aceito pelo dono, "
            "ADR-0011); conferida contra o football-data.org nas temporadas em comum. Atribuição por cortesia."
        ),
        allowed_uses=[
            AllowedUse.RESEARCH_LOCAL,
            AllowedUse.PROTOTYPE_LOCAL,
            AllowedUse.PUBLIC_DISPLAY_DERIVED,
            AllowedUse.REDISTRIBUTION,
        ],
        license_name="CC0-1.0",
        terms_url=f"https://github.com/openfootball/{repo}/blob/{commit}/LICENSE.md",
        terms_checked_at=TERMS_CHECKED_AT,
        attribution="Resultados históricos: openfootball (domínio público, CC0)",
    )


def football_data_manifest(code: str, files: dict[str, str], retrieved_at: datetime) -> SourceManifest:
    return SourceManifest(
        source_name=FOOTBALL_DATA_SOURCE,
        origin=f"{FOOTBALL_DATA_BASE}/competitions/{code}/matches",
        version=f"v4-{code}-{retrieved_at.strftime('%Y%m%dT%H%M%SZ')}",
        retrieved_at=retrieved_at,
        files=files,
        license_status=LicenseStatus.LICENSED_WITH_ATTRIBUTION,
        license_notes=(
            f"Plano gratuito, competição {code}. Mesma chave e mesmas cláusulas do ADR-0008 (2.3, 6.1, 7.1, 9.1, "
            "11.1); uso limitado à temporada corrente e à conferência local (ADR-0011)."
        ),
        allowed_uses=[AllowedUse.RESEARCH_LOCAL, AllowedUse.PROTOTYPE_LOCAL, AllowedUse.PUBLIC_DISPLAY_DERIVED],
        license_name="football-data.org Terms and Conditions (em vigor desde 2018-06-01)",
        terms_url="https://www.football-data.org/terms",
        terms_checked_at=date(2026, 10, 27),
        attribution=FOOTBALL_DATA_ATTRIBUTION,
    )


def write_manifest(target_dir: Path, manifest: SourceManifest) -> None:
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def read_manifest(source_dir: Path) -> SourceManifest:
    return SourceManifest.model_validate_json((source_dir / "manifest.json").read_text(encoding="utf-8"))


def verify_files(source_dir: Path, manifest: SourceManifest) -> None:
    for file_name, expected in manifest.files.items():
        if sha256_bytes((source_dir / file_name).read_bytes()) != expected:
            raise SourceFormatError(f"{source_dir.name}/{file_name}: SHA-256 não confere com o manifesto")


def _get(url: str, headers: dict[str, str] | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "AIndaDa/0.1", **(headers or {})})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload: bytes = response.read()
    return payload


def season_folder(season: int) -> str:
    return f"{season}-{str(season + 1)[2:]}"


def fetch_openfootball(
    raw_dir: Path, repo: str, path: str, commit: str, seasons: list[int], expected_sha256: dict[str, str]
) -> Path:
    target_dir = raw_dir / OPENFOOTBALL_SOURCE / f"{repo}-{commit[:12]}"
    target_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for season in seasons:
        remote = f"{season_folder(season)}/{path}"
        content = _get(f"https://raw.githubusercontent.com/openfootball/{repo}/{commit}/{remote}")
        digest = sha256_bytes(content)
        local = remote.replace("/", "_")
        if local in expected_sha256 and expected_sha256[local] != digest:
            raise SourceFormatError(f"{remote}: SHA-256 {digest} difere do fixado")
        (target_dir / local).write_bytes(content)
        files[local] = digest
    write_manifest(target_dir, openfootball_manifest(repo, commit, files, datetime.now(tz=UTC)))
    return target_dir


def fetch_football_data(raw_dir: Path, code: str, seasons: list[int]) -> Path:
    token = os.environ.get("FOOTBALL_DATA_ORG_TOKEN", "").strip()
    if not token:
        raise MissingTokenError()
    retrieved_at = datetime.now(tz=UTC)
    target_dir = raw_dir / FOOTBALL_DATA_SOURCE / f"v4-{code}-{retrieved_at.strftime('%Y%m%dT%H%M%SZ')}"
    target_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for position, season in enumerate(seasons):
        if position:
            time.sleep(MIN_SECONDS_BETWEEN_CALLS)
        query = urllib.parse.urlencode({"season": season})
        url = f"{FOOTBALL_DATA_BASE}/competitions/{code}/matches?{query}"
        for attempt in range(3):
            try:
                content = _get(url, {"X-Auth-Token": token})
                break
            except urllib.error.HTTPError as error:
                if error.code != 429 or attempt == 2:
                    raise SourceFormatError(f"football-data.org devolveu {error.code} para {code} {season}") from None
                time.sleep(float(error.headers.get("X-RequestCounter-Reset", "60")) + 1)
        file_name = f"{code}_{season}.json"
        (target_dir / file_name).write_bytes(content)
        files[file_name] = sha256_bytes(content)
    write_manifest(target_dir, football_data_manifest(code, files, retrieved_at))
    return target_dir
