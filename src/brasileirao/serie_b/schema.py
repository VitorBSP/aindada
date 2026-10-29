"""Contrato do `forecast.json` do site da Série B (ADR-0010). Só a temporada corrente."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

SERIE_B_SCHEMA_VERSION = "1.0"


class Clinched(BaseModel):
    """Situações já decididas pela aritmética dos pontos (condição suficiente; nunca por simulação)."""

    promoted_direct: bool = False
    top6: bool = False
    out_of_top2: bool = False
    out_of_top6: bool = False
    relegated: bool = False
    safe: bool = False


class TeamForecast(BaseModel):
    club_id: str
    name: str
    short_name: str
    position: int = Field(ge=1)
    played: int = Field(ge=0)
    points: int = Field(ge=0)
    wins: int = Field(ge=0)
    draws: int = Field(ge=0)
    losses: int = Field(ge=0)
    goals_for: int = Field(ge=0)
    goals_against: int = Field(ge=0)
    remaining: int = Field(ge=0)
    expected_points: float
    points_interval_90: tuple[float, float]
    expected_position: float
    position_probabilities: list[float]
    title: float
    promotion_direct: float
    playoff: float
    promotion_playoff: float
    promotion: float
    playoff_win_if_qualified: float | None
    relegation: float
    clinched: Clinched
    elo: float


class PlayoffPairing(BaseModel):
    """Confronto de playoff mais provável por grupo e sua frequência."""

    group: str
    better_position: int
    worse_position: int
    better_club_id: str
    worse_club_id: str
    probability: float
    better_advances: float


class RemainingMatch(BaseModel):
    match_id: str
    home_id: str
    away_id: str
    p_home: float
    p_draw: float
    p_away: float
    expected_home_goals: float
    expected_away_goals: float


class SourceCredit(BaseModel):
    source_name: str
    version: str
    origin: str
    license_name: str | None
    attribution: str | None
    retrieved_at: str


class SerieBForecast(BaseModel):
    schema_version: str = SERIE_B_SCHEMA_VERSION
    competition: str
    season: int
    reference_date: str
    generated_at: str
    n_simulations: int
    seed: int
    observed_matches: int
    remaining_matches: int
    model_version: str
    data_version: str
    regulation: dict[str, str]
    rules: dict[str, Any]
    warnings: list[str]
    sources: list[SourceCredit]
    teams: list[TeamForecast]
    likely_playoffs: list[PlayoffPairing]
    remaining: list[RemainingMatch]
    backtest: dict[str, Any] | None = None
