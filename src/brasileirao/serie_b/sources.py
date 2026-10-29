"""Fontes da Série B (ADR-0010): openfootball (CC0) e matriz de confrontos da Wikipédia pt (CC BY-SA 4.0).

Os parsers não acessam a rede; `fetch_*` baixa, grava o arquivo bruto e o manifesto.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from brasileirao.contracts import AllowedUse, LicenseStatus, SourceManifest

OPENFOOTBALL_SOURCE = "openfootball"
WIKIPEDIA_SOURCE = "wikipedia_pt"
OPENFOOTBALL_REPO = "openfootball/south-america"
WIKIPEDIA_API = "https://pt.wikipedia.org/w/api.php"
USER_AGENT = "AIndaDa/0.1 (https://github.com/VitorBSP/aindada)"
TERMS_CHECKED_AT = date(2026, 10, 29)

MONTHS_EN = {
    name: index
    for index, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), start=1
    )
}
MONTHS_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}  # fmt: skip

MATCHDAY_PATTERN = re.compile(r"^\s*▪?\s*Matchday\s+(\d+)\s*$")
DATE_PATTERN = re.compile(r"^\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?\s*$")
FIXTURE_PATTERN = re.compile(
    r"^\s+(?:\d{1,2}[:.]\d{2}\s+)?(?P<home>\S.*?)\s+v\s+(?P<away>\S.*?)"
    r"(?:\s+(?P<home_goals>\d+)-(?P<away_goals>\d+)(?:\s+\(\d+-\d+\))?(?P<note>\s+\[[a-z ]+\])?)?\s*$"
)
SEASON_HEADER_PATTERN = re.compile(r"^#\s*Date\s+\w{3}\s+[A-Z][a-z]{2}\s+\d{1,2}\s+(\d{4})")
WIKI_TEAM_PATTERN = re.compile(r"^\|team\d+\s*=\s*([A-Z0-9]+)", re.MULTILINE)
WIKI_TEAM_INLINE_PATTERN = re.compile(r"\|team\d+\s*=\s*([A-Z0-9]+)")
WIKI_NAME_PATTERN = re.compile(r"^\|name_([A-Z0-9]+)\s*=\s*(.+?)\s*$", re.MULTILINE)
WIKI_MATCH_PATTERN = re.compile(r"^\|match_([A-Z0-9]+)_([A-Z0-9]+)\s*=(.*)$", re.MULTILINE)
WIKI_UPDATE_PATTERN = re.compile(r"^\|update\s*=\s*(.+?)\s*$", re.MULTILINE)
SCORE_PATTERN = re.compile(r"^(\d+)\s*[–—-]\s*(\d+)$")


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
    awarded: bool


@dataclass(frozen=True)
class MatrixResult:
    home_name: str
    away_name: str
    home_goals: int | None
    away_goals: int | None


@dataclass(frozen=True)
class ResultsMatrix:
    season: int
    updated: str
    results: tuple[MatrixResult, ...]

    def cutoff_date(self) -> date | None:
        """Data do campo `update` da matriz ("27 de outubro"); `None` se a temporada estiver completa."""
        return parse_portuguese_day(self.updated, self.season)


def parse_portuguese_day(text: str, season: int) -> date | None:
    cleaned = text.strip().lower()
    if cleaned == "complete":
        return None
    match = re.fullmatch(r"(\d{1,2})\s+de\s+([a-zç]+)(?:\s+de\s+(\d{4}))?", cleaned)
    if match is None or match.group(2) not in MONTHS_PT:
        raise SourceFormatError(f"data de atualização ilegível: {text!r}")
    year = int(match.group(3)) if match.group(3) else season
    return date(year, MONTHS_PT[match.group(2)], int(match.group(1)))


def parse_openfootball(text: str, season: int) -> list[FixtureRow]:
    """Lê um arquivo Football.TXT (`YYYY_br2.txt`). Ano da data herdado da última linha com ano."""
    year: int | None = None
    current_round: int | None = None
    current_date: date | None = None
    rows: list[FixtureRow] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("="):
            continue
        header = SEASON_HEADER_PATTERN.match(line)
        if header:
            year = int(header.group(1))
            continue
        if line.lstrip().startswith("#"):
            continue
        matchday = MATCHDAY_PATTERN.match(line)
        if matchday:
            current_round = int(matchday.group(1))
            continue
        day = DATE_PATTERN.match(line)
        if day:
            month, day_number = MONTHS_EN[day.group(1)], int(day.group(2))
            if day.group(3):
                year = int(day.group(3))
            if year is None:
                raise SourceFormatError(f"{season}: data sem ano antes do cabeçalho: {line.strip()!r}")
            candidate = date(year, month, day_number)
            if current_date is not None and (current_date - candidate).days > 180:
                year += 1
                candidate = date(year, month, day_number)
            current_date = candidate
            continue
        fixture = FIXTURE_PATTERN.match(line)
        if fixture is None or current_date is None:
            raise SourceFormatError(f"{season}: linha não reconhecida: {line.strip()!r}")
        note = (fixture.group("note") or "").strip()
        if note and note != "[awarded]":
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
                awarded=note == "[awarded]",
            )
        )
    return rows


def _strip_wiki_markup(value: str) -> str:
    without_refs = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", value, flags=re.DOTALL)
    without_comments = re.sub(r"<!--.*?-->", "", without_refs, flags=re.DOTALL)
    without_links = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", without_comments)
    return re.sub(r"<[^>]+>", "", without_links).strip()


def _wiki_team_name(value: str) -> str:
    template = re.search(r"\{\{\s*Futebol\s+([^}|]+?)\s*(?:\|[^}]*)?\}\}", value)
    if template:
        return template.group(1).strip()
    return _strip_wiki_markup(value)


def parse_wikipedia_matrix(wikitext: str, season: int) -> ResultsMatrix:
    """Lê o módulo `sports results` (seção "Confrontos"): linha = mandante, coluna = visitante."""
    start = wikitext.find("{{#invoke:sports results")
    if start < 0:
        raise SourceFormatError(f"{season}: matriz de confrontos não encontrada")
    end = wikitext.find("\n}}", start)
    block = wikitext[start : end if end > 0 else len(wikitext)]
    codes = WIKI_TEAM_INLINE_PATTERN.findall(block.split("|name_", 1)[0])
    names = {code: _wiki_team_name(value) for code, value in WIKI_NAME_PATTERN.findall(block)}
    missing_names = [code for code in codes if code not in names]
    if not codes or missing_names:
        raise SourceFormatError(f"{season}: códigos sem nome na matriz: {missing_names}")
    results: dict[tuple[str, str], MatrixResult] = {}
    for home_code, away_code, raw_value in WIKI_MATCH_PATTERN.findall(block):
        if home_code not in names or away_code not in names:
            continue
        value = _strip_wiki_markup(raw_value)
        score = SCORE_PATTERN.match(value)
        if value and score is None:
            raise SourceFormatError(f"{season}: placar ilegível em {home_code} x {away_code}: {value!r}")
        results[(home_code, away_code)] = MatrixResult(
            home_name=names[home_code],
            away_name=names[away_code],
            home_goals=int(score.group(1)) if score else None,
            away_goals=int(score.group(2)) if score else None,
        )
    expected_pairs = {(home, away) for home in codes for away in codes if home != away}
    if set(results) != expected_pairs:
        missing_pairs = sorted(expected_pairs - set(results))[:5]
        raise SourceFormatError(
            f"{season}: matriz incompleta; faltam {len(expected_pairs - set(results))}, ex.: {missing_pairs}"
        )
    update = WIKI_UPDATE_PATTERN.search(block)
    return ResultsMatrix(
        season=season,
        updated=update.group(1) if update else "",
        results=tuple(results[pair] for pair in sorted(results)),
    )


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _http_get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload: bytes = response.read()
    return payload


def wikipedia_title(season: int) -> str:
    return f"Campeonato Brasileiro de Futebol de {season} - Série B"


def openfootball_manifest(commit: str, files: dict[str, str], retrieved_at: datetime) -> SourceManifest:
    return SourceManifest(
        source_name=OPENFOOTBALL_SOURCE,
        origin=f"https://github.com/{OPENFOOTBALL_REPO}/tree/{commit}/brazil",
        version=commit[:12],
        retrieved_at=retrieved_at,
        files=files,
        license_status=LicenseStatus.LICENSED_WITH_ATTRIBUTION,
        license_notes=(
            "CC0-1.0 declarada no repositório (API de licenças do GitHub). Proveniência de segunda mão: o "
            "repositório não diz de onde vêm os resultados da Série B; risco aceito pelo dono (ADR-0010). "
            "Atribuição dada por cortesia, não exigida pela CC0."
        ),
        allowed_uses=[
            AllowedUse.RESEARCH_LOCAL,
            AllowedUse.PROTOTYPE_LOCAL,
            AllowedUse.PUBLIC_DISPLAY_DERIVED,
            AllowedUse.REDISTRIBUTION,
        ],
        license_name="CC0-1.0",
        terms_url=f"https://github.com/{OPENFOOTBALL_REPO}/blob/{commit}/LICENSE.md",
        terms_checked_at=TERMS_CHECKED_AT,
        attribution="Resultados históricos: openfootball (domínio público, CC0)",
    )


def wikipedia_manifest(season: int, revision_id: int, revision_timestamp: str, files: dict[str, str],
                       retrieved_at: datetime) -> SourceManifest:  # fmt: skip
    title = wikipedia_title(season)
    page_url = "https://pt.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    return SourceManifest(
        source_name=WIKIPEDIA_SOURCE,
        origin=f"{page_url}?oldid={revision_id}",
        version=f"{season}-r{revision_id}",
        retrieved_at=retrieved_at,
        files=files,
        license_status=LicenseStatus.LICENSED_WITH_ATTRIBUTION,
        license_notes=(
            f"CC BY-SA 4.0 (rodapé da página). Revisão {revision_id} de {revision_timestamp}. Só a matriz de "
            "confrontos é lida. Placar é fato; a atribuição e o compartilhamento pela mesma licença valem para "
            "qualquer redistribuição da matriz, que o projeto não faz (ADR-0010)."
        ),
        allowed_uses=[
            AllowedUse.RESEARCH_LOCAL,
            AllowedUse.PROTOTYPE_LOCAL,
            AllowedUse.PUBLIC_DISPLAY_DERIVED,
            AllowedUse.REDISTRIBUTION,
        ],
        license_name="CC BY-SA 4.0",
        terms_url="https://creativecommons.org/licenses/by-sa/4.0/deed.pt-br",
        terms_checked_at=TERMS_CHECKED_AT,
        attribution=f'Resultados de {season}: colaboradores da Wikipédia em português, "{title}" (CC BY-SA 4.0)',
    )


def _write_manifest(target_dir: Path, manifest: SourceManifest) -> None:
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def fetch_openfootball(raw_dir: Path, commit: str, seasons: list[int], expected_sha256: dict[str, str]) -> Path:
    target_dir = raw_dir / OPENFOOTBALL_SOURCE / commit[:12]
    target_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for season in seasons:
        file_name = f"{season}_br2.txt"
        content = _http_get(f"https://raw.githubusercontent.com/{OPENFOOTBALL_REPO}/{commit}/brazil/{file_name}")
        digest = sha256_bytes(content)
        if file_name in expected_sha256 and expected_sha256[file_name] != digest:
            raise SourceFormatError(f"{file_name}: SHA-256 {digest} difere do fixado {expected_sha256[file_name]}")
        (target_dir / file_name).write_bytes(content)
        files[file_name] = digest
    _write_manifest(target_dir, openfootball_manifest(commit, files, datetime.now(tz=UTC)))
    return target_dir


def standings_title(season: int) -> str:
    return f"Predefinição:Tabela do Campeonato Brasileiro da Série B - {season}"


def _fetch_revision(title: str | None, revision_id: int | None) -> dict[str, Any]:
    query = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "format": "json",
        "formatversion": "2",
    }
    if revision_id is None:
        query["titles"] = str(title)
    else:
        query["revids"] = str(revision_id)
    payload = json.loads(_http_get(f"{WIKIPEDIA_API}?{urllib.parse.urlencode(query)}"))
    page = payload["query"]["pages"][0]
    if page.get("missing"):
        raise SourceFormatError(f"página não encontrada: {title or revision_id}")
    revision: dict[str, Any] = page["revisions"][0]
    return revision


def fetch_wikipedia(raw_dir: Path, season: int, revision_id: int | None = None) -> Path:
    """Baixa a revisão fixada (ou a mais recente) da página da temporada.

    Sem revisão fixada (temporada corrente), baixa também a predefinição de classificação, usada para
    conferir a matriz (`standings.wikitext`).
    """
    revision = _fetch_revision(wikipedia_title(season), revision_id)
    content = str(revision["slots"]["main"]["content"]).encode("utf-8")
    target_dir = raw_dir / WIKIPEDIA_SOURCE / f"{season}-r{revision['revid']}"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "page.wikitext").write_bytes(content)
    files = {"page.wikitext": sha256_bytes(content)}
    timestamp = str(revision["timestamp"])
    if revision_id is None:
        standings = _fetch_revision(standings_title(season), None)
        standings_content = str(standings["slots"]["main"]["content"]).encode("utf-8")
        (target_dir / "standings.wikitext").write_bytes(standings_content)
        files["standings.wikitext"] = sha256_bytes(standings_content)
        timestamp += f"; classificação: revisão {standings['revid']} de {standings['timestamp']}"
    manifest = wikipedia_manifest(season, int(revision["revid"]), timestamp, files, datetime.now(tz=UTC))
    _write_manifest(target_dir, manifest)
    return target_dir


STANDINGS_STAT_PATTERN = re.compile(r"\|(win|draw|loss|gf|ga|adjust_points)_([A-Z0-9]+)\s*=\s*([-+]?\d+)")


@dataclass(frozen=True)
class StandingsTable:
    updated: str
    stats: dict[str, tuple[int, int, int, int, int]]
    point_adjustments: dict[str, int]


def parse_wikipedia_standings(wikitext: str, season: int) -> StandingsTable:
    """Lê a predefinição `Sports table`: vitórias, empates, derrotas, gols pró e contra por clube."""
    if "{{#invoke:Sports table" not in wikitext:
        raise SourceFormatError(f"{season}: predefinição de classificação sem o módulo Sports table")
    names = {code: _wiki_team_name(value) for code, value in WIKI_NAME_PATTERN.findall(wikitext)}
    values: dict[str, dict[str, int]] = {}
    for field, code, value in STANDINGS_STAT_PATTERN.findall(wikitext):
        values.setdefault(code, {})[field] = int(value)
    missing = [code for code in names if not {"win", "draw", "loss", "gf", "ga"} <= set(values.get(code, {}))]
    if not names or missing:
        raise SourceFormatError(f"{season}: classificação incompleta para {missing}")
    update = WIKI_UPDATE_PATTERN.search(wikitext)
    return StandingsTable(
        updated=update.group(1) if update else "",
        stats={
            names[code]: tuple(values[code][field] for field in ("win", "draw", "loss", "gf", "ga"))  # type: ignore[misc]
            for code in names
        },
        point_adjustments={names[code]: values[code].get("adjust_points", 0) for code in names},
    )


def read_manifest(source_dir: Path) -> SourceManifest:
    return SourceManifest.model_validate_json((source_dir / "manifest.json").read_text(encoding="utf-8"))


def verify_files(source_dir: Path, manifest: SourceManifest) -> None:
    for file_name, expected in manifest.files.items():
        actual = sha256_bytes((source_dir / file_name).read_bytes())
        if actual != expected:
            raise SourceFormatError(f"{source_dir.name}/{file_name}: SHA-256 não confere com o manifesto")
