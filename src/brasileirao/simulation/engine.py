"""Simulação Monte Carlo do restante da temporada.

Cada simulação é uma linha dos arrays de estado: todas partem do mesmo estado observado
e a atualização de ratings de uma simulação nunca afeta outra.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.competition_rules.standings import TableStats, accumulate_table, rank_clubs
from brasileirao.config import RatingParams, SimulationUncertainty
from brasileirao.contracts import MatchStatus
from brasileirao.prediction.goals_model import GoalsModel, score_matrix
from brasileirao.ratings.elo import elo_delta, expected_home_score, match_score
from brasileirao.ratings.history import RatingState, form_smoothing

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]

SAMPLING_CHUNK_ROWS = 100_000


@dataclass(frozen=True)
class SimulationResult:
    season: int
    reference_date: date
    club_ids: tuple[str, ...]
    n_simulations: int
    seed: int
    dynamic_ratings: bool
    observed_matches: pd.DataFrame
    remaining_matches: pd.DataFrame
    observed_table: TableStats
    final_order: IntArray
    positions: IntArray
    points: IntArray
    wins: IntArray
    goals_for: IntArray
    goals_against: IntArray
    simulated_home_goals: npt.NDArray[np.int16]
    simulated_away_goals: npt.NDArray[np.int16]
    uncertainty: SimulationUncertainty = field(default_factory=SimulationUncertainty)


def split_season_matches(season_matches: pd.DataFrame, reference_date: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    is_finished = season_matches["status"] == MatchStatus.FINISHED.value
    is_observed = is_finished & (season_matches["match_date"].dt.date <= reference_date)
    observed = season_matches[is_observed].sort_values(["match_date", "match_id"])
    remaining = season_matches[~is_observed].sort_values(["match_date", "match_id"])
    return observed.reset_index(drop=True), remaining.reset_index(drop=True)


def _sample_scores(
    home_rate: FloatArray,
    away_rate: FloatArray,
    rho: float,
    max_goals: int,
    draw_inflation: float,
    generator: np.random.Generator,
) -> tuple[IntArray, IntArray]:
    """Sorteia placares em blocos de `SAMPLING_CHUNK_ROWS` jogos simulados para limitar a memória.

    Os uniformes são consumidos na mesma ordem com ou sem blocos, logo a semente reproduz o resultado.
    """
    flat_home, flat_away = home_rate.reshape(-1), away_rate.reshape(-1)
    flat_index = np.empty(len(flat_home), dtype=np.int64)
    n_scores = (max_goals + 1) ** 2
    for start in range(0, len(flat_home), SAMPLING_CHUNK_ROWS):
        stop = min(start + SAMPLING_CHUNK_ROWS, len(flat_home))
        probabilities = score_matrix(flat_home[start:stop], flat_away[start:stop], rho, max_goals, draw_inflation)
        cumulative = np.cumsum(probabilities.reshape(stop - start, -1), axis=1)
        draws = generator.random(stop - start)[:, None]
        flat_index[start:stop] = np.minimum((cumulative < draws).sum(axis=1), n_scores - 1)
    home_goals = (flat_index // (max_goals + 1)).reshape(home_rate.shape)
    away_goals = (flat_index % (max_goals + 1)).reshape(home_rate.shape)
    return home_goals.astype(np.int64), away_goals.astype(np.int64)


class SeasonSimulator:
    def __init__(
        self,
        season_matches: pd.DataFrame,
        reference_date: date,
        rating_state: RatingState,
        goals_model: GoalsModel,
        rating_params: RatingParams,
        rules: SeasonRules,
        card_totals: Mapping[str, tuple[int, int]] | None = None,
    ) -> None:
        self.reference_date = reference_date
        self.rules = rules
        self.goals_model = goals_model
        self.rating_params = rating_params
        self.rating_state = rating_state
        self.season = int(season_matches["season"].iloc[0])
        self.club_ids = tuple(sorted(set(season_matches["home_id"]) | set(season_matches["away_id"])))
        if len(self.club_ids) != rules.n_clubs:
            raise ValueError(f"{len(self.club_ids)} clubes na temporada; regras exigem {rules.n_clubs}")
        missing_ratings = [club for club in self.club_ids if club not in rating_state.ratings]
        if missing_ratings:
            raise ValueError(f"clubes sem rating no estado inicial: {missing_ratings}")
        self.club_index = {club: index for index, club in enumerate(self.club_ids)}
        self.observed, self.remaining = split_season_matches(season_matches, reference_date)
        cards = card_totals or {}
        self.observed_table = accumulate_table(
            self.club_ids,
            [self.club_index[club] for club in self.observed["home_id"]],
            [self.club_index[club] for club in self.observed["away_id"]],
            self.observed["home_goals"].astype(int).tolist(),
            self.observed["away_goals"].astype(int).tolist(),
            rules,
            red_cards=[cards.get(club, (0, 0))[0] for club in self.club_ids],
            yellow_cards=[cards.get(club, (0, 0))[1] for club in self.club_ids],
        )

    def _initial_arrays(self, n_simulations: int) -> dict[str, FloatArray]:
        ratings = [self.rating_state.ratings[club] for club in self.club_ids]
        return {
            "elo": np.tile([rating.elo for rating in ratings], (n_simulations, 1)).astype(np.float64),
            "attack": np.tile([rating.attack for rating in ratings], (n_simulations, 1)).astype(np.float64),
            "defense": np.tile([rating.defense for rating in ratings], (n_simulations, 1)).astype(np.float64),
            "form": np.tile([rating.form for rating in ratings], (n_simulations, 1)).astype(np.float64),
        }

    def _batch_features(
        self, arrays: dict[str, FloatArray], home_index: IntArray, away_index: IntArray
    ) -> dict[str, FloatArray]:
        base, home_effect = self.rating_state.base, self.rating_state.home_effect
        return {
            "elo_diff": (arrays["elo"][:, home_index] - arrays["elo"][:, away_index]).reshape(-1),
            "ad_log_home": (
                base + home_effect + arrays["attack"][:, home_index] - arrays["defense"][:, away_index]
            ).reshape(-1),
            "ad_log_away": (base + arrays["attack"][:, away_index] - arrays["defense"][:, home_index]).reshape(-1),
            "form_diff": (arrays["form"][:, home_index] - arrays["form"][:, away_index]).reshape(-1),
        }

    def _update_ratings(
        self,
        arrays: dict[str, FloatArray],
        home_index: IntArray,
        away_index: IntArray,
        home_goals: IntArray,
        away_goals: IntArray,
    ) -> None:
        elo_params = self.rating_params.elo
        ad_params = self.rating_params.attack_defense
        smoothing = form_smoothing(self.rating_params.form.span_matches)
        base, home_effect = self.rating_state.base, self.rating_state.home_effect
        home_elo, away_elo = arrays["elo"][:, home_index], arrays["elo"][:, away_index]
        scored_home, scored_away = home_goals.astype(np.float64), away_goals.astype(np.float64)
        elo_step = elo_delta(home_elo, away_elo, scored_home, scored_away, elo_params)
        surprise = match_score(scored_home, scored_away) - expected_home_score(
            home_elo, away_elo, elo_params.home_advantage
        )
        home_attack, away_attack = arrays["attack"][:, home_index], arrays["attack"][:, away_index]
        home_defense, away_defense = arrays["defense"][:, home_index], arrays["defense"][:, away_index]
        home_error = scored_home - np.exp(base + home_effect + home_attack - away_defense)
        away_error = scored_away - np.exp(base + away_attack - home_defense)
        home_form, away_form = arrays["form"][:, home_index], arrays["form"][:, away_index]
        rate = ad_params.learning_rate
        for match_position, (home_club, away_club) in enumerate(zip(home_index, away_index, strict=True)):
            arrays["elo"][:, home_club] += elo_step[:, match_position]
            arrays["elo"][:, away_club] -= elo_step[:, match_position]
            arrays["attack"][:, home_club] += rate * home_error[:, match_position]
            arrays["defense"][:, home_club] -= rate * away_error[:, match_position]
            arrays["attack"][:, away_club] += rate * away_error[:, match_position]
            arrays["defense"][:, away_club] -= rate * home_error[:, match_position]
            arrays["form"][:, home_club] += smoothing * (surprise[:, match_position] - home_form[:, match_position])
            arrays["form"][:, away_club] += smoothing * (-surprise[:, match_position] - away_form[:, match_position])

    def run(
        self,
        n_simulations: int,
        seed: int,
        dynamic_ratings: bool = True,
        uncertainty: SimulationUncertainty | None = None,
    ) -> SimulationResult:
        """Sorteios de incerteza usam geradores próprios derivados da semente: o fluxo dos placares
        é o mesmo com ou sem incerteza (números aleatórios comuns entre configurações)."""
        generator = np.random.default_rng(seed)
        uncertainty = uncertainty or SimulationUncertainty()
        parameter_draws = (
            self.goals_model.sample_parameters(n_simulations, np.random.default_rng((seed, 1)))
            if uncertainty.coefficient_draws
            else None
        )
        latent_strength = (
            uncertainty.strength_sd
            * np.random.default_rng((seed, 2)).standard_normal((n_simulations, len(self.club_ids)))
            if uncertainty.strength_sd > 0
            else None
        )
        arrays = self._initial_arrays(n_simulations)
        n_remaining = len(self.remaining)
        simulated_home = np.zeros((n_simulations, n_remaining), dtype=np.int16)
        simulated_away = np.zeros((n_simulations, n_remaining), dtype=np.int16)
        home_all = np.array([self.club_index[club] for club in self.remaining["home_id"]], dtype=np.int64)
        away_all = np.array([self.club_index[club] for club in self.remaining["away_id"]], dtype=np.int64)
        batch_keys = self.remaining["match_date"].to_numpy()
        for batch_date in pd.unique(batch_keys):
            positions_in_batch = np.flatnonzero(batch_keys == batch_date)
            home_index, away_index = home_all[positions_in_batch], away_all[positions_in_batch]
            features = self._batch_features(arrays, home_index, away_index)
            shape = (n_simulations, len(positions_in_batch))
            if parameter_draws is None:
                home_rate, away_rate = self.goals_model.expected_goals(features)
            else:
                home_rate, away_rate = self.goals_model.expected_goals_by_draw(features, *parameter_draws)
            home_rate, away_rate = home_rate.reshape(shape), away_rate.reshape(shape)
            if latent_strength is not None:
                strength_gap = latent_strength[:, home_index] - latent_strength[:, away_index]
                home_rate, away_rate = home_rate * np.exp(strength_gap), away_rate * np.exp(-strength_gap)
            home_goals, away_goals = _sample_scores(
                home_rate,
                away_rate,
                self.goals_model.rho,
                self.goals_model.max_goals,
                self.goals_model.draw_inflation,
                generator,
            )
            simulated_home[:, positions_in_batch] = home_goals
            simulated_away[:, positions_in_batch] = away_goals
            if dynamic_ratings:
                self._update_ratings(arrays, home_index, away_index, home_goals, away_goals)
        totals = self._final_totals(simulated_home, simulated_away, home_all, away_all)
        draw_lot = generator.random((n_simulations, len(self.club_ids)))
        final_order = self._rank_all(totals, simulated_home, simulated_away, home_all, away_all, draw_lot)
        positions = np.empty_like(final_order)
        rows = np.arange(n_simulations)[:, None]
        positions[rows, final_order] = np.arange(len(self.club_ids))[None, :]
        return SimulationResult(
            season=self.season,
            reference_date=self.reference_date,
            club_ids=self.club_ids,
            n_simulations=n_simulations,
            seed=seed,
            dynamic_ratings=dynamic_ratings,
            observed_matches=self.observed,
            remaining_matches=self.remaining,
            observed_table=self.observed_table,
            final_order=final_order,
            positions=positions,
            points=totals["points"],
            wins=totals["wins"],
            goals_for=totals["goals_for"],
            goals_against=totals["goals_against"],
            simulated_home_goals=simulated_home,
            simulated_away_goals=simulated_away,
            uncertainty=uncertainty,
        )

    def _final_totals(
        self,
        simulated_home: npt.NDArray[np.int16],
        simulated_away: npt.NDArray[np.int16],
        home_all: IntArray,
        away_all: IntArray,
    ) -> dict[str, IntArray]:
        n_simulations = simulated_home.shape[0]
        table = self.observed_table
        totals = {
            name: np.tile(values, (n_simulations, 1)).astype(np.int64)
            for name, values in (
                ("points", table.points),
                ("wins", table.wins),
                ("goals_for", table.goals_for),
                ("goals_against", table.goals_against),
            )
        }
        points_win, points_draw = self.rules.points_win, self.rules.points_draw
        for match_position, (home_club, away_club) in enumerate(zip(home_all, away_all, strict=True)):
            home_goals = simulated_home[:, match_position].astype(np.int64)
            away_goals = simulated_away[:, match_position].astype(np.int64)
            home_win, draw = home_goals > away_goals, home_goals == away_goals
            away_win = home_goals < away_goals
            totals["points"][:, home_club] += home_win * points_win + draw * points_draw
            totals["points"][:, away_club] += away_win * points_win + draw * points_draw
            totals["wins"][:, home_club] += home_win
            totals["wins"][:, away_club] += away_win
            totals["goals_for"][:, home_club] += home_goals
            totals["goals_against"][:, home_club] += away_goals
            totals["goals_for"][:, away_club] += away_goals
            totals["goals_against"][:, away_club] += home_goals
        return totals

    def _rank_all(
        self,
        totals: dict[str, IntArray],
        simulated_home: npt.NDArray[np.int16],
        simulated_away: npt.NDArray[np.int16],
        home_all: IntArray,
        away_all: IntArray,
        draw_lot: FloatArray,
    ) -> IntArray:
        points, wins = totals["points"], totals["wins"]
        goal_difference = totals["goals_for"] - totals["goals_against"]
        goals_for = totals["goals_for"]
        final_order = np.lexsort((-draw_lot, -goals_for, -goal_difference, -wins, -points), axis=1)
        rows = np.arange(points.shape[0])[:, None]
        primary = np.stack([points, wins, goal_difference, goals_for], axis=-1)[rows, final_order]
        tied_neighbours = np.all(primary[:, 1:] == primary[:, :-1], axis=-1)
        observed_table = self.observed_table
        for simulation in np.flatnonzero(tied_neighbours.any(axis=1)):
            h2h_points = observed_table.head_to_head_points.copy()
            h2h_goal_difference = observed_table.head_to_head_goal_difference.copy()
            for match_position, (home_club, away_club) in enumerate(zip(home_all, away_all, strict=True)):
                home_goals = int(simulated_home[simulation, match_position])
                away_goals = int(simulated_away[simulation, match_position])
                h2h_goal_difference[home_club, away_club] += home_goals - away_goals
                h2h_goal_difference[away_club, home_club] += away_goals - home_goals
                if home_goals > away_goals:
                    h2h_points[home_club, away_club] += self.rules.points_win
                elif home_goals < away_goals:
                    h2h_points[away_club, home_club] += self.rules.points_win
                else:
                    h2h_points[home_club, away_club] += self.rules.points_draw
                    h2h_points[away_club, home_club] += self.rules.points_draw
            final_order[simulation] = rank_clubs(
                points[simulation],
                wins[simulation],
                goal_difference[simulation],
                goals_for[simulation],
                h2h_points,
                h2h_goal_difference,
                observed_table.red_cards,
                observed_table.yellow_cards,
                draw_lot[simulation],
                self.rules.head_to_head_max_clubs,
            )
        return final_order.astype(np.int64)
