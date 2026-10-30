"""Fonte do Mundial de LoL (ADR-0013): artigos da Wikipédia em inglês (CC BY-SA 4.0).

Lê o modelo `{{Esports match}}` (uma série por bloco, com placar em mapas); a liga de cada time vem do cadastro
revisado `data/reference/lol_teams.csv`. Os parsers não acessam a rede; `fetch_article` baixa a revisão e grava
o manifesto.
"""

from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from brasileirao.contracts import AllowedUse, LicenseStatus, SourceManifest
from brasileirao.serie_b.sources import sha256_bytes

WIKIPEDIA_EN_API = "https://en.wikipedia.org/w/api.php"
SOURCE_NAME = "wikipedia_en"
USER_AGENT = "AIndaDa/0.1 (https://github.com/VitorBSP/aindada)"
MONTHS = {
    name: index
    for index, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
         "November", "December"),
        start=1,
    )
}  # fmt: skip
BLOCK_PATTERN = re.compile(r"\{\{Esports match\s*(.*?)\n\}\}", re.DOTALL)
FIELD_PATTERN = re.compile(r"^\|[ \t]*(\w+)[ \t]*=[ \t]*(.*?)[ \t]*$", re.MULTILINE)
HEADING_PATTERN = re.compile(r"^(==+)\s*(.+?)\s*\1\s*$", re.MULTILINE)
MAP_WINNER_PATTERN = re.compile(r"\b(\S+) wins\b")
TBD_NAMES = frozenset({"", "TBD", "TBA"})


class SourceFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Series:
    """Uma série (melhor de N). `score1`/`score2` = mapas vencidos; `None` enquanto não foi jogada."""

    event: str
    section: str
    label: str
    match_date: date
    team1: str
    team2: str
    score1: int | None
    score2: int | None
    maps_listed: int

    @property
    def played(self) -> bool:
        return self.score1 is not None and self.score2 is not None and self.score1 + self.score2 > 0

    @property
    def defined(self) -> bool:
        return self.team1 not in TBD_NAMES and self.team2 not in TBD_NAMES


def clean(value: str) -> str:
    without_refs = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", value, flags=re.DOTALL)
    without_links = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", without_refs)
    without_tags = re.sub(r"<[^>]+>", " ", without_links)
    return re.sub(r"\s+", " ", without_tags.replace("'''", "").replace("''", "")).strip()


def _score(value: str) -> int | None:
    cleaned = clean(value)
    if not cleaned:
        return None
    if not cleaned.isdigit():
        raise SourceFormatError(f"placar ilegível: {value!r}")
    return int(cleaned)


def parse_series(wikitext: str, event: str) -> list[Series]:
    headings = [
        (found.start(), len(found.group(1)), clean(found.group(2))) for found in HEADING_PATTERN.finditer(wikitext)
    ]
    rows: list[Series] = []
    for block in BLOCK_PATTERN.finditer(wikitext):
        fields = {name: value for name, value in FIELD_PATTERN.findall(block.group(1))}
        before = [(level, text) for position, level, text in headings if position < block.start()]
        top = next((text for level, text in reversed(before) if level == 2), "")
        sub = before[-1][1] if before and before[-1][0] > 2 else ""
        day_text = clean(fields.get("date", ""))
        day = re.fullmatch(
            r"(?P<day>\d{1,2}) (?P<month>[A-Z][a-z]+)|(?P<month2>[A-Z][a-z]+) (?P<day2>\d{1,2})", day_text
        )
        month_name = (day.group("month") or day.group("month2")) if day else None
        if day is None or month_name not in MONTHS:
            raise SourceFormatError(f"{event}: data ilegível {day_text!r}")
        day_number = int(day.group("day") or day.group("day2"))
        year = int(clean(fields.get("year", "")))
        rows.append(
            Series(
                event=event,
                section=f"{top} / {sub}" if sub else top,
                label=clean(fields.get("match", "")),
                match_date=date(year, MONTHS[month_name], day_number),
                team1=clean(fields.get("team1", "")),
                team2=clean(fields.get("team2", "")),
                score1=_score(fields.get("team1score", "")),
                score2=_score(fields.get("team2score", "")),
                maps_listed=sum(1 for name in fields if re.fullmatch(r"map\d+", name)),
            )
        )
    return rows


