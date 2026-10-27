"""Monta o lote do 08A a partir dos snapshots persistidos e aplica os portões automáticos."""

from __future__ import annotations

from datetime import date

from brasileirao.config import INSIGHT_RULES_VERSION
from brasileirao.insights.contracts import EditorialReview, InsightBatch, InsightCandidate, SnapshotRef
from brasileirao.insights.criteria import InsightCriteria
from brasileirao.insights.editorial import EditorialStore, gate_review
from brasileirao.insights.gates import check_candidate
from brasileirao.insights.rules import RULES, ClubValues, RoundContext, RuleInput, SnapshotView
from brasileirao.storage.schema import PredictionSnapshot, RoundReview
from brasileirao.storage.snapshots import SnapshotStore


def snapshot_view(snapshot: PredictionSnapshot, snapshot_id: int) -> SnapshotView:
    ref = SnapshotRef(
        snapshot_id=str(snapshot_id),
        season=snapshot.season,
        reference_date=date.fromisoformat(snapshot.reference_date),
        model_version=snapshot.model.model_version,
        data_version=snapshot.data.version,
        seed=snapshot.seed,
        n_simulations=snapshot.n_simulations,
    )
    clubs = {
        team.club_id: ClubValues(name=team.name, title=team.title, top4=team.top4, relegation=team.relegation)
        for team in snapshot.teams
    }
    return SnapshotView(ref=ref, clubs=clubs)


def round_context(review: RoundReview | None, reference_date: date) -> RoundContext | None:
    """Última visão com resumo até a data do snapshot, e a visão anterior a ela."""
    if review is None:
        return None
    eligible = [
        index
        for index, view in enumerate(review.rounds)
        if view.summary is not None and view.reference_date <= reference_date and index > 0
    ]
    if not eligible:
        return None
    index = eligible[-1]
    return RoundContext(
        view=review.rounds[index], previous_view=review.rounds[index - 1], n_simulations=review.n_simulations
    )


def recent_published(store: EditorialStore, window: int) -> list[tuple[str, str]]:
    insights = store.published()
    dates = sorted({insight.snapshot_ref.reference_date for insight in insights}, reverse=True)[:window]
    return [
        (insight.rule_id, insight.subjects[0].id)
        for insight in insights
        if insight.snapshot_ref.reference_date in dates and insight.subjects
    ]


def score_candidates(candidates: list[InsightCandidate], criteria: InsightCriteria) -> list[InsightCandidate]:
    """Pontuação editorial; diversidade penaliza o mesmo clube ou jogo já mais bem colocado."""

    def partial(candidate: InsightCandidate) -> float:
        relevance = candidate.relevance
        return (
            criteria.w_relevance * relevance.relevance
            + criteria.w_novelty * relevance.novelty
            + criteria.w_materiality * relevance.materiality
        )

    seen: set[str] = set()
    scored: list[InsightCandidate] = []
    for candidate in sorted(candidates, key=partial, reverse=True):
        primary = candidate.subjects[0].id
        diversity = 0.0 if primary in seen else 1.0
        seen.add(primary)
        relevance = candidate.relevance.model_copy(
            update={"diversity": diversity, "score": round(partial(candidate) + criteria.w_diversity * diversity, 6)}
        )
        scored.append(candidate.model_copy(update={"relevance": relevance}))
    return scored


def build_batch(rule_input: RuleInput, now: str, previous_ref: SnapshotRef | None = None) -> InsightBatch:
    candidates: list[InsightCandidate] = []
    for rule in RULES.values():
        candidates.extend(rule(rule_input))
    criteria = rule_input.criteria
    ref = rule_input.current.ref
    return InsightBatch(
        batch_id=f"{ref.season}-s{ref.snapshot_id}-{INSIGHT_RULES_VERSION}-{criteria.criteria_hash[:8]}",
        generated_at=now,
        snapshot_ref=ref,
        previous_snapshot_ref=previous_ref,
        rules_version=INSIGHT_RULES_VERSION,
        criteria_hash=criteria.criteria_hash,
        candidates=score_candidates(candidates, criteria),
    )


def generate(
    snapshots: SnapshotStore, editorial: EditorialStore, season: int, criteria: InsightCriteria, now: str
) -> tuple[InsightBatch, list[EditorialReview]]:
    records = snapshots.latest_per_reference_date(season)
    if not records:
        raise RuntimeError(f"nenhum snapshot para {season}")
    current = snapshot_view(snapshots.load(records[-1].snapshot_id), records[-1].snapshot_id)
    previous = (
        snapshot_view(snapshots.load(records[-2].snapshot_id), records[-2].snapshot_id) if len(records) > 1 else None
    )
    rule_input = RuleInput(
        current=current,
        previous=previous,
        criteria=criteria,
        round_context=round_context(snapshots.latest_round_review(season), current.ref.reference_date),
        recent_published=recent_published(editorial, criteria.novelty_window),
    )
    batch = build_batch(rule_input, now, previous.ref if previous else None)
    editorial.save_batch(batch)
    gate_reviews: list[EditorialReview] = []
    for candidate in batch.candidates:
        failures = check_candidate(candidate, batch.snapshot_ref, criteria)
        if failures:
            review = gate_review(candidate, failures, criteria.criteria_hash, now)
            editorial.append_review(review)
            gate_reviews.append(review)
    return batch, gate_reviews
