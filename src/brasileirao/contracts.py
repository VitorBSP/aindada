"""Contratos de dados compartilhados entre camadas."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MatchStatus(StrEnum):
    FINISHED = "finished"
    SCHEDULED = "scheduled"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class LicenseStatus(StrEnum):
    """Status de licença de uma fonte, do mais permissivo ao mais restritivo (ADR-0008, Decisão 2)."""

    VERIFIED_OPEN = "verified_open"
    LICENSED_WITH_ATTRIBUTION = "licensed_with_attribution"
    RESEARCH_ONLY_UNVERIFIED = "research_only_unverified"
    REQUIRES_AGREEMENT = "requires_agreement"
    BLOCKED = "blocked"


PUBLISHABLE_LICENSE_STATUSES = frozenset({LicenseStatus.VERIFIED_OPEN, LicenseStatus.LICENSED_WITH_ATTRIBUTION})


def most_restrictive_license(statuses: Iterable[LicenseStatus]) -> LicenseStatus:
    """Status mais restritivo de um conjunto de fontes, pela ordem de declaração do enum."""
    ordered = list(LicenseStatus)
    collected = list(statuses)
    if not collected:
        raise ValueError("nenhum status de licença informado")
    return max(collected, key=ordered.index)


class AllowedUse(StrEnum):
    """Vocabulário fechado de usos permitidos (ADR-0008, Decisão 2).

    `public_display_derived`: o site público exibe resultados derivados e os fatos de partida da
    temporada exibida, com atribuição; não inclui arquivos de dados em lote. `redistribution`: a
    licença permitiria publicar os dados em lote; declarar o uso não autoriza exercê-lo.
    """

    RESEARCH_LOCAL = "research_local"
    PROTOTYPE_LOCAL = "prototype_local"
    PUBLIC_DISPLAY_DERIVED = "public_display_derived"
    REDISTRIBUTION = "redistribution"


PUBLIC_USES = frozenset({AllowedUse.PUBLIC_DISPLAY_DERIVED, AllowedUse.REDISTRIBUTION})


class Club(BaseModel):
    model_config = ConfigDict(frozen=True)

    club_id: str = Field(pattern=r"^[a-z0-9-]+$")
    display_name: str
    short_name: str = Field(min_length=2, max_length=4)
    state: str = Field(min_length=2, max_length=2)
    aliases: tuple[str, ...]


BRASILIA_TIMEZONE = ZoneInfo("America/Sao_Paulo")


class MatchRecord(BaseModel):
    """Partida normalizada (camada silver). Placar ausente nunca é preenchido.

    `kickoff_utc` e `kickoff_time_confirmed` são opcionais (ADR-0009, Decisão 2): só a fonte com
    horário os preenche. Com `kickoff_utc`, `match_date` é a data dele em America/Sao_Paulo.
    `kickoff_time_confirmed` é `None` sem horário na fonte e `False` quando a fonte tem o jogo, mas
    o horário ainda é provisório ou inexistente (só a data).
    """

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
    kickoff_utc: datetime | None = None
    kickoff_time_confirmed: bool | None = None

    @field_validator("kickoff_utc")
    @classmethod
    def _kickoff_in_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("kickoff_utc sem fuso horário")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _check_consistency(self) -> MatchRecord:
        if self.home_id == self.away_id:
            raise ValueError("mandante e visitante iguais")
        if self.kickoff_utc is not None:
            kickoff_day = self.kickoff_utc.astimezone(BRASILIA_TIMEZONE).date()
            if kickoff_day != self.match_date:
                raise ValueError(f"kickoff_utc em Brasília cai em {kickoff_day}, mas match_date é {self.match_date}")
            if self.kickoff_time_confirmed is None:
                raise ValueError("kickoff_utc sem kickoff_time_confirmed")
        if self.kickoff_time_confirmed is True and self.kickoff_utc is None:
            raise ValueError("horário confirmado sem kickoff_utc")
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
    """Proveniência de uma ingestão. Os campos de termos são obrigatórios para fontes publicáveis."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    origin: str
    version: str
    retrieved_at: datetime
    files: dict[str, str]
    license_status: LicenseStatus
    license_notes: str
    allowed_uses: list[AllowedUse]
    license_name: str | None = None
    terms_url: str | None = None
    terms_checked_at: date | None = None
    attribution: str | None = None

    @model_validator(mode="after")
    def _check_license_terms(self) -> SourceManifest:
        publishable = self.license_status in PUBLISHABLE_LICENSE_STATUSES
        public_uses = sorted(use.value for use in PUBLIC_USES.intersection(self.allowed_uses))
        if public_uses and not publishable:
            raise ValueError(f"{self.source_name}: usos {public_uses} exigem licença verificada ou com atribuição")
        if publishable:
            missing = [
                name
                for name, value in (
                    ("license_name", self.license_name),
                    ("terms_url", self.terms_url),
                    ("terms_checked_at", self.terms_checked_at),
                )
                if value is None or (isinstance(value, str) and not value.strip())
            ]
            if missing:
                raise ValueError(f"{self.source_name}: {self.license_status.value} sem {missing}")
        if self.license_status == LicenseStatus.LICENSED_WITH_ATTRIBUTION and not (self.attribution or "").strip():
            raise ValueError(f"{self.source_name}: licensed_with_attribution sem texto de atribuição")
        return self

    @property
    def allows_public_display(self) -> bool:
        return (
            self.license_status in PUBLISHABLE_LICENSE_STATUSES
            and AllowedUse.PUBLIC_DISPLAY_DERIVED in self.allowed_uses
        )


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
