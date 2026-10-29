"""Simulador de liga com o desempate do regulamento de cada competição (ADR-0011).

Reaproveita o `SeasonSimulator` da Série A (sorteio dos placares e totais) e troca só a ordenação final.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np
import numpy.typing as npt
import pandas as pd

from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.config import RatingParams
from brasileirao.leagues.ranking import (
    HEAD_TO_HEAD_KEYS,
    LOT_KEY,
    HeadToHead,
    add_results,
    empty_head_to_head,
    resolve_order,
)
from brasileirao.prediction.goals_model import GoalsModel
from brasileirao.ratings.history import RatingState
from brasileirao.simulation.engine import SeasonSimulator

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]


def observed_head_to_head(
    observed: pd.DataFrame, club_index: Mapping[str, int], n_clubs: int, points_win: int, points_draw: int
) -> HeadToHead:
    return add_results(
        empty_head_to_head(n_clubs),
        np.array([club_index[club] for club in observed["home_id"]], dtype=np.int64),
        np.array([club_index[club] for club in observed["away_id"]], dtype=np.int64),
        observed["home_goals"].to_numpy(dtype=np.int64),
        observed["away_goals"].to_numpy(dtype=np.int64),
        points_win,
        points_draw,
    )


class LeagueSimulator(SeasonSimulator):
    def __init__(
        self,
        season_matches: pd.DataFrame,
        reference_date: date,
        rating_state: RatingState,
        goals_model: GoalsModel,
        rating_params: RatingParams,
        rules: SeasonRules,
        tiebreak_order: Sequence[str],
    ) -> None:
        super().__init__(season_matches, reference_date, rating_state, goals_model, rating_params, rules)
        self.tiebreak_order = tuple(tiebreak_order)
        self.observed_h2h = observed_head_to_head(
            self.observed, self.club_index, len(self.club_ids), rules.points_win, rules.points_draw
        )

    def _rank_all(
        self,
        totals: dict[str, IntArray],
        simulated_home: npt.NDArray[np.int16],
        simulated_away: npt.NDArray[np.int16],
        home_all: IntArray,
        away_all: IntArray,
        draw_lot: FloatArray,
    ) -> IntArray:
        table = {
            "points": totals["points"],
            "wins": totals["wins"],
            "goals_for": totals["goals_for"],
            "goal_difference": totals["goals_for"] - totals["goals_against"],
        }
        prefix: list[str] = []
        for key in self.tiebreak_order:
            if key in HEAD_TO_HEAD_KEYS or key == LOT_KEY:
                break
            prefix.append(key)
        sort_keys = tuple(-table[key] for key in reversed(prefix))
        final_order = np.lexsort((-draw_lot, *sort_keys), axis=1)
        rows = np.arange(final_order.shape[0])[:, None]
        primary = np.stack([table[key] for key in prefix], axis=-1)[rows, final_order]
        tied = np.all(primary[:, 1:] == primary[:, :-1], axis=-1).any(axis=1)
        if self.tiebreak_order[len(prefix)] == LOT_KEY:
            return final_order.astype(np.int64)
        for simulation in np.flatnonzero(tied):
            head_to_head = add_results(
                self.observed_h2h,
                home_all,
                away_all,
                simulated_home[simulation].astype(np.int64),
                simulated_away[simulation].astype(np.int64),
                self.rules.points_win,
                self.rules.points_draw,
            )
            simulation_table = {key: values[simulation] for key, values in table.items()}
            final_order[simulation] = resolve_order(
                self.tiebreak_order, simulation_table, head_to_head, draw_lot[simulation]
            )
        return final_order.astype(np.int64)

    def observed_order(self, season_complete: bool, lot: FloatArray | None = None) -> list[str]:
        """Classificação atual (sorteio fixo = ordem alfabética).

        Com a temporada em andamento, só os critérios de tabela: os de confronto direto valem para a
        classificação final (PL C.17; LaLiga Art. 10) e, no meio da temporada, se apoiariam em confrontos
        incompletos. Na simulação, que termina a temporada, valem todos.
        """
        order = (
            self.tiebreak_order
            if season_complete
            else tuple(key for key in self.tiebreak_order if key not in HEAD_TO_HEAD_KEYS)
        )
        table = self.observed_table
        values = {
            "points": table.points.astype(np.int64),
            "wins": table.wins.astype(np.int64),
            "goals_for": table.goals_for.astype(np.int64),
            "goal_difference": table.goal_difference.astype(np.int64),
        }
        n_clubs = len(self.club_ids)
        tie_lot = lot if lot is not None else np.linspace(1.0, 0.0, n_clubs)
        return [self.club_ids[index] for index in resolve_order(order, values, self.observed_h2h, tie_lot)]
