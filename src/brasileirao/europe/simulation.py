"""Monte Carlo da Champions League 2026/27: fase de liga (Art. 18) e mata-mata (Art. 19 e Anexo B).

Ratings fixos na data de referência. Desempate da fase de liga: pontos, saldo, gols, gols fora, vitórias,
vitórias fora, pontos, saldo e gols dos adversários; pontos disciplinares e coeficiente (sem dados) viram
sorteio. Mata-mata: ida e volta pelo agregado, sem gol fora; prorrogação de 30 minutos (taxas / 3) e pênaltis
50/50; final em campo neutro. Onde o regulamento sorteia (pares de cada seção, lado da chave), a simulação
sorteia com probabilidades iguais.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from brasileirao.contracts import MatchStatus
from brasileirao.frame_values import as_int
from brasileirao.prediction.goals_model import GoalsModel, score_matrix
from brasileirao.serie_b.playoffs import PairRates

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]

# Seções do playoff (posições 0-based): cabeças 9/10 x 23/24, 11/12 x 21/22, 13/14 x 19/20, 15/16 x 17/18.
PLAYOFF_SECTIONS = (((8, 9), (22, 23)), ((10, 11), (20, 21)), ((12, 13), (18, 19)), ((14, 15), (16, 17)))
# Oitavas: A = 1/2 x vencedores IV; B = 3/4 x III; C = 5/6 x II; D = 7/8 x I.
ROUND_OF_16 = (((0, 1), 3), ((2, 3), 2), ((4, 5), 1), ((6, 7), 0))
STAGES = ("round_of_16", "quarter_finals", "semi_finals", "final", "winner")


def pair_rates(ratings: FloatArray, model: GoalsModel, home_advantage: float) -> tuple[PairRates, PairRates]:
    """Taxas de gols de i mandante contra j visitante, com mando e em campo neutro."""
    diff = ratings[:, None] - ratings[None, :]
    shape = diff.shape

    def rates(values: FloatArray) -> PairRates:
        home, away = model.expected_goals({"elo_diff": values.reshape(-1)})
        return PairRates(home=home.reshape(shape), away=away.reshape(shape))

    with_home = rates(diff + home_advantage)
    neutral = rates(diff)
    symmetric = PairRates(
        home=(neutral.home + neutral.away.T) / 2,
        away=(neutral.away + neutral.home.T) / 2,
    )
    return with_home, symmetric


class ScoreSampler:
    """Probabilidades acumuladas de placar de todos os pares (mandante, visitante), calculadas uma vez.

    O sorteio é vetorizado: cada simulação compara um uniforme com a linha acumulada do seu par.
    """

    CHUNK = 20_000

    def __init__(self, rates: PairRates, model: GoalsModel) -> None:
        n_clubs = rates.home.shape[0]
        matrices = score_matrix(
            rates.home.reshape(-1),
            rates.away.reshape(-1),
            model.rho,
            model.max_goals,
            model.draw_inflation,
            model.goal_dispersion,
        ).reshape(n_clubs * n_clubs, -1)
        cumulative = np.cumsum(matrices, axis=1)
        self.cumulative = cumulative / cumulative[:, -1:]
        self.n_clubs = n_clubs
        self.width = model.max_goals + 1

    def sample(self, home: IntArray, away: IntArray, generator: np.random.Generator) -> tuple[IntArray, IntArray]:
        draws = generator.random(len(home))
        flat = np.empty(len(home), dtype=np.int64)
        codes = home * self.n_clubs + away
        for start in range(0, len(home), self.CHUNK):
            stop = min(start + self.CHUNK, len(home))
            rows = self.cumulative[codes[start:stop]]
            flat[start:stop] = np.minimum((rows < draws[start:stop, None]).sum(axis=1), rows.shape[1] - 1)
        return flat // self.width, flat % self.width


@dataclass(frozen=True)
class LeaguePhase:
    club_ids: tuple[str, ...]
    observed: pd.DataFrame
    remaining: pd.DataFrame


def split_league_phase(champions: pd.DataFrame, reference_date: pd.Timestamp) -> LeaguePhase:
    league = champions[champions["stage"] == "LEAGUE_STAGE"]
    clubs = tuple(sorted(set(league["home_id"]) | set(league["away_id"])))
    observed_mask = (league["status"] == MatchStatus.FINISHED.value) & (league["match_date"] <= reference_date)
    return LeaguePhase(clubs, league[observed_mask], league[~observed_mask])


@dataclass(frozen=True)
class ChampionsSimulation:
    club_ids: tuple[str, ...]
    positions: IntArray
    points: IntArray
    stage_counts: dict[str, FloatArray]


def _points(goals_for: IntArray, goals_against: IntArray) -> IntArray:
    return np.where(goals_for > goals_against, 3, np.where(goals_for == goals_against, 1, 0))


class ChampionsSimulator:
    def __init__(self, phase: LeaguePhase, ratings: dict[str, float], model: GoalsModel, home_advantage: float) -> None:
        self.phase = phase
        self.index = {club: position for position, club in enumerate(phase.club_ids)}
        self.model = model
        rating_values = np.array([ratings[club] for club in phase.club_ids], dtype=np.float64)
        self.with_home, self.neutral = pair_rates(rating_values, model, home_advantage)
        self.home_sampler = ScoreSampler(self.with_home, model)
        self.neutral_sampler = ScoreSampler(self.neutral, model)
        n_clubs = len(phase.club_ids)
        league = pd.concat([phase.observed, phase.remaining])
        self.opponents = np.zeros((n_clubs, n_clubs), dtype=np.int64)
        for home, away in zip(league["home_id"], league["away_id"], strict=True):
            self.opponents[self.index[home], self.index[away]] += 1
            self.opponents[self.index[away], self.index[home]] += 1

    def _observed_totals(self) -> dict[str, IntArray]:
        n_clubs = len(self.phase.club_ids)
        totals = {
            name: np.zeros(n_clubs, dtype=np.int64) for name in ("points", "gf", "ga", "away_gf", "wins", "away_wins")
        }
        for match in self.phase.observed.itertuples(index=False):
            home, away = self.index[str(match.home_id)], self.index[str(match.away_id)]
            home_goals, away_goals = as_int(match.home_goals), as_int(match.away_goals)
            totals["points"][home] += int(_points(np.array(home_goals), np.array(away_goals)))
            totals["points"][away] += int(_points(np.array(away_goals), np.array(home_goals)))
            totals["gf"][home] += home_goals
            totals["ga"][home] += away_goals
            totals["gf"][away] += away_goals
            totals["ga"][away] += home_goals
            totals["away_gf"][away] += away_goals
            totals["wins"][home] += home_goals > away_goals
            totals["wins"][away] += away_goals > home_goals
            totals["away_wins"][away] += away_goals > home_goals
        return totals

    def _league_phase(self, n_simulations: int, generator: np.random.Generator) -> tuple[IntArray, IntArray]:
        observed = self._observed_totals()
        totals = {name: np.tile(values, (n_simulations, 1)) for name, values in observed.items()}
        for match in self.phase.remaining.itertuples(index=False):
            home, away = self.index[str(match.home_id)], self.index[str(match.away_id)]
            home_goals, away_goals = self.home_sampler.sample(
                np.full(n_simulations, home), np.full(n_simulations, away), generator
            )
            totals["points"][:, home] += _points(home_goals, away_goals)
            totals["points"][:, away] += _points(away_goals, home_goals)
            totals["gf"][:, home] += home_goals
            totals["ga"][:, home] += away_goals
            totals["gf"][:, away] += away_goals
            totals["ga"][:, away] += home_goals
            totals["away_gf"][:, away] += away_goals
            totals["wins"][:, home] += home_goals > away_goals
            totals["wins"][:, away] += away_goals > home_goals
            totals["away_wins"][:, away] += away_goals > home_goals
        goal_difference = totals["gf"] - totals["ga"]
        keys = [
            totals["points"],
            goal_difference,
            totals["gf"],
            totals["away_gf"],
            totals["wins"],
            totals["away_wins"],
            totals["points"] @ self.opponents,
            goal_difference @ self.opponents,
            totals["gf"] @ self.opponents,
        ]
        lot = generator.random(totals["points"].shape)
        final_order = np.lexsort((-lot, *[-key for key in reversed(keys)]), axis=1)
        return final_order.astype(np.int64), totals["points"]

    def _tie(
        self, seeded: IntArray, seeded_position: IntArray, other: IntArray, other_position: IntArray,
        generator: np.random.Generator,
    ) -> tuple[IntArray, IntArray]:  # fmt: skip
        """Ida na casa do pior colocado, volta na do melhor. Devolve vencedor e a posição herdada (a do melhor)."""
        better_first = seeded_position <= other_position
        host_second = np.where(better_first, seeded, other)
        host_first = np.where(better_first, other, seeded)
        first_home, first_away = self.home_sampler.sample(host_first, host_second, generator)
        second_home, second_away = self.home_sampler.sample(host_second, host_first, generator)
        second_total = first_away + second_home
        first_total = first_home + second_away
        tied = second_total == first_total
        extra_home = generator.poisson(self.with_home.home[host_second, host_first] / 3) * tied
        extra_away = generator.poisson(self.with_home.away[host_second, host_first] / 3) * tied
        second_total = second_total + extra_home
        first_total = first_total + extra_away
        penalties_second = generator.random(len(seeded)) < 0.5
        second_wins = (second_total > first_total) | ((second_total == first_total) & penalties_second)
        winner = np.where(second_wins, host_second, host_first)
        return winner, np.minimum(seeded_position, other_position)

    def _final(self, first: IntArray, second: IntArray, generator: np.random.Generator) -> IntArray:
        home_goals, away_goals = self.neutral_sampler.sample(first, second, generator)
        tied = home_goals == away_goals
        home_goals = home_goals + generator.poisson(self.neutral.home[first, second] / 3) * tied
        away_goals = away_goals + generator.poisson(self.neutral.away[first, second] / 3) * tied
        penalties = generator.random(len(first)) < 0.5
        return np.where((home_goals > away_goals) | ((home_goals == away_goals) & penalties), first, second)

    def run(self, n_simulations: int, seed: int) -> ChampionsSimulation:
        generator = np.random.default_rng(seed)
        final_order, points = self._league_phase(n_simulations, generator)
        rows = np.arange(n_simulations)
        n_clubs = len(self.phase.club_ids)
        positions = np.empty_like(final_order)
        positions[rows[:, None], final_order] = np.arange(n_clubs)[None, :]

        def club_at(position: int) -> IntArray:
            return final_order[:, position]

        def flip() -> npt.NDArray[np.bool_]:
            return generator.random(n_simulations) < 0.5

        playoff_winners: list[tuple[IntArray, IntArray]] = []
        for seeds, unseeded in PLAYOFF_SECTIONS:
            swap = flip()
            for slot in (0, 1):
                seeded_position = np.full(n_simulations, seeds[slot])
                other_position = np.where(swap, unseeded[1 - slot], unseeded[slot])
                playoff_winners.append(
                    self._tie(
                        club_at(seeds[slot]),
                        seeded_position,
                        final_order[rows, other_position],
                        other_position,
                        generator,
                    )
                )
        counts: dict[str, FloatArray] = {stage: np.zeros(n_clubs) for stage in STAGES}
        sections: list[list[tuple[IntArray, IntArray]]] = []
        for seeds, playoff_section in ROUND_OF_16:
            swap = flip()
            ties = []
            for slot in (0, 1):
                opponent, opponent_position = (
                    np.where(
                        swap,
                        playoff_winners[2 * playoff_section + 1 - slot][index],
                        playoff_winners[2 * playoff_section + slot][index],
                    )
                    for index in (0, 1)
                )
                seeded = club_at(seeds[slot])
                np.add.at(counts["round_of_16"], seeded, 1)
                np.add.at(counts["round_of_16"], opponent, 1)
                ties.append(
                    self._tie(seeded, np.full(n_simulations, seeds[slot]), opponent, opponent_position, generator)
                )
            half = flip()
            sections.append([
                (np.where(half, ties[1][0], ties[0][0]), np.where(half, ties[1][1], ties[0][1])),
                (np.where(half, ties[0][0], ties[1][0]), np.where(half, ties[0][1], ties[1][1])),
            ])  # fmt: skip
        semi_finalists = []
        for side in (0, 1):
            section_a, section_b, section_c, section_d = (section[side] for section in sections)
            quarter_one = self._tie(*section_a, *section_d, generator)
            quarter_two = self._tie(*section_b, *section_c, generator)
            for club, _ in (section_a, section_b, section_c, section_d):
                np.add.at(counts["quarter_finals"], club, 1)
            for club, _ in (quarter_one, quarter_two):
                np.add.at(counts["semi_finals"], club, 1)
            semi_finalists.append(self._tie(*quarter_one, *quarter_two, generator))
        for club, _ in semi_finalists:
            np.add.at(counts["final"], club, 1)
        champion = self._final(semi_finalists[0][0], semi_finalists[1][0], generator)
        np.add.at(counts["winner"], champion, 1)
        return ChampionsSimulation(
            club_ids=self.phase.club_ids,
            positions=positions,
            points=points,
            stage_counts={stage: values / n_simulations for stage, values in counts.items()},
        )
