"""Elo em dois níveis: força da liga + ajuste do time dentro da liga (ADR-0013; ideia do dono do produto).

Força de um time = força da liga + ajuste do time. Cada série atualiza o ajuste dos dois times com `k_team` e,
se as ligas forem diferentes, a força das duas ligas com `k_league`, sempre pela surpresa em mapas:
mapas vencidos − mapas jogados × chance esperada de um mapa (calculada antes da série). A liga junta os
resultados de todos os seus times, o que compensa as poucas séries de cada time em eventos internacionais.
Na virada do ano, o ajuste de cada time volta parte do caminho até zero (`team_regression`); a força da liga
continua. Sem lado do mapa nem mando: eventos internacionais.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from brasileirao.esports.sources import Series


@dataclass(frozen=True)
class LeagueTeamParams:
    k_league: float = 24.0
    k_team: float = 8.0
    team_regression: float = 1.0


def map_probability(rating: float, opponent: float) -> float:
    return float(1.0 / (1.0 + 10.0 ** ((opponent - rating) / 400.0)))


def series_probability(map_win: float, best_of: int) -> float:
    """Chance de vencer uma melhor de N com mapas independentes."""
    needed = best_of // 2 + 1
    return sum(
        math.comb(needed - 1 + losses, losses) * map_win**needed * (1 - map_win) ** losses for losses in range(needed)
    )


def best_of(series: Series) -> int:
    if series.score1 is None or series.score2 is None:
        raise ValueError("série sem placar")
    return 2 * max(series.score1, series.score2) - 1


@dataclass(frozen=True)
class Prediction:
    series: Series
    map_win: float
    series_win: float


@dataclass
class LeagueTeamElo:
    params: LeagueTeamParams
    leagues: Mapping[str, str]
    league_strength: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    team_adjustment: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    year: int | None = None

    def rating(self, team: str) -> float:
        return self.league_strength[self.leagues[team]] + self.team_adjustment[team]

    def run(self, series: Iterable[Series]) -> list[Prediction]:
        """Processa as séries jogadas em ordem; a previsão de cada uma usa só o que veio antes."""
        predictions: list[Prediction] = []
        for item in sorted((s for s in series if s.played), key=lambda s: (s.match_date, s.event, s.label)):
            if self.year is not None and item.match_date.year != self.year:
                keep = 1.0 - self.params.team_regression
                for team in list(self.team_adjustment):
                    self.team_adjustment[team] *= keep
            self.year = item.match_date.year
            expected = map_probability(self.rating(item.team1), self.rating(item.team2))
            predictions.append(Prediction(item, expected, series_probability(expected, best_of(item))))
            assert item.score1 is not None and item.score2 is not None
            surprise = item.score1 - (item.score1 + item.score2) * expected
            self.team_adjustment[item.team1] += self.params.k_team * surprise
            self.team_adjustment[item.team2] -= self.params.k_team * surprise
            first_league, second_league = self.leagues[item.team1], self.leagues[item.team2]
            if first_league != second_league:
                self.league_strength[first_league] += self.params.k_league * surprise
                self.league_strength[second_league] -= self.params.k_league * surprise
        return predictions


def log_losses(predictions: Sequence[Prediction]) -> dict[str, float]:
    """Log loss por mapa e por série; a referência é a moeda (ln 2)."""
    map_terms: list[float] = []
    series_terms: list[float] = []
    for prediction in predictions:
        series = prediction.series
        assert series.score1 is not None and series.score2 is not None
        p = min(max(prediction.map_win, 1e-6), 1 - 1e-6)
        map_terms += [-math.log(p)] * series.score1 + [-math.log(1 - p)] * series.score2
        q = min(max(prediction.series_win, 1e-6), 1 - 1e-6)
        series_terms.append(-math.log(q if series.score1 > series.score2 else 1 - q))
    return {
        "maps": len(map_terms),
        "series": len(series_terms),
        "map_log_loss": sum(map_terms) / len(map_terms),
        "series_log_loss": sum(series_terms) / len(series_terms),
        "coin_log_loss": math.log(2),
    }
