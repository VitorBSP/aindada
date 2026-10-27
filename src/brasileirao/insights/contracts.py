"""Contrato 08A → 08 → 04 (espelha docs/storytelling/contracts/insight.schema.json)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

ContractVersion = Literal["1.0.0"]
CONTRACT_VERSION: ContractVersion = "1.0.0"

Category = Literal["title", "relegation", "libertadores", "sudamericana", "surprise", "trend", "match", "season"]
Source = Literal["predictions", "probability_history", "rounds", "metrics"]
Placement = Literal["home_lead", "home_secondary", "club", "round", "matches", "season"]
SuggestedPlacement = Literal["home", "club", "round", "matches", "season"]
Visual = Literal["before_after_bar", "range_bar", "mini_series", "position_distribution", "match_line", "text_only"]
CausalClaim = Literal["none", "temporal_only", "decomposition_supported"]
Decision = Literal["approved", "needs_revision", "rejected"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SnapshotRef(_Strict):
    snapshot_id: str = Field(min_length=1)
    season: int = Field(ge=2003)
    reference_date: date
    round_number: int | None = Field(default=None, ge=0)
    model_version: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    seed: int
    n_simulations: int = Field(ge=1)


class Subject(_Strict):
    kind: Literal["club", "match", "league"]
    id: str = Field(min_length=1)
    label: str | None = None


class ValueRange(_Strict):
    min: float
    max: float


class Evidence(_Strict):
    source: Source
    path: str
    metric: str
    current: float
    previous: float | None = None
    previous_snapshot_id: str | None = None
    delta_pp: float | None = None
    relative_change: float | None = None
    range: ValueRange | None = None
    noise_threshold_pp: float | None = None


class ReferencePeriod(_Strict):
    from_: date = Field(validation_alias=AliasChoices("from", "from_"), serialization_alias="from")
    to: date


class Relevance(_Strict):
    relevance: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    materiality: float = Field(ge=0, le=1)
    diversity: float = Field(ge=0, le=1)
    score: float = Field(ge=0, le=1)


class Uncertainty(_Strict):
    passes_noise_test: bool
    causal_claim: CausalClaim = "none"
    depends_on_external_tournaments: bool = False
    notes: list[str] = Field(default_factory=list)


class InsightCandidate(_Strict):
    insight_id: str = Field(pattern=r"^ins_[0-9a-f]{16}$")
    insight_version: int = Field(ge=1)
    rule_id: str = Field(pattern=r"^[A-Z_]+$")
    category: Category
    subjects: list[Subject] = Field(min_length=1)
    headline: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=320)
    evidence: list[Evidence] = Field(min_length=1)
    reference_period: ReferencePeriod
    relevance: Relevance
    suggested_placement: list[SuggestedPlacement] = Field(default_factory=list)
    suggested_visual: Visual = "text_only"
    uncertainty: Uncertainty
    llm_assisted: bool = False
    status: Literal["candidate"] = "candidate"


class InsightBatch(_Strict):
    contract_version: ContractVersion = CONTRACT_VERSION
    batch_id: str = Field(min_length=1)
    generated_at: str
    snapshot_ref: SnapshotRef
    previous_snapshot_ref: SnapshotRef | None = None
    rules_version: str = Field(pattern=r"^rules-\d{4}\.\d{2}\.\d+$")
    criteria_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    synthetic: bool = False
    candidates: list[InsightCandidate]


class Checklist(_Strict):
    correct: bool
    supported: bool
    interesting: bool
    adds_information: bool
    clear: bool
    on_voice: bool
    not_duplicate: bool
    visual_fit: bool
    not_misleading: bool

    @classmethod
    def all_true(cls, failed: set[str] | None = None) -> Checklist:
        failed = failed or set()
        unknown = failed - set(cls.model_fields)
        if unknown:
            raise ValueError(f"itens de checklist desconhecidos: {sorted(unknown)}")
        return cls(**{name: name not in failed for name in cls.model_fields})


class EditorialReview(_Strict):
    contract_version: ContractVersion = CONTRACT_VERSION
    insight_id: str = Field(pattern=r"^ins_[0-9a-f]{16}$")
    insight_version: int = Field(ge=1)
    decision: Decision
    reason: str = Field(min_length=1)
    checklist: Checklist
    edited_headline: str | None = Field(default=None, max_length=80)
    edited_body: str | None = Field(default=None, max_length=320)
    placement: Placement | None = None
    priority: int | None = Field(default=None, ge=1)
    editor: str
    reviewed_at: str
    criteria_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _approved_needs_placement_and_core_checks(self) -> EditorialReview:
        if self.decision != "approved":
            return self
        if self.placement is None or self.priority is None:
            raise ValueError("insight aprovado precisa de placement e priority")
        core = self.checklist
        if not (core.correct and core.supported and core.not_misleading):
            raise ValueError("insight aprovado precisa ser correto, sustentado e não enganoso")
        return self


class PublishedInsight(_Strict):
    contract_version: ContractVersion = CONTRACT_VERSION
    insight_id: str = Field(pattern=r"^ins_[0-9a-f]{16}$")
    insight_version: int = Field(ge=1)
    rule_id: str = Field(pattern=r"^[A-Z_]+$")
    status: Literal["published", "retired"]
    headline: str = Field(max_length=80)
    body: str = Field(max_length=320)
    placement: Placement
    priority: int = Field(ge=1)
    subjects: list[Subject] = Field(default_factory=list)
    visual: str | None = None
    snapshot_ref: SnapshotRef
    evidence: list[Evidence] = Field(min_length=1)
    published_at: str
    retired_at: str | None = None
    retired_reason: str | None = None
