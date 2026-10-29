"""Regulamento de liga por competição e temporada (`competition_rules/seasons/<código>_<temporada>.toml`)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from brasileirao.competition_rules.season_rules import (
    SEASONS_DIR,
    CupRedirectPolicy,
    ExternalContext,
    Phase,
    SeasonRules,
)
from brasileirao.leagues.ranking import validate_tiebreak_order


@dataclass(frozen=True)
class Zone:
    zone_id: str
    label: str
    first: int
    last: int
    kind: str
    note: str = ""


@dataclass(frozen=True)
class LeagueRules:
    code: str
    season: int
    season_label: str
    name: str
    n_clubs: int
    points_win: int
    points_draw: int
    timezone: str
    regulation_title: str
    regulation_url: str
    regulation_date: str
    regulation_note: str
    tiebreak_order: tuple[str, ...]
    lot_note: str
    zones: tuple[Zone, ...]

    @property
    def relegation_count(self) -> int:
        return sum(zone.last - zone.first + 1 for zone in self.zones if zone.kind == "down")

    def league_rules(self) -> SeasonRules:
        """Visão mínima para o motor da Série A (totais de pontos); o desempate fica com `LeagueSimulator`."""
        return SeasonRules(
            season=self.season,
            name=self.name,
            n_clubs=self.n_clubs,
            points_win=self.points_win,
            points_draw=self.points_draw,
            regulation_title=self.regulation_title,
            regulation_url=self.regulation_url,
            regulation_date=self.regulation_date,
            tiebreak_order=self.tiebreak_order,
            head_to_head_max_clubs=self.n_clubs,
            relegation_count=self.relegation_count,
            league_slots=(),
            cup_champion_phase=Phase.GROUPS,
            cup_runner_up_phase=Phase.PRELIM,
            continental_title_phase=Phase.GROUPS,
            cup_redirect_policy=CupRedirectPolicy.EQUIVALENT_SLOT_ONLY,
            sudamericana_count=0,
            external=ExternalContext("", "", (), "", (), "", "", (), (), ()),
        )


def rules_file_name(code: str, season: int) -> str:
    return f"{code.replace('-', '_')}_{season}.toml"


def load_league_rules(code: str, season: int, seasons_dir: Path = SEASONS_DIR) -> LeagueRules:
    rules_path = seasons_dir / rules_file_name(code, season)
    if not rules_path.exists():
        raise FileNotFoundError(f"regras de {code} {season} não cadastradas: {rules_path}")
    raw_rules = tomllib.loads(rules_path.read_text(encoding="utf-8"))
    competition = raw_rules["competition"]
    if competition["code"] != code or int(competition["season"]) != season:
        raise ValueError(f"{rules_path.name} declara {competition['code']} {competition['season']}")
    n_clubs = int(competition["n_clubs"])
    zones = tuple(
        Zone(
            zone_id=str(zone["id"]),
            label=str(zone["label"]),
            first=int(zone["first"]),
            last=int(zone["last"]),
            kind=str(zone["kind"]),
            note=str(zone.get("note", "")),
        )
        for zone in raw_rules["zones"]
    )
    for zone in zones:
        if not 1 <= zone.first <= zone.last <= n_clubs or zone.kind not in ("title", "up", "down"):
            raise ValueError(f"zona inválida em {rules_path.name}: {zone}")
    return LeagueRules(
        code=code,
        season=season,
        season_label=str(competition["season_label"]),
        name=str(competition["name"]),
        n_clubs=n_clubs,
        points_win=int(competition["points_win"]),
        points_draw=int(competition["points_draw"]),
        timezone=str(competition["timezone"]),
        regulation_title=str(competition["regulation_title"]),
        regulation_url=str(competition["regulation_url"]),
        regulation_date=str(competition["regulation_date"]),
        regulation_note=str(competition.get("regulation_note", "")),
        tiebreak_order=validate_tiebreak_order(raw_rules["tiebreakers"]["order"]),
        lot_note=str(raw_rules["tiebreakers"]["lot_note"]),
        zones=zones,
    )
