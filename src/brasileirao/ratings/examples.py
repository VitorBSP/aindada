"""Exemplos do Elo calculados pelo próprio motor de ratings ("Como calculamos", D-040).

Para dois clubes de cada competição: a passagem da temporada anterior para a atual (regressão à média ou
regra de clube novo), a trajetória da temporada anterior e o último jogo até a data de referência, com a
conta completa. Os valores saem de subclasses instrumentadas de `RatingEngine` e `GlobalElo`, que só
registram o estado antes e depois de cada passo; a conta exibida é refeita com as funções de
`ratings.elo` e conferida contra o motor (divergência levanta `ExampleMismatchError`).

São números de clubes reais: o arquivo `elo-examples.json` vai para a pasta `data/` de cada site,
ignorada pelo git (decisão B1), nunca para `methods.json`.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd

from brasileirao.config import EloParams, RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.europe.ratings import GlobalElo, GlobalEloParams
from brasileirao.frame_values import as_int, as_timestamp, is_missing, optional_int
from brasileirao.leagues.ranking import add_results, empty_head_to_head, resolve_order
from brasileirao.logging_utils import get_logger
from brasileirao.ratings.elo import elo_delta, expected_home_score, goal_difference_multiplier, match_score
from brasileirao.ratings.history import RatingEngine, finished_before, season_clubs_from_fixtures

LOGGER = get_logger(__name__)

EXAMPLES_FILE_NAME = "elo-examples.json"
SCHEMA_VERSION = "2.0"
TOLERANCE = 1e-9
POINTS_WIN = 3
POINTS_DRAW = 1
WEIGHTED_SEASONS = 5
BRAZIL_TIEBREAK = ("points", "wins", "goal_difference", "goals_for", "h2h_points", "draw_lot")
APPROXIMATE_DATE_SOURCES = frozenset({"imputed", "unknown"})

EXAMPLE_CLUBS: dict[str, tuple[str, str]] = {
    "serie-a": ("internacional", "flamengo"),
    "serie-b": ("sport", "goias"),
    "premier-league": ("liverpool", "manchester-united"),
    "la-liga": ("barcelona", "sevilla"),
    "champions-league": ("eng-manchester-city", "fra-paris-saint-germain"),
}
"""Par de cada competição: o exemplo é o confronto direto mais recente entre os dois (D-040, decisão do 08)."""
HEAD_TO_HEAD_COMPETITION: dict[str, str] = {"champions-league": "CL"}
"""Na Champions o confronto precisa ser da própria Champions; o Elo global também anda nas ligas nacionais."""


COMPETITION_NAMES = {
    "serie-a": "Brasileirão Série A",
    "serie-b": "Série B",
    "premier-league": "Premier League",
    "la-liga": "LaLiga",
    "champions-league": "Champions League",
}
EUROPEAN_CALENDAR = frozenset({"premier-league", "la-liga", "champions-league"})


class ExampleMismatchError(RuntimeError):
    """A conta refeita com `ratings.elo` não bate com o estado do motor."""


@dataclass(frozen=True)
class NewcomerEntry:
    """Elo de entrada de um clube sem rating na competição.

    `rule`: `leavers_mean` (média de quem saiu + `offset`), `initial_rating` (sem ninguém saindo ou primeira
    temporada), `country_mean` (média do país − `offset`) ou `unknown_country` (`initial_rating` − `offset`).
    """

    rule: str
    base: float
    offset: float
    elo: float
    leavers: tuple[str, ...] = ()


@dataclass(frozen=True)
class SeasonStartTrace:
    """Estado em torno da virada de temporada.

    `ratings_before` tem todos os clubes conhecidos antes da regressão; `entry` é o Elo que entra na regressão
    (o fim da temporada anterior ou o de clube novo); `elo_after = recentered_to (ou reference_mean) +
    (entry − reference_mean) × (1 − regression)`.
    """

    season: int
    previous_clubs: frozenset[str]
    ratings_before: dict[str, float]
    entry: dict[str, float]
    reference_mean: dict[str, float]
    recentered_to: float | None
    regression: float
    elo_after: dict[str, float]
    newcomers: dict[str, NewcomerEntry] = field(default_factory=dict)


@dataclass(frozen=True)
class MatchTrace:
    match_id: str
    season: int
    match_date: date
    competition: str | None
    home_id: str
    away_id: str
    home_goals: int
    away_goals: int
    home_advantage: float
    home_elo_before: float
    away_elo_before: float
    home_elo_after: float
    away_elo_after: float


@dataclass(frozen=True)
class EloTrace:
    k_factor: float
    season_starts: dict[int, SeasonStartTrace]
    matches: list[MatchTrace]
    final_elo: dict[str, float]
    newcomers: dict[tuple[int, str], NewcomerEntry] = field(default_factory=dict)


def _check(expected: float, found: float, what: str) -> None:
    if abs(expected - found) > TOLERANCE:
        raise ExampleMismatchError(f"{what}: conta {expected!r}, motor {found!r}")


class TracedRatingEngine(RatingEngine):
    """`RatingEngine` que registra o estado antes e depois de cada virada de temporada e de cada lote."""

    def __init__(self, params: RatingParams) -> None:
        super().__init__(params)
        self.season_starts: dict[int, SeasonStartTrace] = {}
        self.batch_log: list[tuple[list[tuple[str, str, int, int]], dict[str, float], dict[str, float]]] = []

    def start_season(self, season: int, clubs: Iterable[str]) -> None:
        clubs_in_season = frozenset(clubs)
        previous_clubs = self.state.season_clubs
        before = {club: rating.elo for club, rating in self.state.ratings.items()}
        super().start_season(season, clubs_in_season)
        elo_params = self.params.elo
        leavers = tuple(sorted(club for club in previous_clubs - clubs_in_season if club in before))
        if leavers:
            leavers_mean = float(np.mean([before[club] for club in leavers]))
            prior = NewcomerEntry("leavers_mean", leavers_mean, elo_params.promoted_offset, 0.0, leavers)
        else:
            prior = NewcomerEntry("initial_rating", elo_params.initial_rating, 0.0, 0.0)
        prior = NewcomerEntry(prior.rule, prior.base, prior.offset, prior.base + prior.offset, prior.leavers)
        entry: dict[str, float] = {}
        newcomers: dict[str, NewcomerEntry] = {}
        for club in sorted(clubs_in_season):
            if club in previous_clubs and club in before:
                entry[club] = before[club]
            else:
                entry[club] = prior.elo
                newcomers[club] = prior
        mean_elo = float(np.mean(list(entry.values())))
        trace = SeasonStartTrace(
            season=season,
            previous_clubs=previous_clubs,
            ratings_before=before,
            entry=entry,
            reference_mean=dict.fromkeys(entry, mean_elo),
            recentered_to=elo_params.initial_rating,
            regression=elo_params.season_regression,
            elo_after={club: self.state.ratings[club].elo for club in clubs_in_season},
            newcomers=newcomers,
        )
        for club in entry:
            _check(regressed_elo(trace, club), trace.elo_after[club], f"início de {season} de {club}")
        self.season_starts[season] = trace

    def process_batch(self, batch: list[tuple[str, str, int, int]]) -> None:
        clubs = {club for home_id, away_id, _, _ in batch for club in (home_id, away_id)}
        before = {club: self.state.ratings[club].elo for club in clubs}
        super().process_batch(batch)
        after = {club: self.state.ratings[club].elo for club in clubs}
        self.batch_log.append((list(batch), before, after))


def regressed_elo(trace: SeasonStartTrace, club: str) -> float:
    """A conta da virada de temporada, como é mostrada no site."""
    mean = trace.reference_mean[club]
    anchor = mean if trace.recentered_to is None else trace.recentered_to
    return anchor + (trace.entry[club] - mean) * (1.0 - trace.regression)


def trace_league_ratings(
    matches_data: pd.DataFrame, reference_date: date, season: int, params: RatingParams
) -> EloTrace:
    """Mesmo caminho de `build_state_as_of`, com o motor instrumentado."""
    season_clubs = season_clubs_from_fixtures(matches_data)
    engine = TracedRatingEngine(params)
    features = engine.run(finished_before(matches_data, reference_date), season_clubs)
    if engine.state.season != season:
        engine.start_season(season, season_clubs[season])
    flattened = [(match, before, after) for batch, before, after in engine.batch_log for match in batch]
    if len(flattened) != len(features):
        raise ExampleMismatchError("lotes do motor e features pré-jogo com tamanhos diferentes")
    matches: list[MatchTrace] = []
    for row, ((home_id, away_id, home_goals, away_goals), before, after) in zip(
        features.itertuples(index=False), flattened, strict=True
    ):
        if (str(row.home_id), str(row.away_id)) != (home_id, away_id):
            raise ExampleMismatchError(f"ordem do motor diferente das features em {row.match_id}")
        matches.append(
            MatchTrace(
                match_id=str(row.match_id),
                season=as_int(row.season),
                match_date=as_timestamp(row.match_date).date(),
                competition=None,
                home_id=home_id,
                away_id=away_id,
                home_goals=home_goals,
                away_goals=away_goals,
                home_advantage=params.elo.home_advantage,
                home_elo_before=before[home_id],
                away_elo_before=before[away_id],
                home_elo_after=after[home_id],
                away_elo_after=after[away_id],
            )
        )
    return EloTrace(
        k_factor=params.elo.k_factor,
        season_starts=engine.season_starts,
        matches=matches,
        final_elo={club: rating.elo for club, rating in engine.state.ratings.items()},
    )


class TracedGlobalElo(GlobalElo):
    """`GlobalElo` (ADR-0012) que registra viradas de temporada, entradas de clubes novos e o pré-jogo."""

    def __init__(self, params: GlobalEloParams, countries: Mapping[str, str]) -> None:
        super().__init__(params, countries)
        self.season_starts: dict[int, SeasonStartTrace] = {}
        self.newcomers: dict[tuple[int, str], NewcomerEntry] = {}
        self.pre_match: list[tuple[str, str, float, float, float]] = []

    def _ensure(self, club: str, domestic: bool) -> float:
        if club in self.state.ratings:
            return self.state.ratings[club]
        country_mean = self.state.country_mean(self.countries[club], self.countries)
        rating = super()._ensure(club, domestic)
        params = self.params
        if domestic and self.first_season:
            entry = NewcomerEntry("initial_rating", params.initial_rating, 0.0, rating)
        elif country_mean is not None:
            entry = NewcomerEntry("country_mean", country_mean, params.newcomer_offset if domestic else 0.0, rating)
        else:
            entry = NewcomerEntry("unknown_country", params.initial_rating, params.unknown_offset, rating)
        _check(entry.base - entry.offset, rating, f"entrada de {club}")
        self.newcomers[(self.state.season or 0, club)] = entry
        return rating

    def _start_season(self, season: int) -> None:
        started = self.state.season is not None
        previous = frozenset(self.state.ratings)
        before = dict(self.state.ratings)
        super()._start_season(season)
        if not started:
            return
        values: dict[str, list[float]] = {}
        for club, rating in before.items():
            values.setdefault(self.countries[club], []).append(rating)
        means = {country: float(np.mean(ratings)) for country, ratings in values.items()}
        trace = SeasonStartTrace(
            season=season,
            previous_clubs=previous,
            ratings_before=before,
            entry=before,
            reference_mean={club: means[self.countries[club]] for club in before},
            recentered_to=None,
            regression=self.params.season_regression,
            elo_after=dict(self.state.ratings),
        )
        for club in before:
            _check(regressed_elo(trace, club), trace.elo_after[club], f"início de {season} de {club}")
        self.season_starts[season] = trace

    def effective_diff(self, home: str, away: str, neutral: bool, domestic: bool = False) -> float:
        diff = super().effective_diff(home, away, neutral, domestic)
        advantage = 0.0 if neutral else self.params.home_advantage
        self.pre_match.append((home, away, self.state.ratings[home], self.state.ratings[away], advantage))
        return diff


def _elo_after_match(
    index: int,
    club: str,
    matches: Sequence[MatchTrace],
    starts: Mapping[int, SeasonStartTrace],
    final: Mapping[str, float],
) -> float:
    """Elo depois do jogo `index`: o pré-jogo seguinte do clube na mesma temporada, o fim da temporada ou o atual."""
    season = matches[index].season
    for later in matches[index + 1 :]:
        if later.season != season:
            break
        if club == later.home_id:
            return later.home_elo_before
        if club == later.away_id:
            return later.away_elo_before
    next_starts = sorted(start for start in starts if start > season)
    return starts[next_starts[0]].ratings_before[club] if next_starts else final[club]


def trace_global_ratings(
    matches_data: pd.DataFrame,
    reference_date: date,
    season: int,
    params: GlobalEloParams,
    countries: Mapping[str, str],
) -> EloTrace:
    """Mesmo caminho do `build_forecast` da Champions, com o motor instrumentado."""
    engine = TracedGlobalElo(params, countries)
    features = engine.run(matches_data[matches_data["match_date"] <= pd.Timestamp(reference_date)])
    engine.start_season_if_needed(season)
    if len(engine.pre_match) != len(features):
        raise ExampleMismatchError("pré-jogo do motor e features com tamanhos diferentes")
    provisional: list[MatchTrace] = []
    for row, (home_id, away_id, home_elo, away_elo, advantage) in zip(
        features.itertuples(index=False), engine.pre_match, strict=True
    ):
        provisional.append(
            MatchTrace(
                match_id=str(row.match_id),
                season=as_int(row.season),
                match_date=as_timestamp(row.match_date).date(),
                competition=str(row.competition),
                home_id=home_id,
                away_id=away_id,
                home_goals=as_int(row.home_goals),
                away_goals=as_int(row.away_goals),
                home_advantage=advantage,
                home_elo_before=home_elo,
                away_elo_before=away_elo,
                home_elo_after=0.0,
                away_elo_after=0.0,
            )
        )
    final = dict(engine.state.ratings)
    matches = [
        replace(
            match,
            home_elo_after=_elo_after_match(index, match.home_id, provisional, engine.season_starts, final),
            away_elo_after=_elo_after_match(index, match.away_id, provisional, engine.season_starts, final),
        )
        for index, match in enumerate(provisional)
    ]
    return EloTrace(
        k_factor=params.k_factor,
        season_starts=engine.season_starts,
        matches=matches,
        final_elo=final,
        newcomers=engine.newcomers,
    )


@dataclass(frozen=True)
class CompetitionInfo:
    competition_id: str
    name: str
    season: int
    reference_date: date
    data_version: str
    model_version: str
    european_calendar: bool = False


class PublishedForecast(Protocol):
    """O que os exemplos usam do forecast publicado: a mesma data de referência e as mesmas versões."""

    @property
    def season(self) -> int: ...

    @property
    def reference_date(self) -> str: ...

    @property
    def data_version(self) -> str: ...

    @property
    def model_version(self) -> str: ...


def competition_info(
    competition_id: str, season: int, reference_date: str, data_version: str, model_version: str
) -> CompetitionInfo:
    return CompetitionInfo(
        competition_id=competition_id,
        name=COMPETITION_NAMES[competition_id],
        season=season,
        reference_date=date.fromisoformat(reference_date),
        data_version=data_version,
        model_version=model_version,
        european_calendar=competition_id in EUROPEAN_CALENDAR,
    )


def info_from_forecast(competition_id: str, forecast: PublishedForecast) -> CompetitionInfo:
    return competition_info(
        competition_id, forecast.season, forecast.reference_date, forecast.data_version, forecast.model_version
    )


def display_names(registry: ClubRegistry) -> dict[str, str]:
    return {club_id: club.display_name for club_id, club in registry.clubs.items()}


def season_label(season: int, european_calendar: bool) -> str:
    return f"{season}/{str(season + 1)[2:]}" if european_calendar else str(season)


def _club(club_id: str, names: Mapping[str, str]) -> dict[str, str]:
    return {"club_id": club_id, "name": names.get(club_id, club_id)}


def _newcomer_rule(entry: NewcomerEntry, names: Mapping[str, str]) -> dict[str, Any]:
    return {
        "rule": entry.rule,
        "base": entry.base,
        "offset": entry.offset,
        "elo": entry.elo,
        "leavers": [_club(club, names) for club in entry.leavers],
    }


def _entry(trace: EloTrace, club: str, season: int, names: Mapping[str, str]) -> dict[str, Any]:
    """Conta exata da entrada do clube na temporada: regressão à média ou regra de clube novo."""
    start = trace.season_starts.get(season)
    if start is not None and club in start.entry:
        newcomer = start.newcomers.get(club)
        return {
            "newcomer": newcomer is not None,
            "newcomer_rule": None if newcomer is None else _newcomer_rule(newcomer, names),
            "before": start.entry[club],
            "reference_mean": start.reference_mean[club],
            "reference_mean_kind": "league" if start.recentered_to is not None else "country",
            "recentered_to": start.recentered_to,
            "regression": start.regression,
            "after": start.elo_after[club],
        }
    newcomer = trace.newcomers.get((season, club))
    if newcomer is None:
        raise KeyError(f"{club} sem entrada em {season}")
    return {
        "newcomer": True,
        "newcomer_rule": _newcomer_rule(newcomer, names),
        "before": None,
        "reference_mean": None,
        "reference_mean_kind": "country",
        "recentered_to": None,
        "regression": None,
        "after": newcomer.elo,
    }


def _club_delta(trace: EloTrace, match: MatchTrace, club: str) -> float:
    """Variação do Elo do clube no jogo, com as funções de `ratings.elo` e o estado anterior ao jogo."""
    params = EloParams(k_factor=trace.k_factor, home_advantage=match.home_advantage)
    delta = float(
        elo_delta(
            match.home_elo_before, match.away_elo_before, float(match.home_goals), float(match.away_goals), params
        )
    )
    return delta if match.home_id == club else -delta


def _involves(match: MatchTrace, club: str) -> bool:
    return club in (match.home_id, match.away_id)


def _season_end(trace: EloTrace, club: str, season: int) -> float:
    """Elo no fim da temporada: o de antes da próxima virada, ou o estado atual se não houver virada depois."""
    later = sorted(start for start in trace.season_starts if start > season)
    return trace.season_starts[later[0]].ratings_before[club] if later else trace.final_elo[club]


def _net(entry_elo: float, end_elo: float, deltas: Sequence[float], what: str) -> float:
    """Saldo = fim − entrada (subtração exata entre valores próximos), conferido com a soma jogo a jogo."""
    net = end_elo - entry_elo
    _check(float(sum(deltas)), net, what)
    return net


def ledger_seasons(
    trace: EloTrace, club: str, before_season: int, names: Mapping[str, str], european_calendar: bool
) -> list[dict[str, Any]]:
    """Cada temporada do clube na competição antes de `before_season`: entrada, jogos, saldo e fim."""
    by_season: dict[int, list[MatchTrace]] = {}
    for match in trace.matches:
        if match.season < before_season and _involves(match, club):
            by_season.setdefault(match.season, []).append(match)
    rows: list[dict[str, Any]] = []
    for season, played in sorted(by_season.items()):
        entry = _entry(trace, club, season, names)
        end_elo = _season_end(trace, club, season)
        deltas = [_club_delta(trace, match, club) for match in played]
        row: dict[str, Any] = {
            "season": season,
            "label": season_label(season, european_calendar),
            "entry_elo": entry["after"],
            "matches": len(played),
            "net": _net(entry["after"], end_elo, deltas, f"saldo de {club} em {season}"),
            "end_elo": end_elo,
        }
        if entry["newcomer"]:
            row["newcomer_rule"] = entry["newcomer_rule"]
        competitions = Counter(match.competition for match in played if match.competition)
        if competitions:
            row["competitions"] = dict(sorted(competitions.items()))
        rows.append(row)
    return rows


def ledger_current(
    trace: EloTrace,
    club: str,
    match_index: int,
    names: Mapping[str, str],
    match_details: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """A temporada do confronto até a véspera: entrada, cada jogo com a variação e o Elo antes do confronto."""
    example = trace.matches[match_index]
    entry = _entry(trace, club, example.season, names)
    played = [
        match for match in trace.matches[:match_index] if match.season == example.season and _involves(match, club)
    ]
    matches_until: list[dict[str, Any]] = []
    for match in played:
        home = match.home_id == club
        opponent = match.away_id if home else match.home_id
        details = match_details.get(match.match_id, {})
        matches_until.append(
            {
                "match_id": match.match_id,
                "date": match.match_date.isoformat(),
                "date_is_approximate": bool(details.get("date_is_approximate", False)),
                "opponent_id": opponent,
                "opponent_name": names.get(opponent, opponent),
                "venue": "neutral" if match.home_advantage == 0.0 else "home" if home else "away",
                "competition": match.competition,
                "home_goals": match.home_goals,
                "away_goals": match.away_goals,
                "delta": _club_delta(trace, match, club),
                "elo_after": match.home_elo_after if home else match.away_elo_after,
            }
        )
    elo_before_match = example.home_elo_before if example.home_id == club else example.away_elo_before
    net_until = _net(
        entry["after"],
        elo_before_match,
        [item["delta"] for item in matches_until],
        f"saldo de {club} até {example.match_id}",
    )
    return {
        "season": example.season,
        "entry": entry,
        "matches_until": matches_until,
        "net_until": net_until,
        "elo_before_match": elo_before_match,
    }


def ledger_weights(
    seasons: Sequence[Mapping[str, Any]], current: Mapping[str, Any], regression: float, anchor: float
) -> dict[str, Any]:
    """Decomposição aproximada do Elo antes do confronto.

    Elo ≈ âncora + (entrada da última vez que o clube chegou como novo − âncora) × (1 − regressão)^anos
    + Σ saldo de cada temporada desde então × (1 − regressão)^anos, com `anos` = temporadas até a do confronto.
    A entrada como clube novo substitui o rating, então as temporadas anteriores a ela não contam. É aproximada
    porque ignora o deslocamento da média em cada virada (e, na Champions, a média do país); `exact` é o Elo do
    motor.
    """
    match_season = int(current["season"])
    keep = 1.0 - regression

    def weighted(season: int, net: float) -> dict[str, Any]:
        weight = keep ** (match_season - season)
        return {"season": season, "net": net, "weight": weight, "contribution": net * weight}

    entry = current["entry"]
    if entry["newcomer"]:
        start_season, start_elo, counted = match_season, float(entry["after"]), []
    else:
        resets = [item for item in seasons if "newcomer_rule" in item]
        last_reset = resets[-1] if resets else seasons[0]
        start_season, start_elo = int(last_reset["season"]), float(last_reset["entry_elo"])
        counted = [item for item in seasons if int(item["season"]) >= start_season]
    start_weight = keep ** (match_season - start_season)
    starting_point = {
        "season": start_season,
        "entry_elo": start_elo,
        "weight": start_weight,
        "contribution": (start_elo - anchor) * start_weight,
    }
    newest_first = [weighted(int(item["season"]), float(item["net"])) for item in reversed(counted)]
    rows = [weighted(match_season, float(current["net_until"])), *newest_first[:WEIGHTED_SEASONS]]
    older = newest_first[WEIGHTED_SEASONS:]
    older_row = {
        "first_season": min((item["season"] for item in older), default=None),
        "last_season": max((item["season"] for item in older), default=None),
        "n_seasons": len(older),
        "net": float(sum(item["net"] for item in older)),
        "contribution": float(sum(item["contribution"] for item in older)),
    }
    total = starting_point["contribution"] + sum(item["contribution"] for item in rows) + older_row["contribution"]
    return {
        "anchor": anchor,
        "regression": regression,
        "starting_point": starting_point,
        "seasons": rows,
        "older": older_row,
        "approx_total": anchor + total,
        "exact": float(current["elo_before_match"]),
    }


def _final_position(season_matches: Sequence[MatchTrace], club: str, tiebreak: Sequence[str]) -> tuple[int, int]:
    club_ids = sorted({match.home_id for match in season_matches} | {match.away_id for match in season_matches})
    index = {club_id: position for position, club_id in enumerate(club_ids)}
    home_index = np.array([index[match.home_id] for match in season_matches], dtype=np.int64)
    away_index = np.array([index[match.away_id] for match in season_matches], dtype=np.int64)
    home_goals = np.array([match.home_goals for match in season_matches], dtype=np.int64)
    away_goals = np.array([match.away_goals for match in season_matches], dtype=np.int64)
    head_to_head = add_results(
        empty_head_to_head(len(club_ids)), home_index, away_index, home_goals, away_goals, POINTS_WIN, POINTS_DRAW
    )
    goals_for = head_to_head.goals_for.sum(axis=1)
    goals_against = head_to_head.goals_against.sum(axis=1)
    wins = np.zeros(len(club_ids), dtype=np.int64)
    np.add.at(wins, home_index[home_goals > away_goals], 1)
    np.add.at(wins, away_index[away_goals > home_goals], 1)
    table = {
        "points": head_to_head.points.sum(axis=1),
        "wins": wins,
        "goals_for": goals_for,
        "goal_difference": goals_for - goals_against,
    }
    order = resolve_order(tiebreak, table, head_to_head, np.zeros(len(club_ids)))
    return order.index(index[club]) + 1, len(club_ids)


def previous_season_example(
    trace: EloTrace, club: str, season: int, tiebreak: Sequence[str] | None
) -> dict[str, Any] | None:
    """Trajetória do clube na temporada `season` (a anterior à atual), na mesma competição do motor."""
    start = trace.season_starts.get(season)
    following = trace.season_starts.get(season + 1)
    season_matches = [match for match in trace.matches if match.season == season]
    played = [match for match in season_matches if club in (match.home_id, match.away_id)]
    if following is None or not played or club not in following.ratings_before:
        return None
    wins = draws = losses = goals_for = goals_against = 0
    for match in played:
        scored, conceded = (
            (match.home_goals, match.away_goals) if match.home_id == club else (match.away_goals, match.home_goals)
        )
        goals_for += scored
        goals_against += conceded
        wins += scored > conceded
        draws += scored == conceded
        losses += scored < conceded
    position = n_clubs = None
    if tiebreak is not None:
        position, n_clubs = _final_position(season_matches, club, tiebreak)
    first = min(played, key=lambda match: (match.match_date, match.match_id))
    first_elo = first.home_elo_before if first.home_id == club else first.away_elo_before
    elo_start = start.elo_after.get(club, first_elo) if start is not None else first_elo
    return {
        "season": season,
        "elo_start": elo_start,
        "elo_end": following.ratings_before[club],
        "matches": len(played),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "points": None if tiebreak is None else POINTS_WIN * wins + POINTS_DRAW * draws,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "position": position,
        "n_clubs": n_clubs,
        "competitions": dict(sorted(Counter(match.competition for match in played if match.competition).items())),
    }


def find_head_to_head(trace: EloTrace, pair: tuple[str, str], season: int, competition: str | None = None) -> int:
    """Índice do confronto direto mais recente: na temporada atual ou, se não houver, na anterior."""
    for candidate_season in (season, season - 1):
        found = [
            index
            for index, match in enumerate(trace.matches)
            if match.season == candidate_season
            and {match.home_id, match.away_id} == set(pair)
            and (competition is None or match.competition == competition)
        ]
        if found:
            return found[-1]
    raise KeyError(f"sem confronto entre {pair[0]} e {pair[1]} em {season} nem em {season - 1}")


def match_example(
    trace: EloTrace,
    match_index: int,
    names: Mapping[str, str],
    match_details: Mapping[str, Mapping[str, Any]],
    european_calendar: bool,
) -> dict[str, Any]:
    """O confronto, com a conta refeita com `ratings.elo` e conferida contra o motor."""
    match = trace.matches[match_index]
    params = EloParams(k_factor=trace.k_factor, home_advantage=match.home_advantage)
    home_goals, away_goals = float(match.home_goals), float(match.away_goals)
    expected = float(expected_home_score(match.home_elo_before, match.away_elo_before, params.home_advantage))
    result = float(match_score(home_goals, away_goals))
    multiplier = float(goal_difference_multiplier(home_goals - away_goals))
    delta = float(elo_delta(match.home_elo_before, match.away_elo_before, home_goals, away_goals, params))
    _check(match.home_elo_before + delta, match.home_elo_after, f"Elo do mandante depois de {match.match_id}")
    _check(match.away_elo_before - delta, match.away_elo_after, f"Elo do visitante depois de {match.match_id}")
    details = match_details.get(match.match_id, {})
    return {
        "match_id": match.match_id,
        "season": match.season,
        "season_label": season_label(match.season, european_calendar),
        "date": match.match_date.isoformat(),
        "date_is_approximate": bool(details.get("date_is_approximate", False)),
        "round": details.get("round"),
        "competition": match.competition,
        "neutral": match.home_advantage == 0.0,
        "home": {**_club(match.home_id, names), "elo_before": match.home_elo_before, "elo_after": match.home_elo_after},
        "away": {**_club(match.away_id, names), "elo_before": match.away_elo_before, "elo_after": match.away_elo_after},
        "home_goals": match.home_goals,
        "away_goals": match.away_goals,
        "home_advantage": match.home_advantage,
        "expected_home": expected,
        "result_home": result,
        "goal_difference_multiplier": multiplier,
        "k_factor": trace.k_factor,
        "delta_home": delta,
    }


def match_details_from(matches_data: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Rodada e data aproximada (Série B: a fonte não traz datas) por `match_id`."""
    details: dict[str, dict[str, Any]] = {}
    columns = [column for column in ("match_id", "round", "date_source") if column in matches_data.columns]
    for record in matches_data[columns].to_dict("records"):
        date_source = record.get("date_source")
        details[str(record["match_id"])] = {
            "round": optional_int(record.get("round")),
            "date_is_approximate": not is_missing(date_source) and str(date_source) in APPROXIMATE_DATE_SOURCES,
        }
    return details


