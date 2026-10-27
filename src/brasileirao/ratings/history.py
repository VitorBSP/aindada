"""Reconstrução cronológica dos ratings e das features pré-jogo.

Política de jogos simultâneos: todas as partidas da mesma data usam o estado anterior
àquela data e as atualizações são somadas depois. A ordem de processamento dentro da data
não altera o resultado.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date

import numpy as np
import pandas as pd

from brasileirao.config import RatingParams
from brasileirao.contracts import MatchStatus
from brasileirao.frame_values import as_int, as_timestamp
from brasileirao.ratings.attack_defense import attack_defense_update, expected_log_goals
from brasileirao.ratings.elo import elo_delta, expected_home_score, match_score

FEATURE_COLUMNS = [
    "elo_home",
    "elo_away",
    "elo_diff",
    "ad_log_home",
    "ad_log_away",
    "form_home",
    "form_away",
    "form_diff",
]


@dataclass(frozen=True)
class ClubRating:
    elo: float
    attack: float
    defense: float
    form: float


@dataclass
class RatingState:
    ratings: dict[str, ClubRating] = field(default_factory=dict)
    base: float = 0.0
    home_effect: float = 0.0
    season: int | None = None
    season_clubs: frozenset[str] = frozenset()
    last_match_date: date | None = None
    n_matches_processed: int = 0

    def copy(self) -> RatingState:
        return replace(self, ratings=dict(self.ratings))


def form_smoothing(span_matches: int) -> float:
    return 2.0 / (span_matches + 1.0)


class RatingEngine:
    def __init__(self, params: RatingParams) -> None:
        self.params = params
        self.state = RatingState(
            base=params.attack_defense.initial_log_goal_rate,
            home_effect=params.attack_defense.initial_home_effect,
        )

    def start_season(self, season: int, clubs: Iterable[str]) -> None:
        clubs_in_season = frozenset(clubs)
        previous_clubs = self.state.season_clubs
        elo_params = self.params.elo
        ad_params = self.params.attack_defense
        existing = self.state.ratings
        leavers = [existing[club] for club in previous_clubs - clubs_in_season if club in existing]
        if leavers:
            promoted_prior = ClubRating(
                elo=float(np.mean([rating.elo for rating in leavers])) + elo_params.promoted_offset,
                attack=float(np.mean([rating.attack for rating in leavers])),
                defense=float(np.mean([rating.defense for rating in leavers])),
                form=0.0,
            )
        else:
            promoted_prior = ClubRating(elo=elo_params.initial_rating, attack=0.0, defense=0.0, form=0.0)
        season_ratings: dict[str, ClubRating] = {}
        for club in clubs_in_season:
            if club in previous_clubs and club in existing:
                season_ratings[club] = existing[club]
            else:
                season_ratings[club] = promoted_prior
        mean_elo = float(np.mean([rating.elo for rating in season_ratings.values()]))
        mean_attack = float(np.mean([rating.attack for rating in season_ratings.values()]))
        mean_defense = float(np.mean([rating.defense for rating in season_ratings.values()]))
        keep_elo = 1.0 - elo_params.season_regression
        keep_ad = 1.0 - ad_params.season_regression
        for club, rating in season_ratings.items():
            existing[club] = ClubRating(
                elo=elo_params.initial_rating + (rating.elo - mean_elo) * keep_elo,
                attack=(rating.attack - mean_attack) * keep_ad,
                defense=(rating.defense - mean_defense) * keep_ad,
                form=rating.form * keep_ad,
            )
        self.state.base += mean_attack - mean_defense
        self.state.season = season
        self.state.season_clubs = clubs_in_season

    def pre_match_features(self, home_id: str, away_id: str) -> dict[str, float]:
        home, away = self.state.ratings[home_id], self.state.ratings[away_id]
        return {
            "elo_home": home.elo,
            "elo_away": away.elo,
            "elo_diff": home.elo - away.elo,
            "ad_log_home": expected_log_goals(self.state.base, self.state.home_effect, home.attack, away.defense, True),
            "ad_log_away": expected_log_goals(
                self.state.base, self.state.home_effect, away.attack, home.defense, False
            ),
            "form_home": home.form,
            "form_away": away.form,
            "form_diff": home.form - away.form,
        }

    def process_batch(self, batch: list[tuple[str, str, int, int]]) -> None:
        elo_params = self.params.elo
        ad_params = self.params.attack_defense
        smoothing = form_smoothing(self.params.form.span_matches)
        increments: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
        base_increment = 0.0
        home_effect_increment = 0.0
        for home_id, away_id, home_goals, away_goals in batch:
            home, away = self.state.ratings[home_id], self.state.ratings[away_id]
            delta = float(elo_delta(home.elo, away.elo, float(home_goals), float(away_goals), elo_params))
            expected = float(expected_home_score(home.elo, away.elo, elo_params.home_advantage))
            surprise = float(match_score(float(home_goals), float(away_goals))) - expected
            update = attack_defense_update(
                self.state.base,
                self.state.home_effect,
                home.attack,
                home.defense,
                away.attack,
                away.defense,
                float(home_goals),
                float(away_goals),
                ad_params,
            )
            home_increment, away_increment = increments[home_id], increments[away_id]
            home_increment[0] += delta
            away_increment[0] -= delta
            home_increment[1] += update.home_attack - home.attack
            home_increment[2] += update.home_defense - home.defense
            away_increment[1] += update.away_attack - away.attack
            away_increment[2] += update.away_defense - away.defense
            home_increment[3] += smoothing * (surprise - home.form)
            away_increment[3] += smoothing * (-surprise - away.form)
            base_increment += ad_params.global_learning_rate * (update.home_error + update.away_error) / 2
            home_effect_increment += ad_params.global_learning_rate * (update.home_error - update.away_error) / 2
        for club, (elo_step, attack_step, defense_step, form_step) in increments.items():
            rating = self.state.ratings[club]
            self.state.ratings[club] = ClubRating(
                elo=rating.elo + elo_step,
                attack=rating.attack + attack_step,
                defense=rating.defense + defense_step,
                form=rating.form + form_step,
            )
        self.state.base += base_increment
        self.state.home_effect += home_effect_increment
        self.state.n_matches_processed += len(batch)

    def run(self, finished_matches: pd.DataFrame, season_clubs: Mapping[int, Iterable[str]]) -> pd.DataFrame:
        """Processa partidas encerradas em ordem cronológica e devolve features pré-jogo."""
        ordered = finished_matches.sort_values(["match_date", "match_id"])
        feature_rows: list[dict[str, object]] = []
        for (season, match_date), date_matches in ordered.groupby(["season", "match_date"], sort=True):
            season_number = int(str(season))
            if self.state.season != season_number:
                self.start_season(season_number, season_clubs[season_number])
            batch: list[tuple[str, str, int, int]] = []
            for match in date_matches.itertuples(index=False):
                features = self.pre_match_features(str(match.home_id), str(match.away_id))
                feature_rows.append(
                    {
                        "match_id": match.match_id,
                        "season": season_number,
                        "match_date": match.match_date,
                        "home_id": match.home_id,
                        "away_id": match.away_id,
                        "home_goals": as_int(match.home_goals),
                        "away_goals": as_int(match.away_goals),
                        **features,
                    }
                )
                home_goals, away_goals = as_int(match.home_goals), as_int(match.away_goals)
                batch.append((str(match.home_id), str(match.away_id), home_goals, away_goals))
            self.process_batch(batch)
            self.state.last_match_date = as_timestamp(match_date).date()
        return pd.DataFrame(feature_rows)


def season_clubs_from_fixtures(matches_data: pd.DataFrame) -> dict[int, frozenset[str]]:
    return {
        int(str(season)): frozenset(season_matches["home_id"]) | frozenset(season_matches["away_id"])
        for season, season_matches in matches_data.groupby("season")
    }


def finished_before(matches_data: pd.DataFrame, reference_date: date) -> pd.DataFrame:
    is_finished = matches_data["status"] == MatchStatus.FINISHED.value
    is_observed: pd.Series[bool] = matches_data["match_date"].dt.date <= reference_date
    return matches_data.loc[is_finished & is_observed]


def build_state_as_of(
    matches_data: pd.DataFrame, reference_date: date, season: int, params: RatingParams
) -> tuple[RatingEngine, pd.DataFrame]:
    """Estado dos ratings usando apenas partidas encerradas até a data de referência."""
    season_clubs = season_clubs_from_fixtures(matches_data)
    engine = RatingEngine(params)
    features = engine.run(finished_before(matches_data, reference_date), season_clubs)
    if engine.state.season != season:
        engine.start_season(season, season_clubs[season])
    return engine, features
