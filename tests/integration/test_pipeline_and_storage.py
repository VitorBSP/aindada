"""Pipeline ponta a ponta com dados SINTÉTICOS (nunca apresentados como reais)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.config import RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.pipeline import ModelConfig, build_round_review, build_snapshot, probability_history
from brasileirao.storage.schema import DataInfo, PredictionSnapshot, RoundReview
from brasileirao.storage.snapshots import SnapshotStore

DATA_INFO = DataInfo(
    source="synthetic-fixture",
    version="synthetic",
    license_status="synthetic",
    retrieved_at="2032-10-01T00:00:00",
    warnings=["dados sintéticos de teste"],
)


@pytest.fixture(scope="module")
def snapshot(
    synthetic_matches: pd.DataFrame, synthetic_rules: SeasonRules, synthetic_registry: ClubRegistry
) -> PredictionSnapshot:
    built = build_snapshot(
        synthetic_matches,
        2032,
        date(2032, 10, 25),
        300,
        3,
        synthetic_rules,
        synthetic_registry,
        ModelConfig("elo_attack_defense", RatingParams(), True),
        DATA_INFO,
    )
    return built.model_copy(update={"is_synthetic": False})


def test_snapshot_has_twenty_teams(snapshot: PredictionSnapshot) -> None:
    assert len(snapshot.teams) == 20


def test_snapshot_counts_all_380_matches(snapshot: PredictionSnapshot) -> None:
    assert snapshot.observed_matches + snapshot.remaining_matches == 380


def test_remaining_matches_have_probabilities(snapshot: PredictionSnapshot) -> None:
    remaining = [match for match in snapshot.matches if match.status != "finished"]
    assert all(abs((m.p_home or 0) + (m.p_draw or 0) + (m.p_away or 0) - 1) < 1e-6 for m in remaining)


def test_scenario_ranges_bound_each_scenario(snapshot: PredictionSnapshot) -> None:
    team = snapshot.teams[0]
    values = team.libertadores_total.by_scenario.values()
    assert all(team.libertadores_total.min <= value <= team.libertadores_total.max for value in values)


def test_store_round_trip(tmp_path: Path, snapshot: PredictionSnapshot) -> None:
    store = SnapshotStore(tmp_path / "s.sqlite", include_research=True)
    snapshot_id = store.save(snapshot)
    assert store.load(snapshot_id).reference_date == snapshot.reference_date


def test_synthetic_snapshots_hidden_from_listing(tmp_path: Path, snapshot: PredictionSnapshot) -> None:
    store = SnapshotStore(tmp_path / "s.sqlite", include_research=True)
    store.save(snapshot.model_copy(update={"is_synthetic": True}))
    assert store.list_records() == []


def test_probability_history_keeps_latest_per_date(tmp_path: Path, snapshot: PredictionSnapshot) -> None:
    store = SnapshotStore(tmp_path / "s.sqlite", include_research=True)
    store.save(snapshot)
    store.save(snapshot.model_copy(update={"generated_at": "9999-01-01T00:00:00"}))
    assert len(probability_history(store, 2032)) == 1


@pytest.fixture(scope="module")
def round_review(
    synthetic_matches: pd.DataFrame, synthetic_rules: SeasonRules, synthetic_registry: ClubRegistry
) -> RoundReview:
    season_matches = synthetic_matches[synthetic_matches["season"] == 2032]
    round_four = pd.Timestamp(season_matches.loc[season_matches["round"] == 4, "match_date"].min()).date()
    return build_round_review(
        synthetic_matches,
        2032,
        round_four,
        300,
        3,
        synthetic_rules,
        synthetic_registry,
        ModelConfig("elo_attack_defense", RatingParams(), True),
        DATA_INFO,
    )


def test_round_review_starts_at_pre_season(round_review: RoundReview) -> None:
    assert [view.round_number for view in round_review.rounds][:2] == [0, 1]


def test_round_review_attributes_matches_after_pre_season(round_review: RoundReview) -> None:
    assert all(view.matches for view in round_review.rounds[1:])


def test_round_review_round_trip(tmp_path: Path, round_review: RoundReview) -> None:
    store = SnapshotStore(tmp_path / "reviews.sqlite", include_research=True)
    store.save_round_review(round_review)
    assert store.latest_round_review(2032) == round_review
