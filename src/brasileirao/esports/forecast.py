"""Previsão do Mundial de LoL: contrato do `forecast.json`, calibração e montagem (ADR-0013)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from brasileirao.esports.model import LeagueTeamElo, LeagueTeamParams, log_losses, map_probability, series_probability
from brasileirao.esports.sources import Series, TeamRegistry, fetch_article, parse_series
from brasileirao.esports.worlds import (
    FINAL,
    QUARTERFINALS,
    SEMIFINALS,
    SWISS,
    WorldsSimulator,
    complete_only,
    required_wins,
    swiss_records,
)

LOL_SCHEMA_VERSION = "1.0"
LOL_MODEL_VERSION = "lol-0.1.0"
GRID = {
    "k_league": (4.0, 8.0, 16.0, 24.0, 32.0),
    "k_team": (0.0, 8.0, 16.0, 24.0, 32.0),
    "team_regression": (0.0, 0.5, 1.0),
}
RIOT_NOTICE = (
    'AInda dá? foi criado sob a política "Legal Jibber Jabber" da Riot Games usando ativos de propriedade da Riot '
    "Games. A Riot Games não endossa nem patrocina este projeto."
)


class TeamOutlook(BaseModel):
    team_id: str
    name: str
    short_name: str
    league: str
    swiss_wins: int
    swiss_losses: int
    status: str
    rating: float
    league_strength: float
    stages: dict[str, float]


class SeriesOutlook(BaseModel):
    stage: str
    label: str
    match_date: str
    team1: str
    team2: str
    best_of: int
    p_team1: float


class LolForecast(BaseModel):
    schema_version: str = LOL_SCHEMA_VERSION
    competition: str = "mundial-lol"
    competition_name: str
    reference_date: str
    generated_at: str
    n_simulations: int
    seed: int
    model_version: str
    data_version: str
    params: dict[str, float]
    league_strength: dict[str, float]
    teams: list[TeamOutlook]
    upcoming: list[SeriesOutlook]
    warnings: list[str]
    sources: list[dict[str, Any]]
    backtest: dict[str, Any] | None = None
    notice: str = RIOT_NOTICE


def load_pins(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def fetch_all(raw_dir: Path, pins: dict[str, Any]) -> None:
    for title, revision_id in pins["closed_events"].items():
        fetch_article(raw_dir, title, int(revision_id))
    fetch_article(raw_dir, str(pins["current_event"]))


def _latest(raw_dir: Path, title: str) -> Path:
    candidates = sorted((raw_dir / "wikipedia_en").glob(f"{title.replace(' ', '_')}-r*"))
    if not candidates:
        raise FileNotFoundError(f"artigo não ingerido: {title}")
    return max(
        candidates, key=lambda path: json.loads((path / "manifest.json").read_text(encoding="utf-8"))["retrieved_at"]
    )


def load_series(
    raw_dir: Path, pins: dict[str, Any], registry: TeamRegistry
) -> tuple[list[Series], list[Series], list[dict[str, Any]]]:
    """Todas as séries (para os ratings), as do evento corrente e o crédito de cada artigo."""
    every: list[Series] = []
    current: list[Series] = []
    sources: list[dict[str, Any]] = []
    titles = [*pins["closed_events"], pins["current_event"]]
    for title in titles:
        folder = (
            raw_dir / "wikipedia_en" / f"{title.replace(' ', '_')}-r{pins['closed_events'][title]}"
            if title in pins["closed_events"]
            else _latest(raw_dir, title)
        )
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        content = (folder / "page.wikitext").read_bytes()
        if hashlib.sha256(content).hexdigest() != manifest["files"]["page.wikitext"]:
            raise ValueError(f"{folder.name}: SHA-256 não confere com o manifesto")
        series = registry.resolve(parse_series(content.decode("utf-8"), title))
        if title == pins["current_event"]:
            series = complete_only(series)
        every += series
        if title == pins["current_event"]:
            current = series
        sources.append(
            {
                key: manifest[key]
                for key in ("source_name", "origin", "version", "retrieved_at", "license_name", "attribution")
            }
        )
    return every, current, sources


def tune(every: list[Series], pins: dict[str, Any], registry: TeamRegistry) -> dict[str, Any]:
    """Escolha na validação (eventos encerrados depois do primeiro); teste = séries já jogadas do evento corrente."""
    closed = list(pins["closed_events"])
    validation_events, test_event = set(closed[1:]), pins["current_event"]
    records = []
    for k_league in GRID["k_league"]:
        for k_team in GRID["k_team"]:
            for regression in GRID["team_regression"]:
                params = LeagueTeamParams(k_league, k_team, regression)
                predictions = LeagueTeamElo(params, registry.league).run(every)
                validation = log_losses([p for p in predictions if p.series.event in validation_events])
                test = log_losses([p for p in predictions if p.series.event == test_event])
                records.append({**asdict(params), "validation": validation, "test": test})
    chosen = min(records, key=lambda record: record["validation"]["map_log_loss"])
    return {
        "model_version": LOL_MODEL_VERSION,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "protocol": "escolha na validação (eventos encerrados após o primeiro); teste = séries jogadas do evento atual",
        "validation_events": sorted(validation_events),
        "test_event": test_event,
        "chosen": {key: chosen[key] for key in ("k_league", "k_team", "team_regression")},
        "validation": chosen["validation"],
        "test": chosen["test"],
        "candidates": records,
    }


def build_forecast(
    every: list[Series],
    current: list[Series],
    sources: list[dict[str, Any]],
    registry: TeamRegistry,
    params: LeagueTeamParams,
    n_simulations: int,
    seed: int,
    event_name: str,
    backtest: dict[str, Any] | None,
) -> LolForecast:
    elo = LeagueTeamElo(params, registry.league)
    elo.run(every)
    played = [item.match_date for item in current if item.played]
    reference_date: date = max(played)
    simulator = WorldsSimulator(current, elo.rating)
    result = simulator.run(n_simulations, seed)
    teams = [
        TeamOutlook(
            team_id=team,
            name=registry.display[team],
            short_name=registry.short[team],
            league=registry.league[team],
            swiss_wins=record.wins,
            swiss_losses=record.losses,
            status=record.status,
            rating=elo.rating(team),
            league_strength=elo.league_strength[registry.league[team]],
            stages=result.stage_probabilities[team],
        )
        for team, record in simulator.records.items()
    ]
    teams.sort(key=lambda team: (-team.stages["champion"], -team.stages["final"], -team.stages["qualify"], team.name))
    records = swiss_records(current)
    upcoming = []
    for item in current:
        if (
            item.played
            or not item.defined
            or not (item.section.startswith(SWISS) or item.section in (QUARTERFINALS, SEMIFINALS, FINAL))
        ):
            continue
        record = records.get(item.team1)
        best_of = 2 * required_wins(item.section, record.wins if record else 0, record.losses if record else 0) - 1
        win = series_probability(map_probability(elo.rating(item.team1), elo.rating(item.team2)), best_of)
        upcoming.append(
            SeriesOutlook(
                stage=item.section,
                label=item.label,
                match_date=item.match_date.isoformat(),
                team1=item.team1,
                team2=item.team2,
                best_of=best_of,
                p_team1=win,
            )
        )
    tags = sorted(str(source["version"]) for source in sources)
    return LolForecast(
        competition_name=event_name,
        reference_date=reference_date.isoformat(),
        generated_at=datetime.now(tz=UTC).isoformat(),
        n_simulations=n_simulations,
        seed=seed,
        model_version=LOL_MODEL_VERSION,
        data_version=hashlib.sha256("|".join(tags).encode("utf-8")).hexdigest()[:12],
        params=asdict(params),
        league_strength={
            league: float(value) for league, value in sorted(elo.league_strength.items(), key=lambda kv: -kv[1])
        },
        teams=teams,
        upcoming=upcoming,
        warnings=[
            "Só jogos de eventos internacionais (MSI e Mundial de 2025 e 2026): os das ligas nacionais não entram.",
            "Teste curto: o acerto foi medido em poucos mapas do próprio Mundial 2026.",
            "Mapas tratados como independentes dentro da série; sem efeito de lado do mapa.",
            "Onde a organização sorteia (rodada 5 da fase suíça e quartas), a simulação sorteia com a regra da página.",
        ],
        sources=sources,
        backtest=backtest,
    )


def params_from(config: dict[str, Any]) -> LeagueTeamParams:
    return replace(LeagueTeamParams(), **config)
