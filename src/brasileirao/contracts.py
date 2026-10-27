"""Contratos de dados compartilhados entre camadas."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MatchStatus(StrEnum):
    FINISHED = "finished"
    SCHEDULED = "scheduled"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class LicenseStatus(StrEnum):
    VERIFIED_OPEN = "verified_open"
    RESEARCH_ONLY_UNVERIFIED = "research_only_unverified"
    REQUIRES_AGREEMENT = "requires_agreement"
    BLOCKED = "blocked"


class Club(BaseModel):
    model_config = ConfigDict(frozen=True)

    club_id: str = Field(pattern=r"^[a-z0-9-]+$")
    display_name: str
    short_name: str = Field(min_length=2, max_length=4)
    state: str = Field(min_length=2, max_length=2)
    aliases: tuple[str, ...]


class MatchRecord(BaseModel):
    """Partida normalizada (camada silver). Placar ausente nunca é preenchido."""

    model_config = ConfigDict(frozen=True)

    match_id: str
    season: int = Field(ge=2003, le=2100)
    round: int | None = Field(default=None, ge=1)
    match_date: date
    home_id: str
    away_id: str
    home_goals: int | None = Field(default=None, ge=0)
    away_goals: int | None = Field(default=None, ge=0)
    status: MatchStatus
    source: str
    source_match_id: str

    @model_validator(mode="after")
    def _check_consistency(self) -> MatchRecord:
        if self.home_id == self.away_id:
            raise ValueError("mandante e visitante iguais")
        has_score = self.home_goals is not None and self.away_goals is not None
        if self.status == MatchStatus.FINISHED and not has_score:
            raise ValueError("partida encerrada sem placar")
        if self.status != MatchStatus.FINISHED and (self.home_goals is not None or self.away_goals is not None):
            raise ValueError("partida não encerrada com placar")
        return self


class ClubCardTotals(BaseModel):
    model_config = ConfigDict(frozen=True)

    season: int
    club_id: str
    red_cards: int = Field(ge=0)
    yellow_cards: int = Field(ge=0)
    matches_covered: int = Field(ge=0)


class SourceManifest(BaseModel):
    source_name: str
    origin: str
    version: str
    retrieved_at: datetime
    files: dict[str, str]
    license_status: LicenseStatus
    license_notes: str
    allowed_uses: list[str]


class StandingRow(BaseModel):
    position: int = Field(ge=1)
    club_id: str
    played: int = Field(ge=0)
    points: int = Field(ge=0)
    wins: int = Field(ge=0)
    draws: int = Field(ge=0)
    losses: int = Field(ge=0)
    goals_for: int = Field(ge=0)
    goals_against: int = Field(ge=0)
    goal_difference: int