def competition_examples(
    info: CompetitionInfo,
    trace: EloTrace,
    pair: tuple[str, str],
    names: Mapping[str, str],
    match_details: Mapping[str, Mapping[str, Any]],
    tiebreak: Sequence[str] | None,
    elo_params: Mapping[str, float],
    regression: float,
    anchor: float,
) -> dict[str, Any]:
    """Um confronto direto entre os dois clubes do par e, para cada lado, de onde vem o Elo antes do jogo."""
    match_index = find_head_to_head(trace, pair, info.season, HEAD_TO_HEAD_COMPETITION.get(info.competition_id))
    match = trace.matches[match_index]
    examples: list[dict[str, Any]] = []
    for side, club in (("home", match.home_id), ("away", match.away_id)):
        previous = previous_season_example(trace, club, info.season - 1, tiebreak)
        seasons = ledger_seasons(trace, club, match.season, names, info.european_calendar)
        current = ledger_current(trace, club, match_index, names, match_details)
        examples.append(
            {
                "club_id": club,
                "name": names.get(club, club),
                "side": side,
                "previous_season": None
                if previous is None
                else {**previous, "label": season_label(previous["season"], info.european_calendar)},
                "ledger": {
                    "seasons": seasons,
                    "current": {**current, "label": season_label(match.season, info.european_calendar)},
                    "weights": ledger_weights(seasons, current, regression, anchor),
                },
            }
        )
    return {
        "id": info.competition_id,
        "name": info.name,
        "season": info.season,
        "season_label": season_label(info.season, info.european_calendar),
        "reference_date": info.reference_date.isoformat(),
        "data_version": info.data_version,
        "model_version": info.model_version,
        "elo_params": dict(elo_params),
        "match": match_example(trace, match_index, names, match_details, info.european_calendar),
        "examples": examples,
    }


