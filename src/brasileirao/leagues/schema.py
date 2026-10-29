"""Contrato do `forecast.json` das ligas europeias (ADR-0011). Só a temporada corrente."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

LEAGUE_SCHEMA_VERSION = "1.0"

ClinchState = Literal["in", "out"]


class ZoneInfo(BaseModel):
    zone_id: str
    label: str
    first: int = Field(ge=1)
    last: int = Field(ge=1)
    kind: str
    note: str = ""


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
    zones: dict[str, float]
    clinched: dict[str, ClinchState | None]
    elo: float


class MatchForecast(BaseModel):
    match_id: str
    round: int | None
    match_date: str
    kickoff_utc: str | None
    status: str
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


class LeagueForecast(BaseModel):
    schema_version: str = LEAGUE_SCHEMA_VERSION
    competition: str
    competition_name: str
    season: int
    season_label: str
    reference_date: str
    generated_at: str
    n_simulations: int
    seed: int
    observed_matches: int
    remaining_matches: int
    model_version: str
    data_version: str
    regulation: dict[str, str]
    tiebreak_order: list[str]
    zones: list[ZoneInfo]
    warnings: list[str]
    sources: list[SourceCredit]
    teams: list[TeamForecast]
    remaining: list[MatchForecast]
    backtest: dict[str, Any] | None = None
