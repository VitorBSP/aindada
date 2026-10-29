"""Dificuldade da tabela restante e pontos esperados por mando.

Pontos esperados de um jogo = vitória · P(vitória) + empate · P(empate), com as probabilidades do
modelo de gols na data de referência (ratings congelados; nada posterior à data entra).

O índice de dificuldade (0–100) separa o calendário da força do próprio clube: mede quantos pontos
um clube de força média (média de Elo, ataque, defesa e forma da liga) faria contra os mesmos
adversários, com os mesmos mandos. Escala linear em pontos por jogo do clube médio:

    dificuldade = 50 + 50 · (referência − pontos do clube médio) / meia_escala

- referência: pontos por jogo do clube médio numa tabela média da liga (todos os adversários,
  uma vez em casa e uma fora). 50 = tabela média.
- meia_escala: maior distância entre a referência e um jogo possível (fora contra o adversário mais
  difícil ou em casa contra o mais fácil). Garante 0 ≤ índice ≤ 100.

Por ser linear, a dificuldade de um conjunto de jogos é a média das dificuldades dos jogos.
`opponent_strength` usa a mesma escala sem o efeito do mando (média de enfrentar o adversário em casa
e fora): 50 = adversário médio da liga.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
import pandas as pd

from brasileirao.frame_values import as_timestamp, optional_int
from brasileirao.prediction.goals_model import GoalsModel
from brasileirao.ratings.history import ClubRating, RatingState, average_rating, match_features

FloatArray = npt.NDArray[np.float64]

HOME = "home"
AWAY = "away"


@dataclass(frozen=True)
class ScheduleScale:
    """Âncoras do índice na data de referência, em pontos por jogo do clube médio."""

    reference_points: float
    reference_points_home: float
    reference_points_away: float
    half_range_points: float

    def difficulty(self, average_team_points: float) -> float:
        if self.half_range_points <= 0:
            return 50.0
        value = 50.0 + 50.0 * (self.reference_points - average_team_points) / self.half_range_points
        return float(min(max(value, 0.0), 100.0))


@dataclass(frozen=True)
class ScheduleMatch:
    match_id: str
    round: int | None
    match_date: str
    opponent_id: str
    venue: str
    p_win: float
    p_draw: float
    p_loss: float
    expected_points: float
    average_team_points: float
    difficulty: float
    opponent_strength: float


@dataclass
class ClubSchedule:
    club_id: str
    remaining_matches: int
    home_matches: int
    away_matches: int
    expected_points: float
    expected_points_home: float
    expected_points_away: float
    average_team_points: float
    difficulty: float | None
    opponent_strength: float | None
    difficulty_home: float | None
    difficulty_away: float | None
    difficulty_rank: int | None = None
    difficulty_home_rank: int | None = None
    difficulty_away_rank: int | None = None
    matches: list[ScheduleMatch] = field(default_factory=list)


def _points(probabilities: FloatArray, points_win: int, points_draw: int) -> tuple[FloatArray, FloatArray]:
    """Pontos esperados do mandante e do visitante a partir de (P casa, P empate, P fora)."""
    home_points = points_win * probabilities[:, 0] + points_draw * probabilities[:, 1]
    away_points = points_win * probabilities[:, 2] + points_draw * probabilities[:, 1]
    return home_points, away_points


def _outcomes(state: RatingState, model: GoalsModel, pairs: Sequence[tuple[ClubRating, ClubRating]]) -> FloatArray:
    if not pairs:
        return np.zeros((0, 3))
    features = pd.DataFrame([match_features(state, home, away) for home, away in pairs])
    outcome: FloatArray = model.outcome_probabilities(features)
    return outcome


def average_team_points_by_opponent(
    state: RatingState,
    model: GoalsModel,
    club_ids: Sequence[str],
    points_win: int = 3,
    points_draw: int = 1,
) -> tuple[dict[str, float], dict[str, float]]:
    """Pontos esperados do clube médio contra cada clube: (em casa, fora)."""
    average = average_rating(state.ratings[club_id] for club_id in club_ids)
    opponents = [state.ratings[club_id] for club_id in club_ids]
    at_home = _outcomes(state, model, [(average, opponent) for opponent in opponents])
    away = _outcomes(state, model, [(opponent, average) for opponent in opponents])
    home_points, _ = _points(at_home, points_win, points_draw)
    _, away_points = _points(away, points_win, points_draw)
    return (
        {club_id: float(value) for club_id, value in zip(club_ids, home_points, strict=True)},
        {club_id: float(value) for club_id, value in zip(club_ids, away_points, strict=True)},
    )


def schedule_scale(home_points: dict[str, float], away_points: dict[str, float]) -> ScheduleScale:
    reference_home = float(np.mean(list(home_points.values())))
    reference_away = float(np.mean(list(away_points.values())))
    reference = (reference_home + reference_away) / 2
    half_range = max(reference - min(away_points.values()), max(home_points.values()) - reference)
    return ScheduleScale(reference, reference_home, reference_away, float(half_range))


def _mean_or_none(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def _assign_ranks(schedules: list[ClubSchedule], attribute: str, rank_attribute: str) -> None:
    """1 = tabela mais difícil; empates desfeitos pelo `club_id`."""
    ranked = sorted(
        (schedule for schedule in schedules if getattr(schedule, attribute) is not None),
        key=lambda schedule: (-round(float(getattr(schedule, attribute)), 12), schedule.club_id),
    )
    for position, schedule in enumerate(ranked, start=1):
        setattr(schedule, rank_attribute, position)


def build_schedules(
    remaining: pd.DataFrame,
    state: RatingState,
    model: GoalsModel,
    club_ids: Sequence[str],
    points_win: int = 3,
    points_draw: int = 1,
) -> tuple[list[ClubSchedule], ScheduleScale]:
    """Pontos esperados e dificuldade dos jogos restantes de cada clube, na ordem de `club_ids`.

    `remaining` inclui todo jogo sem placar observado (agendado, adiado ou sem data).
    """
    home_points, away_points = average_team_points_by_opponent(state, model, club_ids, points_win, points_draw)
    scale = schedule_scale(home_points, away_points)
    opponent_strength = {
        club_id: scale.difficulty((home_points[club_id] + away_points[club_id]) / 2) for club_id in club_ids
    }
    rows = list(remaining.itertuples(index=False))
    outcome = _outcomes(
        state, model, [(state.ratings[str(row.home_id)], state.ratings[str(row.away_id)]) for row in rows]
    )
    club_home_points, club_away_points = _points(outcome, points_win, points_draw)
    by_club: dict[str, list[ScheduleMatch]] = {club_id: [] for club_id in club_ids}
    for position, row in enumerate(rows):
        home_id, away_id = str(row.home_id), str(row.away_id)
        match_id = str(row.match_id)
        round_number = optional_int(row.round)
        match_date = as_timestamp(row.match_date).date().isoformat()
        p_home, p_draw, p_away = (float(value) for value in outcome[position])
        for club_id, opponent_id, venue, p_win, p_loss, expected, average_points in (
            (home_id, away_id, HOME, p_home, p_away, club_home_points[position], home_points[away_id]),
            (away_id, home_id, AWAY, p_away, p_home, club_away_points[position], away_points[home_id]),
        ):
            by_club[club_id].append(
                ScheduleMatch(
                    match_id=match_id,
                    round=round_number,
                    match_date=match_date,
                    opponent_id=opponent_id,
                    venue=venue,
                    p_win=p_win,
                    p_draw=p_draw,
                    p_loss=p_loss,
                    expected_points=float(expected),
                    average_team_points=average_points,
                    difficulty=scale.difficulty(average_points),
                    opponent_strength=opponent_strength[opponent_id],
                )
            )
    schedules: list[ClubSchedule] = []
    for club_id in club_ids:
        matches = by_club[club_id]
        home_matches = [match for match in matches if match.venue == HOME]
        away_matches = [match for match in matches if match.venue == AWAY]
        schedules.append(
            ClubSchedule(
                club_id=club_id,
                remaining_matches=len(matches),
                home_matches=len(home_matches),
                away_matches=len(away_matches),
                expected_points=float(sum(match.expected_points for match in matches)),
                expected_points_home=float(sum(match.expected_points for match in home_matches)),
                expected_points_away=float(sum(match.expected_points for match in away_matches)),
                average_team_points=float(sum(match.average_team_points for match in matches)),
                difficulty=_mean_or_none([match.difficulty for match in matches]),
                opponent_strength=_mean_or_none([match.opponent_strength for match in matches]),
                difficulty_home=_mean_or_none([match.difficulty for match in home_matches]),
                difficulty_away=_mean_or_none([match.difficulty for match in away_matches]),
                matches=matches,
            )
        )
    _assign_ranks(schedules, "difficulty", "difficulty_rank")
    _assign_ranks(schedules, "difficulty_home", "difficulty_home_rank")
    _assign_ranks(schedules, "difficulty_away", "difficulty_away_rank")
    return schedules, scale