def league_elo_params(params: EloParams) -> dict[str, float]:
    return {
        "k_factor": params.k_factor,
        "home_advantage": params.home_advantage,
        "season_regression": params.season_regression,
        "initial_rating": params.initial_rating,
        "promoted_offset": params.promoted_offset,
    }


def global_elo_params(params: GlobalEloParams) -> dict[str, float]:
    return {
        "k_factor": params.k_factor,
        "home_advantage": params.home_advantage,
        "season_regression": params.season_regression,
        "initial_rating": params.initial_rating,
        "newcomer_offset": params.newcomer_offset,
        "unknown_offset": params.unknown_offset,
    }


def league_examples(
    info: CompetitionInfo,
    matches_data: pd.DataFrame,
    params: RatingParams,
    names: Mapping[str, str],
    tiebreak: Sequence[str],
    pair: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Série A, Série B e ligas europeias: o `RatingEngine` de cada competição."""
    trace = trace_league_ratings(matches_data, info.reference_date, info.season, params)
    return competition_examples(
        info,
        trace,
        pair or EXAMPLE_CLUBS[info.competition_id],
        names,
        match_details_from(matches_data),
        tiebreak,
        league_elo_params(params.elo),
        params.elo.season_regression,
        params.elo.initial_rating,
    )


def champions_examples(
    info: CompetitionInfo,
    matches_data: pd.DataFrame,
    params: GlobalEloParams,
    countries: Mapping[str, str],
    names: Mapping[str, str],
    pair: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Champions League: o Elo único entre ligas (ADR-0012); sem posição, porque a temporada mistura torneios."""
    trace = trace_global_ratings(matches_data, info.reference_date, info.season, params, countries)
    competition = competition_examples(
        info,
        trace,
        pair or EXAMPLE_CLUBS[info.competition_id],
        names,
        match_details_from(matches_data),
        None,
        global_elo_params(params),
        params.season_regression,
        params.initial_rating,
    )
    for example in competition["examples"]:
        example["country"] = countries.get(example["club_id"])
    return competition


def examples_document(competition: dict[str, Any], generated_at: datetime | None = None) -> dict[str, Any]:
    moment = generated_at or datetime.now(tz=UTC)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": moment.isoformat(timespec="seconds"),
        "competitions": [competition],
    }


