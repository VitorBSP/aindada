"""Registro editorial: lotes do 08A, revisões do 08 e insights publicados (arquivos JSON)."""

from __future__ import annotations

import json
from pathlib import Path

from brasileirao.insights.contracts import (
    Checklist,
    Decision,
    EditorialReview,
    InsightBatch,
    InsightCandidate,
    Placement,
    PublishedInsight,
)
from brasileirao.insights.gates import NUMBER_TOKEN, allowed_number_tokens

GATE_EDITOR = "portao-automatico"
PLACEMENT_ORDER = ["home_lead", "home_secondary", "round", "club", "matches", "season"]


class EditorialError(ValueError):
    """Operação editorial inválida (candidato inexistente, aprovação proibida etc.)."""


class EditorialStore:
    def __init__(self, root: Path, season: int) -> None:
        self.directory = root / str(season)
        self.batches = self.directory / "batches"
        self.reviews_path = self.directory / "reviews.jsonl"
        self.published_path = self.directory / "published.json"
        self.latest_path = self.directory / "latest_batch.txt"

    def save_batch(self, batch: InsightBatch) -> Path:
        self.batches.mkdir(parents=True, exist_ok=True)
        target = self.batches / f"{batch.batch_id}.json"
        target.write_text(batch.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
        self.latest_path.write_text(batch.batch_id, encoding="utf-8")
        return target

    def load_batch(self, batch_id: str) -> InsightBatch:
        path = self.batches / f"{batch_id}.json"
        if not path.exists():
            raise EditorialError(f"lote {batch_id} não encontrado")
        return InsightBatch.model_validate_json(path.read_text(encoding="utf-8"))

    def latest_batch(self) -> InsightBatch | None:
        if not self.latest_path.exists():
            return None
        return self.load_batch(self.latest_path.read_text(encoding="utf-8").strip())

    def append_review(self, review: EditorialReview) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.reviews_path.open("a", encoding="utf-8") as handle:
            handle.write(review.model_dump_json() + "\n")

    def reviews(self) -> list[EditorialReview]:
        if not self.reviews_path.exists():
            return []
        lines = self.reviews_path.read_text(encoding="utf-8").splitlines()
        return [EditorialReview.model_validate_json(line) for line in lines if line.strip()]

    def latest_review(self, insight_id: str, insight_version: int) -> EditorialReview | None:
        matching = [
            review
            for review in self.reviews()
            if review.insight_id == insight_id and review.insight_version == insight_version
        ]
        return matching[-1] if matching else None

    def published(self) -> list[PublishedInsight]:
        if not self.published_path.exists():
            return []
        documents = json.loads(self.published_path.read_text(encoding="utf-8"))
        return [PublishedInsight.model_validate(document) for document in documents]

    def save_published(self, insights: list[PublishedInsight]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = [insight.model_dump(mode="json", by_alias=True) for insight in insights]
        self.published_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def find_candidate(batch: InsightBatch, insight_id: str) -> InsightCandidate:
    candidate = next((item for item in batch.candidates if item.insight_id == insight_id), None)
    if candidate is None:
        raise EditorialError(f"candidato {insight_id} não está no lote {batch.batch_id}")
    return candidate


def gate_review(candidate: InsightCandidate, failures: list[str], criteria_hash: str, now: str) -> EditorialReview:
    return EditorialReview(
        insight_id=candidate.insight_id,
        insight_version=candidate.insight_version,
        decision="rejected",
        reason="; ".join(failures),
        checklist=Checklist.all_true({"correct", "supported", "not_misleading"}),
        editor=GATE_EDITOR,
        reviewed_at=now,
        criteria_hash=criteria_hash,
    )


def review_candidate(
    store: EditorialStore,
    batch: InsightBatch,
    insight_id: str,
    decision: Decision,
    reason: str,
    editor: str,
    now: str,
    failed_checks: set[str] | None = None,
    placement: Placement | None = None,
    priority: int | None = None,
    edited_headline: str | None = None,
    edited_body: str | None = None,
) -> EditorialReview:
    candidate = find_candidate(batch, insight_id)
    previous = store.latest_review(candidate.insight_id, candidate.insight_version)
    if decision == "approved" and previous is not None and previous.editor == GATE_EDITOR:
        raise EditorialError("candidato reprovado em portão automático não pode ser aprovado")
    allowed = allowed_number_tokens(candidate.evidence)
    for text in (edited_headline, edited_body):
        invented = [token for token in NUMBER_TOKEN.findall(text or "") if token not in allowed]
        if invented:
            raise EditorialError(f"texto editado cita número sem evidência: {', '.join(invented)}")
    review = EditorialReview(
        insight_id=candidate.insight_id,
        insight_version=candidate.insight_version,
        decision=decision,
        reason=reason,
        checklist=Checklist.all_true(failed_checks),
        edited_headline=edited_headline,
        edited_body=edited_body,
        placement=placement,
        priority=priority,
        editor=editor,
        reviewed_at=now,
        criteria_hash=batch.criteria_hash,
    )
    store.append_review(review)
    return review


def publish_latest(store: EditorialStore, now: str) -> list[PublishedInsight]:
    """Publica os aprovados do lote mais recente e retira do ar o que veio de lotes anteriores."""
    batch = store.latest_batch()
    if batch is None:
        raise EditorialError("nenhum lote gerado")
    fresh: list[PublishedInsight] = []
    for candidate in batch.candidates:
        review = store.latest_review(candidate.insight_id, candidate.insight_version)
        if review is None or review.decision != "approved" or review.placement is None or review.priority is None:
            continue
        fresh.append(
            PublishedInsight(
                insight_id=candidate.insight_id,
                insight_version=candidate.insight_version,
                rule_id=candidate.rule_id,
                status="published",
                headline=review.edited_headline or candidate.headline,
                body=review.edited_body or candidate.body,
                placement=review.placement,
                priority=review.priority,
                subjects=candidate.subjects,
                visual=candidate.suggested_visual,
                snapshot_ref=batch.snapshot_ref,
                evidence=candidate.evidence,
                published_at=now,
            )
        )
    fresh_ids = {insight.insight_id for insight in fresh}
    history: list[PublishedInsight] = []
    for insight in store.published():
        if insight.insight_id in fresh_ids:
            continue
        if insight.status != "published":
            history.append(insight)
            continue
        retired = {"status": "retired", "retired_at": now, "retired_reason": f"substituído pelo lote {batch.batch_id}"}
        history.append(insight.model_copy(update=retired))
    store.save_published(history + fresh)
    return active_insights(history + fresh)


def active_insights(insights: list[PublishedInsight]) -> list[PublishedInsight]:
    live = [insight for insight in insights if insight.status == "published"]
    return sorted(live, key=lambda insight: (PLACEMENT_ORDER.index(insight.placement), insight.priority))


def export_published(insights: list[PublishedInsight], output_dir: Path, season: int) -> Path:
    target = output_dir / "api" / "seasons" / str(season) / "insights.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [insight.model_dump(mode="json", by_alias=True) for insight in active_insights(insights)]
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return target
