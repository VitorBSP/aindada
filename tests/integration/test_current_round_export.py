"""`current-round.json` no export estático e campos de horário do `MatchPrediction` (ADR-0009).

Dados SINTÉTICOS (synthetic), temporada 2032; nunca apresentados como reais.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.config import RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.data_pipeline.ingest import with_kickoff_columns
from brasileirao.pipeline import ModelConfig, build_round_review, build_snapshot, export_static_api
from brasileirao.storage.schema import DataInfo
from brasileirao.storage.snapshots import SnapshotStore

SEASON = 2032
METRICS = ("title", "top4", "relegation")
REFERENCE = date(2032, 4, 15)
ROUND_FOUR_DAY = "2032-04-22"
INFO = DataInfo(
    source="synthetic", version="synthetic", license_status="synthetic", retrieved_at="2032-04-15", warnings=[]
)
CONFIRMED_ID = f"syn-{SEASON}-04-00"
UNCONFIRMED_ID = f"syn-{SEASON}-04-01"
POSTPONED_ID = f"syn-{SEASON}-05-00"
DELAYED_ID = f"syn-{SEASON}-02-00"


def _set(matches_data: pd.DataFrame, match_id: str, **values: Any) -> None:
    row = matches_data["match_id"] == match_id
    for column, value in values.items():
        matches_data.loc[row, column] = value


@pytest.fixture(scope="module")
def kickoff_matches(synthetic_matches: pd.DataFrame) -> pd.DataFrame:
    matches_data = with_kickoff_columns(synthetic_matches)
    _set(matches_data, CONFIRMED_ID, kickoff_utc="2032-04-22T22:00:00Z", kickoff_time_confirmed=True)
    _set(matches_data, UNCONFIRMED_ID, kickoff_utc="2032-04-23T00:00:00Z", kickoff_time_confirmed=False)
    _set(matches_data, POSTPONED_ID, status="postponed", home_goals=pd.NA, away_goals=pd.NA)
    _set(
        matches_data,
        DELAYED_ID,
        status="scheduled",
        home_goals=pd.NA,
        away_goals=pd.NA,
        match_date=pd.Timestamp(ROUND_FOUR_DAY),
    )
    return matches_data


@pytest.fixture(scope="module")
def store(
    tmp_path_factory: pytest.TempPathFactory,
    kickoff_matches: pd.DataFrame,
    synthetic_rules: SeasonRules,
    synthetic_registry: ClubRegistry,
) -> SnapshotStore:
    snapshot_store = SnapshotStore(tmp_path_factory.mktemp("current-round") / "s.sqlite", include_research=True)
    config = ModelConfig("elo_only", RatingParams(), True)
    snapshot_store.save(
        build_snapshot(kickoff_matches, SEASON, REFERENCE, 200, 1, synthetic_rules, synthetic_registry, config, INFO)
    )
    snapshot_store.save_round_review(
        build_round_review(
            kickoff_matches, SEASON, REFERENCE, 100, 1, synthetic_rules, synthetic_registry, config, INFO
        )
    )
    return snapshot_store


def _export(store: SnapshotStore, target: Path, now: datetime) -> dict[str, Any]:
    export_static_api(store, SEASON, target, now=now)
    season_dir = target / "api" / "seasons" / str(SEASON)
    return {
        name: json.loads((season_dir / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("current-round", "predictions", "rounds")
    }


@pytest.fixture(scope="module")
def in_progress(store: SnapshotStore, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return _export(store, tmp_path_factory.mktemp("export-a"), datetime(2032, 4, 22, 12, tzinfo=UTC))


@pytest.fixture(scope="module")
def finished(store: SnapshotStore, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return _export(store, tmp_path_factory.mktemp("export-b"), datetime(2032, 4, 17, 12, tzinfo=UTC))


def _match(documents: dict[str, Any], match_id: str) -> dict[str, Any]:
    return next(match for match in documents["predictions"]["matches"] if match["match_id"] == match_id)


def test_round_of_the_day_is_in_progress(in_progress: dict[str, Any]) -> None:
    round_info = in_progress["current-round"]["round"]
    assert (round_info["round_number"], round_info["state"]) == (4, "in_progress")


def test_delayed_match_listed_in_round(in_progress: dict[str, Any]) -> None:
    assert DELAYED_ID in in_progress["current-round"]["round"]["match_ids"]


def test_last_round_before_next_start_is_finished(finished: dict[str, Any]) -> None:
    round_info = finished["current-round"]["round"]
    assert (round_info["round_number"], round_info["state"]) == (3, "finished")


def test_listed_ids_exist_in_predictions(in_progress: dict[str, Any]) -> None:
    round_info = in_progress["current-round"]["round"]
    known = {match["match_id"] for match in in_progress["predictions"]["matches"]}
    assert set(round_info["match_ids"]) | set(round_info["rescheduled_match_ids"]) <= known


def test_lists_are_disjoint(in_progress: dict[str, Any]) -> None:
    round_info = in_progress["current-round"]["round"]
    assert not set(round_info["match_ids"]) & set(round_info["rescheduled_match_ids"])


def test_baseline_has_prediction_clubs(in_progress: dict[str, Any]) -> None:
    clubs = {team["club_id"] for team in in_progress["predictions"]["teams"]}
    assert set(in_progress["current-round"]["round"]["baseline"]["teams"]) == clubs


def test_baseline_equals_cited_view(in_progress: dict[str, Any]) -> None:
    baseline = in_progress["current-round"]["round"]["baseline"]
    views = [view for view in in_progress["rounds"]["rounds"] if view["reference_date"] == baseline["reference_date"]]
    cited = [
        {club: {metric: values[metric] for metric in METRICS} for club, values in view["teams"].items()}
        for view in views
    ]
    assert cited == [baseline["teams"]]


def test_baseline_has_contract_metrics(in_progress: dict[str, Any]) -> None:
    teams = in_progress["current-round"]["round"]["baseline"]["teams"]
    assert {tuple(values) for values in teams.values()} == {METRICS}


def test_baseline_precedes_round_start(in_progress: dict[str, Any]) -> None:
    round_info = in_progress["current-round"]["round"]
    assert round_info["baseline"]["reference_date"] < round_info["starts_on"]


def test_versions_match_predictions(in_progress: dict[str, Any]) -> None:
    current, predictions = in_progress["current-round"], in_progress["predictions"]
    assert (current["updated_at"], current["model_version"], current["data_version"]) == (
        predictions["generated_at"],
        predictions["model"]["model_version"],
        predictions["data"]["version"],
    )


def test_no_score_outside_finished(in_progress: dict[str, Any]) -> None:
    scored = [
        match
        for match in in_progress["predictions"]["matches"]
        if match["status"] != "finished" and (match["home_goals"] is not None or match["away_goals"] is not None)
    ]
    assert scored == []


def test_current_round_has_no_scores(in_progress: dict[str, Any]) -> None:
    text = json.dumps(in_progress["current-round"])
    assert "home_goals" not in text and "away_goals" not in text


def test_confirmed_kickoff_is_exported(in_progress: dict[str, Any]) -> None:
    assert _match(in_progress, CONFIRMED_ID)["kickoff_utc"] == "2032-04-22T22:00:00Z"


def test_unconfirmed_kickoff_is_null(in_progress: dict[str, Any]) -> None:
    assert _match(in_progress, UNCONFIRMED_ID)["kickoff_utc"] is None


def test_source_match_id_is_exported(in_progress: dict[str, Any]) -> None:
    assert _match(in_progress, CONFIRMED_ID)["source_match_id"] == f"{SEASON}-3-0"


def test_postponed_status_is_kept(in_progress: dict[str, Any]) -> None:
    assert _match(in_progress, POSTPONED_ID)["status"] == "postponed"


def test_finished_after_reference_stays_scheduled(in_progress: dict[str, Any]) -> None:
    assert _match(in_progress, f"syn-{SEASON}-06-00")["status"] == "scheduled"
