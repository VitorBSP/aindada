from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from apps.api.main import create_app
from fastapi.testclient import TestClient

from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.config import RatingParams
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.pipeline import ModelConfig, build_round_review, build_snapshot
from brasileirao.storage.schema import DataInfo
from brasileirao.storage.snapshots import SnapshotStore


@pytest.fixture(scope="module")
def client(
    tmp_path_factory: pytest.TempPathFactory,
    synthetic_matches: pd.DataFrame,
    synthetic_rules: SeasonRules,
    synthetic_registry: ClubRegistry,
) -> TestClient:
    store = SnapshotStore(tmp_path_factory.mktemp("api") / "s.sqlite", include_research=True)
    info = DataInfo(
        source="synthetic", version="synthetic", license_status="synthetic", retrieved_at="2032-10-01", warnings=[]
    )
    store.save(
        build_snapshot(
            synthetic_matches,
            2032,
            date(2032, 10, 25),
            200,
            1,
            synthetic_rules,
            synthetic_registry,
            ModelConfig("elo_only", RatingParams(), True),
            info,
        )
    )
    season_matches = synthetic_matches[synthetic_matches["season"] == 2032]
    round_three = pd.Timestamp(season_matches.loc[season_matches["round"] == 3, "match_date"].min()).date()
    store.save_round_review(
        build_round_review(
            synthetic_matches,
            2032,
            round_three,
            100,
            1,
            synthetic_rules,
            synthetic_registry,
            ModelConfig("elo_only", RatingParams(), True),
            info,
        )
    )
    return TestClient(create_app(store, Path("missing.json")))


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_seasons_lists_snapshot_season(client: TestClient) -> None:
    assert client.get("/api/seasons").json()[0]["season"] == 2032


def test_predictions_returns_twenty_teams(client: TestClient) -> None:
    assert len(client.get("/api/seasons/2032/predictions").json()["teams"]) == 20


def test_unknown_season_is_404(client: TestClient) -> None:
    assert client.get("/api/seasons/1999/standings").status_code == 404


def test_unknown_team_is_404(client: TestClient) -> None:
    assert client.get("/api/seasons/2032/teams/nao-existe").status_code == 404


def test_team_endpoint_returns_matches(client: TestClient) -> None:
    assert len(client.get("/api/seasons/2032/teams/sintetico-03").json()["matches"]) == 38


def test_metrics_missing_report_is_404(client: TestClient) -> None:
    assert client.get("/api/models/metrics").status_code == 404


def test_rounds_returns_pre_season_first(client: TestClient) -> None:
    assert client.get("/api/seasons/2032/rounds").json()["rounds"][0]["round_number"] == 0


def test_rounds_missing_season_is_404(client: TestClient) -> None:
    assert client.get("/api/seasons/1999/rounds").status_code == 404
