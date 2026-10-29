"""Elo único entre ligas (ADR-0012, Decisão 3).

Todos os clubes num mesmo conjunto de ratings: os jogos das ligas nacionais ordenam os clubes dentro de cada
país e os jogos das copas europeias ligam os países. Entre temporadas, cada clube volta parte do caminho para
a média do seu país. Clube novo entra abaixo da média do país (`newcomer_offset`); país sem clube conhecido
entra em `initial_rating - unknown_offset`. A feature `elo_diff` já inclui o mando (zero em campo neutro).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from brasileirao.config import EloParams
from brasileirao.contracts import MatchStatus
from brasileirao.frame_values import as_int
from brasileirao.ratings.elo import elo_delta

CUP_COMPETITIONS = frozenset({"CL", "EL", "CONF"})


@dataclass(frozen=True)
class GlobalEloParams:
    k_factor: float = 20.0
    home_advantage: float = 60.0
    season_regression: float = 0.2
    newcomer_offset: float = 75.0
    unknown_offset: float = 150.0
    initial_rating: float = 1500.0


@dataclass
class GlobalEloState:
    ratings: dict[str, float] = field(default_factory=dict)
    season: int | None = None

    def country_mean(self, country: str, countries: Mapping[str, str]) -> float | None:
        values = [rating for club, rating in self.ratings.items() if countries.get(club) == country]
        return float(np.mean(values)) if len(values) >= 3 else None


class GlobalElo:
    def __init__(self, params: GlobalEloParams, countries: Mapping[str, str]) -> None:
        self.params = params
        self.countries = countries
        self.state = GlobalEloState()
        self.first_season = True

    def _ensure(self, club: str, domestic: bool) -> float:
        """Na primeira temporada, clube de liga nacional começa no valor base; depois, abaixo da média do país."""
        if club not in self.state.ratings:
            country_mean = self.state.country_mean(self.countries[club], self.countries)
            if domestic and self.first_season:
                rating = self.params.initial_rating
            elif country_mean is not None:
                rating = country_mean - (self.params.newcomer_offset if domestic else 0.0)
            else:
                rating = self.params.initial_rating - self.params.unknown_offset
            self.state.ratings[club] = rating
        return self.state.ratings[club]

    def _start_season(self, season: int) -> None:
        if self.state.season is not None:
            by_country: dict[str, list[float]] = defaultdict(list)
            for club, rating in self.state.ratings.items():
                by_country[self.countries[club]].append(rating)
            means = {country: float(np.mean(values)) for country, values in by_country.items()}
            keep = 1.0 - self.params.season_regression
            self.state.ratings = {
                club: means[self.countries[club]] + (rating - means[self.countries[club]]) * keep
                for club, rating in self.state.ratings.items()
            }
            self.first_season = False
        self.state.season = season

    def effective_diff(self, home: str, away: str, neutral: bool, domestic: bool = False) -> float:
        advantage = 0.0 if neutral else self.params.home_advantage
        return self._ensure(home, domestic) + advantage - self._ensure(away, domestic)

    def run(self, matches_data: pd.DataFrame) -> pd.DataFrame:
        """Processa os jogos encerrados em ordem; jogos do mesmo dia usam o estado anterior ao dia."""
        finished = matches_data[matches_data["status"] == MatchStatus.FINISHED.value].sort_values(
            ["match_date", "match_id"]
        )
        rows: list[dict[str, object]] = []
        for (season, _), day in finished.groupby(["season", "match_date"], sort=True):
            season_number = int(str(season))
            if self.state.season != season_number:
                self._start_season(season_number)
            updates: dict[str, float] = defaultdict(float)
            for match in day.itertuples(index=False):
                home, away, neutral = str(match.home_id), str(match.away_id), bool(match.neutral)
                diff = self.effective_diff(home, away, neutral, str(match.competition) not in CUP_COMPETITIONS)
                home_goals, away_goals = as_int(match.home_goals), as_int(match.away_goals)
                rows.append(
                    {
                        "match_id": match.match_id,
                        "season": season_number,
                        "competition": match.competition,
                        "match_date": match.match_date,
                        "home_id": home,
                        "away_id": away,
                        "neutral": neutral,
                        "home_goals": home_goals,
                        "away_goals": away_goals,
                        "elo_diff": diff,
                    }
                )
                delta = float(
                    elo_delta(
                        self.state.ratings[home],
                        self.state.ratings[away],
                        float(home_goals),
                        float(away_goals),
                        EloParams(
                            k_factor=self.params.k_factor,
                            home_advantage=0.0 if neutral else self.params.home_advantage,
                        ),
                    )
                )
                updates[home] += delta
                updates[away] -= delta
            for club, step in updates.items():
                self.state.ratings[club] += step
        return pd.DataFrame(rows)

    def rating(self, club: str) -> float:
        """Rating atual; clube ainda sem jogo recebe o valor inicial do seu país (como numa copa)."""
        return self._ensure(club, domestic=False)

    def start_season_if_needed(self, season: int) -> None:
        if self.state.season != season:
            self._start_season(season)
