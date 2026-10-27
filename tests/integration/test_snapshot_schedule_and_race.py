"""Snapshot 1.1: tabela restante e corrida pela Sul-Americana, com dados SINTÉTICOS (synthetic)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.config import RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.pipeline import ModelConfig, build_snapshot
from brasileirao.storage.schema import DataInfo, PredictionSnapshot

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
    return build_snapshot(
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


def test_every_team_has_schedule(snapshot: PredictionSnapshot) -> None:
    assert all(team.schedule is not None for team in snapshot.teams)


def test_schedule_covers_every_remaining_match_twice(snapshot: PredictionSnapshot) -> None:
    total = sum(team.schedule.remaining_matches for team in snapshot.teams if team.schedule)
    assert total == 2 * snapshot.remaining_matches


def test_schedule_points_match_published_match_probabilities(snapshot: PredictionSnapshot) -> None:
    matches = {match.match_id: match for match in snapshot.matches}
    team = snapshot.teams[0]
    assert team.schedule is not None
    first = team.schedule.matches[0]
    published = matches[first.match_id]
    win = published.p_home if first.venue == "home" else published.p_away
    assert first.p_win == pytest.approx(win)


def test_difficulty_ranks_are_a_permutation(snapshot: PredictionSnapshot) -> None:
    ranks = sorted(team.schedule.difficulty_rank for team in snapshot.teams if team.schedule)
    assert ranks == list(range(1, 21))


def test_schedule_scale_is_published(snapshot: PredictionSnapshot) -> None:
    assert snapshot.schedule_scale is not None and snapshot.schedule_scale.half_range_points > 0


def test_every_team_has_sudamericana_race(snapshot: PredictionSnapshot) -> None:
    assert all(team.sudamericana_race is not None for team in snapshot.teams)


def test_sudamericana_race_bounds_scenario_range(snapshot: PredictionSnapshot) -> None:
    assert all(
        team.sudamericana_race.all_scenarios <= team.sudamericana.min + 1e-12
        and team.sudamericana.max <= team.sudamericana_race.any_scenario + 1e-12
        for team in snapshot.teams
        if team.sudamericana_race
    )


def test_snapshot_round_trips_through_json(snapshot: PredictionSnapshot) -> None:
    assert PredictionSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
