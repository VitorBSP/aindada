"""Fontes da Champions League (ADR-0012): copas europeias do openfootball (CC0) e football-data.org (`CL`).

Formato das copas no openfootball: "Casa (PAÍS) v Fora (PAÍS) placar", com prorrogação ("2-1 a.e.t. (1-1, 0-0)":
120 minutos, depois 90 minutos e intervalo) e pênaltis ("4-2 pen. 1-0 a.e.t. (1-0, 1-0)").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from brasileirao.leagues.sources import MONTHS, SourceFormatError

STAGE_PATTERN = re.compile(r"^\s*▪\s*(?P<stage>.+?)\s*$")
DATE_PATTERN = re.compile(r"^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?\s*$")
TEAM = r"(?P<{name}>\S.*?)\s+\((?P<{name}_country>[A-Z]{{3}})\)"
FIXTURE_PATTERN = re.compile(
    r"^\s+(?:\d{1,2}[:.]\d{2}\s+)?"
    + TEAM.format(name="home")
    + r"\s+v\s+"
    + TEAM.format(name="away")
    + r"(?:\s+(?P<tail>.*?))?\s*$"
)
REGULAR_PATTERN = re.compile(r"^(?P<home>\d+)-(?P<away>\d+)(?:\s+\(\d+-\d+\))?$")
EXTRA_TIME_PATTERN = re.compile(
    r"^(?:(?P<pen_home>\d+)-(?P<pen_away>\d+)\s+pen\.\s+)?(?P<aet_home>\d+)-(?P<aet_away>\d+)\s+a\.e\.t\."
    r"\s+\((?P<home>\d+)-(?P<away>\d+)(?:,\s*\d+-\d+)?\)$"
)
# Jogo cancelado ou resultado dado pela organização (W.O.) não é jogo disputado: fica fora dos ratings.
SKIPPED_TAILS = frozenset({"[cancelled]", "[annulled]"})


@dataclass(frozen=True)
class CupMatch:
    """Placar dos 90 minutos (o que o modelo de gols prevê) e, se houve, prorrogação e pênaltis."""

    competition: str
    season: int
    stage: str
    match_date: date
    home_name: str
    home_country: str
    away_name: str
    away_country: str
    home_goals: int | None
    away_goals: int | None
    extra_time: tuple[int, int] | None = None
    penalties: tuple[int, int] | None = None


def _tail_score(tail: str) -> tuple[tuple[int, int] | None, tuple[int, int] | None, tuple[int, int] | None]:
    regular = REGULAR_PATTERN.match(tail)
    if regular:
        return (int(regular.group("home")), int(regular.group("away"))), None, None
    extra = EXTRA_TIME_PATTERN.match(tail)
    if extra is None:
        raise SourceFormatError(f"placar ilegível: {tail!r}")
    penalties = None
    if extra.group("pen_home") is not None:
        penalties = (int(extra.group("pen_home")), int(extra.group("pen_away")))
    return (
        (int(extra.group("home")), int(extra.group("away"))),
        (int(extra.group("aet_home")), int(extra.group("aet_away"))),
        penalties,
    )


def parse_cup(text: str, competition: str, season: int) -> list[CupMatch]:
    year = season
    stage = ""
    current_date: date | None = None
    rows: list[CupMatch] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "=")):
            continue
        stage_found = STAGE_PATTERN.match(line)
        if stage_found:
            stage = stage_found.group("stage")
            continue
        day = DATE_PATTERN.match(line)
        if day:
            if day.group(3):
                year = int(day.group(3))
            candidate = date(year, MONTHS[day.group(1)], int(day.group(2)))
            if current_date is not None and (current_date - candidate).days > 180:
                year += 1
                candidate = date(year, MONTHS[day.group(1)], int(day.group(2)))
            current_date = candidate
            continue
        fixture = FIXTURE_PATTERN.match(line)
        if fixture is None or current_date is None:
            raise SourceFormatError(f"{competition} {season}: linha não reconhecida: {stripped!r}")
        tail = (fixture.group("tail") or "").strip()
        if tail in SKIPPED_TAILS or tail.endswith("[awarded]"):
            continue
        regular, extra_time, penalties = _tail_score(tail) if tail else (None, None, None)
        rows.append(
            CupMatch(
                competition=competition,
                season=season,
                stage=stage,
                match_date=current_date,
                home_name=fixture.group("home").strip(),
                home_country=fixture.group("home_country"),
                away_name=fixture.group("away").strip(),
                away_country=fixture.group("away_country"),
                home_goals=None if regular is None else regular[0],
                away_goals=None if regular is None else regular[1],
                extra_time=extra_time,
                penalties=penalties,
            )
        )
    return rows
