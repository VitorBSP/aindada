"""API REST (FastAPI). Lê apenas snapshots persistidos; não simula em requisições públicas.

Execução local: `uvicorn apps.api.main:app --reload` (requer `pip install -e .[api]`).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from brasileirao.config import PATHS
from brasileirao.insights.contracts import PublishedInsight
from brasileirao.insights.editorial import EditorialStore, active_insights
from brasileirao.pipeline import HistoryMode, history_mode, probability_history
from brasileirao.storage.current_round import build_current_round
from brasileirao.storage.schema import (
    CurrentRound,
    MatchPrediction,
    PredictionSnapshot,
    RoundReview,
    StandingEntry,
    TeamPrediction,
)
from brasileirao.storage.snapshots import SnapshotStore

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
SERIE_B_DIR = Path(__file__).resolve().parents[1] / "web-serie-b"
LEAGUE_CODES = ("premier-league", "la-liga")


def mount_competition_sites(app: FastAPI) -> None:
    """Mesmo desenho do artefato do Pages (ADR-0010, ADR-0011): `/serie-b/` e `/<liga>/`, com o
    `forecast.json` local de cada um; Champions League (ADR-0012) em `/champions-league/` e Mundial de LoL
    (ADR-0013) em `/mundial-lol/`. Os caminhos mais específicos vêm antes do `/` da Série A."""
    if SERIE_B_DIR.exists():
        app.mount("/serie-b", StaticFiles(directory=SERIE_B_DIR, html=True), name="serie-b")
    for code in LEAGUE_CODES if PATHS.league_web_app.exists() else ():
        forecast_dir = PATHS.league_data(code) / "forecast"
        if forecast_dir.exists():
            app.mount(f"/{code}/data", StaticFiles(directory=forecast_dir), name=f"{code}-data")
        app.mount(f"/{code}", StaticFiles(directory=PATHS.league_web_app, html=True), name=code)
    champions_data = PATHS.league_data("champions-league") / "forecast"
    if PATHS.champions_web_app.exists():
        if champions_data.exists():
            app.mount("/champions-league/data", StaticFiles(directory=champions_data), name="champions-data")
        app.mount("/champions-league", StaticFiles(directory=PATHS.champions_web_app, html=True), name="champions")
    lol_data = PATHS.esports_data / "forecast"
    if PATHS.lol_web_app.exists():
        if lol_data.exists():
            app.mount("/mundial-lol/data", StaticFiles(directory=lol_data), name="lol-data")
        app.mount("/mundial-lol", StaticFiles(directory=PATHS.lol_web_app, html=True), name="lol")


class SeasonInfo(BaseModel):
    season: int
    latest_reference_date: str
    n_snapshots: int
    history_mode: HistoryMode


class StandingsResponse(BaseModel):
    season: int
    reference_date: str
    observed_matches: int
    standings: list[StandingEntry]


class MatchesResponse(BaseModel):
    season: int
    reference_date: str
    matches: list[MatchPrediction]


class TeamResponse(BaseModel):
    season: int
    reference_date: str
    team: TeamPrediction
    standing: StandingEntry
    matches: list[MatchPrediction]
    scenarios: list[dict[str, str]]


def create_app(
    store: SnapshotStore | None = None, metrics_path: Path | None = None, editorial_dir: Path | None = None
) -> FastAPI:
    snapshot_store = store or SnapshotStore(PATHS.snapshots_db)
    report_path = metrics_path or PATHS.gold / "backtest_report.json"
    editorial_root = editorial_dir or PATHS.editorial
    app = FastAPI(title="Brasileirão Predictions API", version="0.1.0")

    def latest_or_404(season: int) -> PredictionSnapshot:
        snapshot = snapshot_store.latest(season)
        if snapshot is None:
            raise HTTPException(status_code=404, detail=f"sem snapshot para a temporada {season}")
        return snapshot

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/seasons", response_model=list[SeasonInfo])
    def seasons() -> list[SeasonInfo]:
        by_season: dict[int, list[str]] = {}
        for record in snapshot_store.list_records():
            by_season.setdefault(record.season, []).append(record.reference_date)
        return [
            SeasonInfo(
                season=season,
                latest_reference_date=max(dates),
                n_snapshots=len(dates),
                history_mode=history_mode(snapshot_store.latest_per_reference_date(season)),
            )
            for season, dates in sorted(by_season.items())
        ]

    @app.get("/api/seasons/{season}/standings", response_model=StandingsResponse)
    def standings(season: int) -> StandingsResponse:
        snapshot = latest_or_404(season)
        return StandingsResponse(
            season=season,
            reference_date=snapshot.reference_date,
            observed_matches=snapshot.observed_matches,
            standings=snapshot.standings,
        )

    @app.get("/api/seasons/{season}/matches", response_model=MatchesResponse)
    def matches(season: int) -> MatchesResponse:
        snapshot = latest_or_404(season)
        return MatchesResponse(season=season, reference_date=snapshot.reference_date, matches=snapshot.matches)

    @app.get("/api/seasons/{season}/predictions", response_model=PredictionSnapshot)
    def predictions(season: int) -> PredictionSnapshot:
        return latest_or_404(season)

    @app.get("/api/seasons/{season}/teams/{team_id}", response_model=TeamResponse)
    def team(season: int, team_id: str) -> TeamResponse:
        snapshot = latest_or_404(season)
        team_prediction = next((item for item in snapshot.teams if item.club_id == team_id), None)
        if team_prediction is None:
            raise HTTPException(status_code=404, detail=f"clube {team_id} não encontrado")
        standing = next(entry for entry in snapshot.standings if entry.club_id == team_id)
        team_matches = [match for match in snapshot.matches if team_id in (match.home_id, match.away_id)]
        return TeamResponse(
            season=season,
            reference_date=snapshot.reference_date,
            team=team_prediction,
            standing=standing,
            matches=team_matches,
            scenarios=[scenario.model_dump() for scenario in snapshot.scenarios],
        )

    @app.get("/api/seasons/{season}/probability-history")
    def history(season: int) -> list[dict[str, Any]]:
        latest_or_404(season)
        return probability_history(snapshot_store, season)

    @app.get("/api/seasons/{season}/rounds", response_model=RoundReview)
    def rounds(season: int) -> RoundReview:
        review = snapshot_store.latest_round_review(season)
        if review is None:
            raise HTTPException(status_code=404, detail=f"sem revisão por rodada para a temporada {season}")
        return review

    @app.get("/api/seasons/{season}/current-round", response_model=CurrentRound)
    def current_round(season: int) -> CurrentRound:
        """Rodada mostrada na aba da home (ADR-0009); `round` nulo na pré-temporada."""
        snapshot = latest_or_404(season)
        return build_current_round(snapshot, snapshot_store.latest_round_review(season), datetime.now(tz=UTC))

    @app.get("/api/seasons/{season}/insights", response_model=list[PublishedInsight])
    def insights(season: int) -> list[PublishedInsight]:
        """Só insights aprovados pelo editor (08) e publicados; candidatos nunca saem por aqui."""
        return active_insights(EditorialStore(editorial_root, season).published())

    @app.get("/api/models/metrics")
    def metrics() -> dict[str, Any]:
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="relatório de backtesting não gerado")
        report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
        report.pop("tuning_records", None)
        report.get("season_simulation", {}).pop("records", None)
        return report

    mount_competition_sites(app)
    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()
