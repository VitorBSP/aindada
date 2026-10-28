"""Rodada mostrada na aba "Rodada atual" / "Última rodada" (ADR-0009, Decisão 3).

Só lê o snapshot publicado e a revisão por rodada da mesma execução; não calcula probabilidade. O horário
do export (`now`) decide o que já começou e o que está sem placar há mais de `STALE_RESULT_HOURS` horas.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from brasileirao.config import CURRENT_ROUND_SCHEMA_VERSION, ROUND_WINDOW_DAYS, STALE_RESULT_HOURS
from brasileirao.contracts import MatchStatus
from brasileirao.storage.schema import (
    CurrentRound,
    CurrentRoundInfo,
    MatchPrediction,
    PredictionSnapshot,
    RoundBaseline,
    RoundReview,
)

BRASILIA = ZoneInfo("America/Sao_Paulo")
RoundState = Literal["in_progress", "finished"]
BASELINE_METRICS = ("title", "top4", "relegation")
RESOLVED_STATUSES = frozenset({MatchStatus.FINISHED.value, MatchStatus.POSTPONED.value, MatchStatus.CANCELLED.value})


class BaselineMismatchError(ValueError):
    """A visão de partida não tem os mesmos clubes do snapshot publicado."""


@dataclass(frozen=True)
class RoundWindow:
    round_number: int
    in_window: list[MatchPrediction]
    rescheduled: list[MatchPrediction]

    @property
    def starts_on(self) -> date:
        return min(match_day(match) for match in self.in_window)

    @property
    def ends_on(self) -> date:
        return max(match_day(match) for match in self.in_window)


def match_day(match: MatchPrediction) -> date:
    return date.fromisoformat(match.match_date)


def kickoff_moment(match: MatchPrediction) -> datetime:
    """Início do jogo; sem horário confirmado, o fim do dia em Brasília (a hipótese mais tardia)."""
    if match.kickoff_utc:
        moment = datetime.fromisoformat(match.kickoff_utc)
        return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return datetime.combine(match_day(match) + timedelta(days=1), time(), tzinfo=BRASILIA)


def is_resolved(match: MatchPrediction, now: datetime) -> bool:
    if match.status in RESOLVED_STATUSES:
        return True
    return now - kickoff_moment(match) > timedelta(hours=STALE_RESULT_HOURS)


def round_anchor(days: Iterable[date]) -> date:
    """Mediana inferior das datas dos jogos da rodada."""
    ordered = sorted(days)
    return ordered[(len(ordered) - 1) // 2]


def round_windows(matches: list[MatchPrediction]) -> dict[int, RoundWindow]:
    by_round: dict[int, list[MatchPrediction]] = {}
    for match in matches:
        if match.round is not None:
            by_round.setdefault(match.round, []).append(match)
    windows: dict[int, RoundWindow] = {}
    for round_number, round_matches in by_round.items():
        anchor = round_anchor(match_day(match) for match in round_matches)
        in_window = [match for match in round_matches if abs((match_day(match) - anchor).days) <= ROUND_WINDOW_DAYS]
        in_window_ids = {match.match_id for match in in_window}
        rescheduled = [match for match in round_matches if match.match_id not in in_window_ids]
        windows[round_number] = RoundWindow(round_number, in_window, rescheduled)
    return windows


def _display_order(match: MatchPrediction) -> tuple[date, int, str, str]:
    """Por dia; no dia, por `kickoff_utc`, com os jogos sem horário no fim."""
    kickoff = match.kickoff_utc
    kickoff_key = kickoff_moment(match).astimezone(UTC).isoformat() if kickoff else ""
    return match_day(match), 0 if kickoff else 1, kickoff_key, match.match_id


def select_round(windows: dict[int, RoundWindow], now: datetime) -> tuple[RoundWindow, RoundState] | None:
    """Menor rodada não concluída já iniciada (em Brasília); senão a maior concluída; senão nenhuma."""
    today = now.astimezone(BRASILIA).date()
    started = [window for number, window in sorted(windows.items()) if window.starts_on <= today]
    for window in started:
        if not all(is_resolved(match, now) for match in window.in_window):
            return window, "in_progress"
    if started:
        return started[-1], "finished"
    return None


def delayed_matches(window: RoundWindow, windows: dict[int, RoundWindow]) -> list[MatchPrediction]:
    """Jogos de outras rodadas remarcados para fora da janela delas e marcados no intervalo desta rodada."""
    return [
        match
        for other in windows.values()
        if other.round_number != window.round_number
        for match in other.rescheduled
        if window.starts_on <= match_day(match) <= window.ends_on
    ]


def round_baseline(review: RoundReview | None, snapshot: PredictionSnapshot, starts_on: date) -> RoundBaseline | None:
    """Visão do `rounds.json` com a maior `reference_date` anterior a `starts_on`, da mesma base de dados.

    Só as métricas do contrato (`BASELINE_METRICS`); a visão tem também pontos e posição.
    """
    if review is None or review.data_version != snapshot.data.version:
        return None
    earlier = [view for view in review.rounds if view.reference_date < starts_on]
    if not earlier:
        return None
    view = max(earlier, key=lambda item: item.reference_date)
    clubs = {team.club_id for team in snapshot.teams}
    if set(view.teams) != clubs:
        raise BaselineMismatchError(f"visão de {view.reference_date} sem os mesmos clubes do snapshot")
    return RoundBaseline(
        reference_date=view.reference_date.isoformat(),
        model_version=review.model_version,
        n_simulations=review.n_simulations,
        reconstructed=True,
        teams={club: {metric: values[metric] for metric in BASELINE_METRICS} for club, values in view.teams.items()},
    )


def build_current_round(snapshot: PredictionSnapshot, review: RoundReview | None, now: datetime) -> CurrentRound:
    windows = round_windows(snapshot.matches)
    selected = select_round(windows, now)
    round_info = None
    if selected is not None:
        window, state = selected
        listed = sorted([*window.in_window, *delayed_matches(window, windows)], key=_display_order)
        round_info = CurrentRoundInfo(
            round_number=window.round_number,
            state=state,
            starts_on=window.starts_on.isoformat(),
            ends_on=window.ends_on.isoformat(),
            match_ids=[match.match_id for match in listed],
            rescheduled_match_ids=[match.match_id for match in sorted(window.rescheduled, key=_display_order)],
            baseline=round_baseline(review, snapshot, window.starts_on),
        )
    return CurrentRound(
        schema_version=CURRENT_ROUND_SCHEMA_VERSION,
        season=snapshot.season,
        updated_at=snapshot.generated_at,
        model_version=snapshot.model.model_version,
        data_version=snapshot.data.version,
        round=round_info,
    )
