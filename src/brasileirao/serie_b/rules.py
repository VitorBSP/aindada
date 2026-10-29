"""Regulamento da Série B por temporada (Art. 5º, 12 e 13 do REC 2026)."""

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


@dataclass(frozen=True)
class SerieBRules:
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
    direct_promotion_count: int
    playoff_groups: tuple[tuple[int, int], ...]
    relegation_count: int

    @property
    def promotion_count(self) -> int:
        return self.direct_promotion_count + len(self.playoff_groups)

    def league_rules(self) -> SeasonRules:
        """Visão da tabela para o simulador e o desempate; sem vagas continentais."""
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
            head_to_head_max_clubs=self.head_to_head_max_clubs,
            relegation_count=self.relegation_count,
            league_slots=(),
            cup_champion_phase=Phase.GROUPS,
            cup_runner_up_phase=Phase.PRELIM,
            continental_title_phase=Phase.GROUPS,
            cup_redirect_policy=CupRedirectPolicy.EQUIVALENT_SLOT_ONLY,
            sudamericana_count=0,
            external=ExternalContext("", "", (), "", (), "", "", (), (), ()),
        )


def load_serie_b_rules(season: int, seasons_dir: Path = SEASONS_DIR) -> SerieBRules:
    rules_path = seasons_dir / f"serie_b_{season}.toml"
    if not rules_path.exists():
        raise FileNotFoundError(f"regras da Série B {season} não cadastradas: {rules_path}")
    raw_rules = tomllib.loads(rules_path.read_text(encoding="utf-8"))
    competition = raw_rules["competition"]
    groups = tuple((int(group[0]), int(group[1])) for group in raw_rules["playoffs"]["groups"])
    n_clubs = int(competition["n_clubs"])
    direct = int(raw_rules["promotion"]["direct_count"])
    for better, worse in groups:
        if not direct < better < worse <= n_clubs:
            raise ValueError(f"grupo de playoff inválido: {better} x {worse}")
    return SerieBRules(
        season=int(competition["season"]),
        name=str(competition["name"]),
        n_clubs=n_clubs,
        points_win=int(competition["points_win"]),
        points_draw=int(competition["points_draw"]),
        regulation_title=str(competition["regulation_title"]),
        regulation_url=str(competition["regulation_url"]),
        regulation_date=str(competition["regulation_date"]),
        tiebreak_order=tuple(raw_rules["tiebreakers"]["order"]),
        head_to_head_max_clubs=int(raw_rules["tiebreakers"]["head_to_head_max_clubs"]),
        direct_promotion_count=direct,
        playoff_groups=groups,
        relegation_count=int(raw_rules["relegation"]["count"]),
    )
