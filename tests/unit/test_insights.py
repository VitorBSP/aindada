"""Subagente 08A: regras, portões e fluxo editorial. Todos os dados aqui são sintéticos."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from brasileirao.config import PATHS
from brasileirao.insights.contracts import EditorialReview, InsightBatch, InsightCandidate, SnapshotRef
from brasileirao.insights.criteria import InsightCriteria, load_criteria
from brasileirao.insights.editorial import (
    EditorialError,
    EditorialStore,
    export_published,
    gate_review,
    publish_latest,
    review_candidate,
)
from brasileirao.insights.gates import check_candidate
from brasileirao.insights.generator import build_batch
from brasileirao.insights.rules import (
    ClubValues,
    RoundContext,
    RuleInput,
    SnapshotView,
    match_moved_most,
    relegation_riser,
    title_faller,
    title_riser,
)
from brasileirao.storage.schema import MatchImpactInfo, RoundSummaryInfo, RoundViewInfo

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "insights" / "insight_batch.synthetic.json"
SCHEMA = PATHS.root / "docs" / "storytelling" / "contracts" / "insight.schema.json"
NOW = "2032-10-20T12:00:00+00:00"


@pytest.fixture(scope="module")
def criteria() -> InsightCriteria:
    return load_criteria()


def ref(snapshot_id: str, day: date, n_simulations: int = 10_000) -> SnapshotRef:
    return SnapshotRef(
        snapshot_id=snapshot_id,
        season=2032,
        reference_date=day,
        model_version="synthetic-model",
        data_version="synthetic-data",
        seed=1,
        n_simulations=n_simulations,
    )


def view(snapshot_id: str, day: date, values: dict[str, tuple[float, float, float]], n: int = 10_000) -> SnapshotView:
    clubs = {
        club: ClubValues(name=f"Sintético {club.upper()}", title=title, top4=top4, relegation=relegation)
        for club, (title, top4, relegation) in values.items()
    }
    return SnapshotView(ref=ref(snapshot_id, day, n), clubs=clubs)


BEFORE = date(2032, 10, 10)
AFTER = date(2032, 10, 17)


def rule_input(
    criteria: InsightCriteria,
    previous: dict[str, tuple[float, float, float]],
    current: dict[str, tuple[float, float, float]],
    n: int = 10_000,
    round_context: RoundContext | None = None,
) -> RuleInput:
    return RuleInput(
        current=view("s2", AFTER, current, n),
        previous=view("s1", BEFORE, previous, n),
        criteria=criteria,
        round_context=round_context,
    )


TABLE_BEFORE = {"a": (0.40, 0.90, 0.0), "b": (0.55, 0.95, 0.0), "c": (0.05, 0.30, 0.20), "d": (0.0, 0.01, 0.50)}
TABLE_AFTER = {"a": (0.60, 0.97, 0.0), "b": (0.36, 0.90, 0.0), "c": (0.04, 0.25, 0.33), "d": (0.0, 0.01, 0.52)}


def round_context_with_impact(impact: float) -> RoundContext:
    match = MatchImpactInfo(
        match_id="m1",
        round=30,
        match_date="2032-10-15",
        home_id="c",
        away_id="d",
        home_goals=0,
        away_goals=2,
        outcome="away",
        pre_match={"home": 0.5, "draw": 0.3, "away": 0.2},
        impacts={
            "c": {"title": 0.0, "top4": 0.0, "relegation": impact},
            "d": {"title": 0.0, "top4": 0.0, "relegation": -0.01},
        },
        stakes={},
    )
    summary = RoundSummaryInfo(
        risers={},
        fallers={},
        total_movement={},
        results_movement={},
        strength_movement={},
        residual_movement={},
        expected_noise_movement={},
        decisive_match_id="m1",
    )
    teams = {club: {"title": t, "top4": g, "relegation": r} for club, (t, g, r) in TABLE_BEFORE.items()}
    previous_view = RoundViewInfo(
        round_number=29, reference_date=BEFORE, partial=False, observed_matches=280, teams=teams
    )
    current_view = RoundViewInfo(
        round_number=30,
        reference_date=AFTER,
        partial=False,
        observed_matches=290,
        teams=teams,
        matches=[match],
        summary=summary,
    )
    return RoundContext(view=current_view, previous_view=previous_view, n_simulations=10_000)


def test_title_riser_picks_largest_material_rise(criteria: InsightCriteria) -> None:
    candidates = title_riser(rule_input(criteria, TABLE_BEFORE, TABLE_AFTER))
    assert [item.subjects[0].id for item in candidates] == ["a"]


def test_title_riser_ignores_changes_below_materiality(criteria: InsightCriteria) -> None:
    after = {**TABLE_BEFORE, "a": (0.42, 0.90, 0.0)}
    assert title_riser(rule_input(criteria, TABLE_BEFORE, after)) == []


def test_title_riser_ignores_monte_carlo_noise_with_few_simulations(criteria: InsightCriteria) -> None:
    after = {**TABLE_BEFORE, "a": (0.45, 0.90, 0.0)}
    assert title_riser(rule_input(criteria, TABLE_BEFORE, after, n=200)) == []


def test_title_faller_picks_largest_drop(criteria: InsightCriteria) -> None:
    candidates = title_faller(rule_input(criteria, TABLE_BEFORE, TABLE_AFTER))
    assert candidates[0].subjects[0].id == "b"


def test_relegation_riser_passes_all_gates(criteria: InsightCriteria) -> None:
    candidate = relegation_riser(rule_input(criteria, TABLE_BEFORE, TABLE_AFTER))[0]
    assert check_candidate(candidate, ref("s2", AFTER), criteria) == []


def test_insight_id_is_deterministic(criteria: InsightCriteria) -> None:
    first = title_riser(rule_input(criteria, TABLE_BEFORE, TABLE_AFTER))[0]
    second = title_riser(rule_input(criteria, TABLE_BEFORE, TABLE_AFTER))[0]
    assert first.insight_id == second.insight_id


def test_match_moved_most_reports_material_impact(criteria: InsightCriteria) -> None:
    context = round_context_with_impact(0.09)
    candidates = match_moved_most(rule_input(criteria, TABLE_BEFORE, TABLE_AFTER, round_context=context))
    assert [subject.id for subject in candidates[0].subjects] == ["m1", "c"]


def test_match_moved_most_stays_quiet_below_materiality(criteria: InsightCriteria) -> None:
    context = round_context_with_impact(0.02)
    assert match_moved_most(rule_input(criteria, TABLE_BEFORE, TABLE_AFTER, round_context=context)) == []


def test_match_candidate_passes_all_gates(criteria: InsightCriteria) -> None:
    context = round_context_with_impact(0.09)
    candidate = match_moved_most(rule_input(criteria, TABLE_BEFORE, TABLE_AFTER, round_context=context))[0]
    assert check_candidate(candidate, ref("s2", AFTER), criteria) == []


def _riser(criteria: InsightCriteria) -> InsightCandidate:
    return title_riser(rule_input(criteria, TABLE_BEFORE, TABLE_AFTER))[0]


def test_gate_rejects_number_without_evidence(criteria: InsightCriteria) -> None:
    invented = _riser(criteria).model_copy(update={"body": "A chance foi a 73% depois da rodada."})
    failures = check_candidate(invented, ref("s2", AFTER), criteria)
    assert any(failure.startswith("rastreabilidade") for failure in failures)


def test_gate_rejects_wrong_arithmetic(criteria: InsightCriteria) -> None:
    candidate = _riser(criteria)
    wrong = candidate.evidence[0].model_copy(update={"delta_pp": 35.0})
    failures = check_candidate(candidate.model_copy(update={"evidence": [wrong]}), ref("s2", AFTER), criteria)
    assert any(failure.startswith("aritmética") for failure in failures)


def test_gate_rejects_period_after_reference_date(criteria: InsightCriteria) -> None:
    failures = check_candidate(_riser(criteria), ref("s2", BEFORE), criteria)
    assert any(failure.startswith("temporalidade") for failure in failures)


def test_approved_review_requires_placement(criteria: InsightCriteria) -> None:
    candidate = _riser(criteria)
    with pytest.raises(ValidationError):
        EditorialReview(
            insight_id=candidate.insight_id,
            insight_version=1,
            decision="approved",
            reason="ok",
            checklist=gate_review(candidate, ["x"], criteria.criteria_hash, NOW).checklist.all_true(),
            editor="agente-08",
            reviewed_at=NOW,
            criteria_hash=criteria.criteria_hash,
        )


def _store_with_batch(
    tmp_path: Path, criteria: InsightCriteria, snapshot_id: str = "s2"
) -> tuple[EditorialStore, InsightBatch]:
    store = EditorialStore(tmp_path, 2032)
    data = rule_input(criteria, TABLE_BEFORE, TABLE_AFTER)
    data = RuleInput(current=view(snapshot_id, AFTER, TABLE_AFTER), previous=data.previous, criteria=criteria)
    batch = build_batch(data, NOW).model_copy(update={"synthetic": True})
    store.save_batch(batch)
    return store, batch


def test_gate_rejected_candidate_cannot_be_approved(tmp_path: Path, criteria: InsightCriteria) -> None:
    store, batch = _store_with_batch(tmp_path, criteria)
    candidate = batch.candidates[0]
    store.append_review(gate_review(candidate, ["ruído: teste"], criteria.criteria_hash, NOW))
    with pytest.raises(EditorialError):
        review_candidate(
            store, batch, candidate.insight_id, "approved", "ok", "agente-08", NOW, placement="home_lead", priority=1
        )


def test_publish_includes_only_approved(tmp_path: Path, criteria: InsightCriteria) -> None:
    store, batch = _store_with_batch(tmp_path, criteria)
    first, second = batch.candidates[0], batch.candidates[1]
    review_candidate(
        store, batch, first.insight_id, "approved", "relevante", "agente-08", NOW, placement="home_lead", priority=1
    )
    review_candidate(store, batch, second.insight_id, "rejected", "repetitivo", "agente-08", NOW)
    assert [item.insight_id for item in publish_latest(store, NOW)] == [first.insight_id]


def test_publish_retires_insights_from_previous_batch(tmp_path: Path, criteria: InsightCriteria) -> None:
    store, batch = _store_with_batch(tmp_path, criteria, "s2")
    first = batch.candidates[0]
    review_candidate(
        store, batch, first.insight_id, "approved", "ok", "agente-08", NOW, placement="home_lead", priority=1
    )
    publish_latest(store, NOW)
    _store_with_batch(tmp_path, criteria, "s3")
    publish_latest(store, NOW)
    assert [item.status for item in store.published()] == ["retired"]


def test_export_contains_only_live_insights(tmp_path: Path, criteria: InsightCriteria) -> None:
    store, batch = _store_with_batch(tmp_path, criteria)
    candidate = batch.candidates[0]
    review_candidate(
        store, batch, candidate.insight_id, "approved", "ok", "agente-08", NOW, placement="home_lead", priority=1
    )
    publish_latest(store, NOW)
    target = export_published(store.published(), tmp_path / "web", 2032)
    assert [item["insight_id"] for item in json.loads(target.read_text(encoding="utf-8"))] == [candidate.insight_id]


def test_synthetic_fixture_matches_contract() -> None:
    batch = InsightBatch.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    assert batch.synthetic


def test_json_schema_and_models_require_the_same_candidate_fields() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    required = set(schema["$defs"]["insight_candidate"]["required"])
    model_required = {name for name, info in InsightCandidate.model_fields.items() if info.is_required()}
    assert model_required <= required


def test_api_serves_only_published_insights(tmp_path: Path, criteria: InsightCriteria) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from apps.api.main import create_app  # noqa: PLC0415
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from brasileirao.storage.snapshots import SnapshotStore  # noqa: PLC0415

    store, batch = _store_with_batch(tmp_path / "editorial", criteria)
    approved, rejected = batch.candidates[0], batch.candidates[1]
    review_candidate(
        store, batch, approved.insight_id, "approved", "ok", "agente-08", NOW, placement="home_lead", priority=1
    )
    review_candidate(store, batch, rejected.insight_id, "rejected", "fraco", "agente-08", NOW)
    publish_latest(store, NOW)
    app = create_app(store=SnapshotStore(tmp_path / "s.sqlite"), editorial_dir=tmp_path / "editorial")
    response = TestClient(app).get("/api/seasons/2032/insights")
    assert [item["insight_id"] for item in response.json()] == [approved.insight_id]


def test_edited_text_cannot_cite_numbers_without_evidence(tmp_path: Path, criteria: InsightCriteria) -> None:
    store, batch = _store_with_batch(tmp_path, criteria)
    candidate = batch.candidates[0]
    with pytest.raises(EditorialError):
        review_candidate(
            store,
            batch,
            candidate.insight_id,
            "approved",
            "ok",
            "agente-08",
            NOW,
            placement="home_lead",
            priority=1,
            edited_body="Agora a chance é de 99%.",
        )


def test_match_moved_most_ignores_round_review_from_older_date(criteria: InsightCriteria) -> None:
    context = round_context_with_impact(0.09)
    later = RuleInput(
        current=view("s3", date(2032, 10, 24), TABLE_AFTER),
        previous=view("s2", AFTER, TABLE_BEFORE),
        criteria=criteria,
        round_context=context,
    )
    assert match_moved_most(later) == []