def write_examples(path: Path, build: Callable[[], dict[str, Any]]) -> bool:
    """Grava o arquivo da competição; falha nos exemplos não derruba a previsão (o site trata a ausência)."""
    path.unlink(missing_ok=True)
    try:
        document = examples_document(build())
    except (KeyError, ValueError, ExampleMismatchError) as error:
        LOGGER.warning("elo_examples_skipped", extra={"path": str(path), "error": str(error)})
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


def copy_examples(source_dir: Path, target_dir: Path) -> bool:
    """`export-web`: copia o arquivo, se a previsão o gerou, para a pasta `data/` do site."""
    source = source_dir / EXAMPLES_FILE_NAME
    target = target_dir / EXAMPLES_FILE_NAME
    target.unlink(missing_ok=True)
    if not source.exists():
        return False
    shutil.copyfile(source, target)
    return True


def check_examples_file(path: Path, competition_id: str, reference_date: str) -> list[str]:
    """Checagem dos gates: arquivo opcional; se existir, é da competição e da data de referência do forecast."""
    if not path.exists():
        return []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        competitions = document["competitions"]
    except (ValueError, KeyError, TypeError):
        return [f"{EXAMPLES_FILE_NAME} fora do esquema"]
    findings: list[str] = []
    if document.get("schema_version") != SCHEMA_VERSION:
        findings.append(f"{EXAMPLES_FILE_NAME} com schema_version {document.get('schema_version')!r}")
    if not isinstance(competitions, list) or [item.get("id") for item in competitions] != [competition_id]:
        findings.append(f"{EXAMPLES_FILE_NAME} não é só de {competition_id}")
    elif competitions[0].get("reference_date") != reference_date:
        findings.append(
            f"{EXAMPLES_FILE_NAME} com reference_date {competitions[0].get('reference_date')} diferente do forecast "
            f"({reference_date})"
        )
    return findings
