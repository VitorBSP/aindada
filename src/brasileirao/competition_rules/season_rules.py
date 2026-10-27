"""Carregamento das regras versionadas por temporada."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

SEASONS_DIR = Path(__file__).parent / "seasons"
FOREIGN_PREFIX = "foreign:"


class Phase(StrEnum):
    GROUPS = "groups"
    PRELIM = "prelim"


PHASE_RANK = {Phase.GROUPS: 0, Phase.PRELIM: 1}


class CupRedirectPolicy(StrEnum):
    EQUIVALENT_SLOT_ONLY = "equivalent_slot_only"
    ANY_OTHER_QUALIFICATION = "any_other_qualification"


@dataclass(frozen=True)
class ExternalContext:
    as_of: str
    libertadores_champion: str
    libertadores_finalists: tuple[str, ...]
    sudamericana_champion: str
    sudamericana_finalists: tuple[str, ...]
    cup_champion: str
    cup_runner_up: str
    cup_semifinals: tuple[tuple[str, str], ...]
    notes: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class SeasonRules:
    season: int
    name: str
    n_clubs: int
    points_win: int
    points_draw: int
    regulation_title: str
    regulation_url: str
    regulation_date: str
    tiebreak_order: tuple[str, ...]
    head_to_head_max_clubs: int
    relegation_count: int
    league_slots: tuple[Phase, ...]
    cup_champion_phase: Phase
    cup_runner_up_phase: Phase
    continental_title_phase: Phase
    cup_redirect_policy: CupRedirectPolicy
    sudamericana_count: int
    external: ExternalContext


def is_foreign(club_reference: str) -> bool:
    return club_reference.startswith(FOREIGN_PREFIX)


def load_season_rules(season: int, seasons_dir: Path = SEASONS_DIR) -> SeasonRules:
    rules_path = seasons_dir / f"serie_a_{season}.toml"
    if not rules_path.exists():
        raise FileNotFoundError(f"regras da temporada {season} não cadastradas: {rules_path}")
    raw_rules = tomllib.loads(rules_path.read_text(encoding="utf-8"))
    competition = raw_rules["competition"]
    libertadores = raw_rules["libertadores"]
    external = raw_rules.get("external", {})
    return SeasonRules(
        season=int(competition["season"]),
        name=str(competition["name"]),
        n_clubs=int(competition["n_clubs"]),
        points_win=int(competition["points_win"]),
        points_draw=int(competition["points_draw"]),
        regulation_title=str(competition["regulation_title"]),
        regulation_url=str(competition["regulation_url"]),
        regulation_date=str(competition["regulation_date"]),
        tiebreak_order=tuple(raw_rules["tiebreakers"]["order"]),
        head_to_head_max_clubs=int(raw_rules["tiebreakers"]["head_to_head_max_clubs"]),
        relegation_count=int(raw_rules["relegation"]["count"]),
        league_slots=tuple(Phase(slot) for slot in libertadores["league_slots"]),
        cup_champion_phase=Phase(libertadores["cup_champion_phase"]),
        cup_runner_up_phase=Phase(libertadores["cup_runner_up_phase"]),
        continental_title_phase=Phase(libertadores["continental_title_phase"]),
        cup_redirect_policy=CupRedirectPolicy(libertadores["cup_redirect_policy"]),
        sudamericana_count=int(raw_rules["sudamericana"]["count"]),
        external=ExternalContext(
            as_of=str(external.get("as_of", "")),
            libertadores_champion=str(external.get("libertadores_champion", "")),
            libertadores_finalists=tuple(external.get("libertadores_finalists", [])),
            sudamericana_champion=str(external.get("sudamericana_champion", "")),
            sudamericana_finalists=tuple(external.get("sudamericana_finalists", [])),
            cup_champion=str(external.get("cup_champion", "")),
            cup_runner_up=str(external.get("cup_runner_up", "")),
            cup_semifinals=tuple((str(pair[0]), str(pair[1])) for pair in external.get("cup_semifinals", [])),
            notes=tuple(
                str(external[key]) for key in ("libertadores_note", "sudamericana_note", "cup_note") if key in external
            ),
            sources=tuple(external.get("sources", [])),
        ),
    )