def article_manifest(title: str, revision_id: int, timestamp: str, files: dict[str, str]) -> SourceManifest:
    page = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    return SourceManifest(
        source_name=SOURCE_NAME,
        origin=f"{page}?oldid={revision_id}",
        version=f"{title.replace(' ', '_')}-r{revision_id}",
        retrieved_at=datetime.now(tz=UTC),
        files=files,
        license_status=LicenseStatus.LICENSED_WITH_ATTRIBUTION,
        license_notes=f"CC BY-SA 4.0 (rodapé da Wikipédia). Revisão {revision_id} de {timestamp}. Só resultados.",
        allowed_uses=[
            AllowedUse.RESEARCH_LOCAL,
            AllowedUse.PROTOTYPE_LOCAL,
            AllowedUse.PUBLIC_DISPLAY_DERIVED,
            AllowedUse.REDISTRIBUTION,
        ],
        license_name="CC BY-SA 4.0",
        terms_url="https://creativecommons.org/licenses/by-sa/4.0/deed.pt-br",
        terms_checked_at=date(2026, 10, 30),
        attribution=f'Resultados: colaboradores da Wikipédia em inglês, "{title}" (CC BY-SA 4.0)',
    )


def fetch_article(raw_dir: Path, title: str, revision_id: int | None = None) -> Path:
    query: dict[str, Any] = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "format": "json",
        "formatversion": "2",
    }
    if revision_id is None:
        query["titles"] = title
    else:
        query["revids"] = str(revision_id)
    request = urllib.request.Request(
        f"{WIKIPEDIA_EN_API}?{urllib.parse.urlencode(query)}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read())
    page = payload["query"]["pages"][0]
    if page.get("missing"):
        raise SourceFormatError(f"página não encontrada: {title}")
    revision = page["revisions"][0]
    content = str(revision["slots"]["main"]["content"]).encode("utf-8")
    target_dir = raw_dir / SOURCE_NAME / f"{title.replace(' ', '_')}-r{revision['revid']}"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "page.wikitext").write_bytes(content)
    manifest = article_manifest(
        title, int(revision["revid"]), str(revision["timestamp"]), {"page.wikitext": sha256_bytes(content)}
    )
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target_dir


@dataclass(frozen=True)
class TeamRegistry:
    by_name: dict[str, str]
    league: dict[str, str]
    display: dict[str, str]
    short: dict[str, str]

    def resolve(self, series: list[Series]) -> list[Series]:
        """Troca o nome de cada time pelo `team_id`; time desconhecido faz falhar (TBD fica como está)."""
        unknown = sorted(
            {name for s in series for name in (s.team1, s.team2) if name not in TBD_NAMES and name not in self.by_name}
        )
        if unknown:
            raise SourceFormatError(f"times sem cadastro em lol_teams.csv: {unknown}")
        return [
            replace(s, team1=self.by_name.get(s.team1, s.team1), team2=self.by_name.get(s.team2, s.team2))
            for s in series
        ]


def load_teams(path: Path) -> TeamRegistry:
    by_name: dict[str, str] = {}
    league: dict[str, str] = {}
    display: dict[str, str] = {}
    short: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            team_id = row["team_id"]
            league[team_id], display[team_id], short[team_id] = row["league"], row["display_name"], row["short_name"]
            for name in [row["display_name"], *(alias for alias in row["aliases"].split("|") if alias)]:
                if by_name.get(name, team_id) != team_id:
                    raise SourceFormatError(f"nome ambíguo no cadastro: {name}")
                by_name[name] = team_id
    return TeamRegistry(by_name, league, display, short)
