"""Gate do artefato de uma liga europeia antes do deploy (ADR-0011, Decisão 5). Saída só com ids e contagens."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

from brasileirao.contracts import BRASILIA_TIMEZONE, PUBLISHABLE_LICENSE_STATUSES, AllowedUse, LicenseStatus
from brasileirao.leagues.schema import LEAGUE_SCHEMA_VERSION, LeagueForecast

TOLERANCE = 1e-6
FORBIDDEN_DIRS = ("raw", "silver", "gold", "snapshots", "editorial")


def check_forecast_core(forecast: LeagueForecast, today: date) -> list[str]:
    findings: list[str] = []
    if forecast.schema_version != LEAGUE_SCHEMA_VERSION:
        findings.append(f"schema_version {forecast.schema_version} != {LEAGUE_SCHEMA_VERSION}")
    if date.fromisoformat(forecast.reference_date) > today:
        findings.append(f"reference_date {forecast.reference_date} no futuro (hoje: {today})")
    if forecast.backtest is not None and forecast.backtest.get("model_version") != forecast.model_version:
        findings.append(f"backtest de {forecast.backtest.get('model_version')} exibido com {forecast.model_version}")
    n_clubs = len(forecast.teams)
    matches_per_club = 2 * (n_clubs - 1)
    for zone in forecast.zones:
        total = sum(team.zones[zone.zone_id] for team in forecast.teams)
        if not math.isclose(total, zone.last - zone.first + 1, abs_tol=1e-3):
            findings.append(f"soma da zona {zone.zone_id} = {total:.4f}; esperado {zone.last - zone.first + 1}")
    for team in forecast.teams:
        if len(team.position_probabilities) != n_clubs or not math.isclose(
            sum(team.position_probabilities), 1.0, abs_tol=TOLERANCE
        ):
            findings.append(f"{team.club_id}: posições não somam 1")
        if team.played + team.remaining != matches_per_club:
            findings.append(f"{team.club_id}: {team.played} jogos + {team.remaining} restantes != {matches_per_club}")
        for zone_id, state in team.clinched.items():
            probability = team.zones[zone_id]
            if (state == "in" and probability < 1 - TOLERANCE) or (state == "out" and probability > TOLERANCE):
                findings.append(f"{team.club_id}: zona {zone_id} '{state}' pela aritmética e contrariada na simulação")
    if sum(team.played for team in forecast.teams) != 2 * forecast.observed_matches:
        findings.append("jogos observados não batem com a tabela")
    if len(forecast.remaining) != forecast.remaining_matches:
        findings.append("jogos restantes sem probabilidade")
    for match in forecast.remaining:
        if not math.isclose(match.p_home + match.p_draw + match.p_away, 1.0, abs_tol=1e-6):
            findings.append(f"{match.match_id}: 1X2 não soma 1")
    return findings


def check_forecast(forecast: LeagueForecast, sources: dict[str, Any], today: date) -> list[str]:
    findings = check_forecast_core(forecast, today)
    reference_date = date.fromisoformat(forecast.reference_date)
    if reference_date != date.fromisoformat(str(sources["reference_date"])):
        findings.append("reference_date difere do sources.json")
    if sources.get("competition") != forecast.competition:
        findings.append(f"sources.json de {sources.get('competition')} com forecast de {forecast.competition}")
    credited = {(source.source_name, source.version) for source in forecast.sources}
    for item in sources["sources"]:
        status = LicenseStatus(item["license_status"])
        if (
            status not in PUBLISHABLE_LICENSE_STATUSES
            or AllowedUse.PUBLIC_DISPLAY_DERIVED.value not in item["allowed_uses"]
        ):
            findings.append(f"fonte {item['tag']} sem uso público")
        if not item.get("attribution"):
            findings.append(f"fonte {item['tag']} sem atribuição")
        if (item["source_name"], item["version"]) not in credited:
            findings.append(f"fonte {item['tag']} usada e não creditada")
        collected_on = datetime.fromisoformat(str(item["retrieved_at"])).astimezone(BRASILIA_TIMEZONE).date()
        if item["source_name"] == "football_data_org" and reference_date > collected_on:
            findings.append(f"reference_date {reference_date} posterior à coleta de {item['tag']} ({collected_on})")
    return findings


def check_artifact(
    site_dir: Path,
    sources: dict[str, Any] | None,
    today: date,
    competition: str,
    live_reference_date: date | None = None,
) -> list[str]:
    """Sem `sources` (fallback do workflow), só as checagens do próprio forecast."""
    forecast_path = site_dir / "data" / "forecast.json"
    if not forecast_path.exists():
        return [f"{forecast_path} ausente"]
    try:
        forecast = LeagueForecast.model_validate_json(forecast_path.read_text(encoding="utf-8"))
    except ValueError as error:
        return [f"forecast.json fora do esquema: {type(error).__name__}"]
    findings = check_forecast_core(forecast, today) if sources is None else check_forecast(forecast, sources, today)
    if forecast.competition != competition:
        findings.append(f"forecast de {forecast.competition} publicado em /{competition}/")
    for required in ("index.html", "app.js", "styles.css"):
        if not (site_dir / required).exists():
            findings.append(f"{required} ausente no artefato")
    for forbidden in FORBIDDEN_DIRS:
        if (site_dir / "data" / forbidden).exists():
            findings.append(f"pasta data/{forbidden} no artefato")
    if live_reference_date is not None and date.fromisoformat(forecast.reference_date) < live_reference_date:
        findings.append(f"reference_date {forecast.reference_date} anterior à do site no ar ({live_reference_date})")
    extra = sorted(path.name for path in (site_dir / "data").iterdir() if path.name != "forecast.json")
    if extra:
        findings.append(f"arquivos inesperados em data/: {extra}")
    return findings


def summary_line(site_dir: Path) -> str:
    payload = json.loads((site_dir / "data" / "forecast.json").read_text(encoding="utf-8"))
    return (
        f"{payload['competition_name']} | referência {payload['reference_date']} | modelo {payload['model_version']} | "
        f"dados {payload['data_version']} | {payload['observed_matches']} jogos observados, "
        f"{payload['remaining_matches']} restantes | {payload['n_simulations']} simulações"
    )
