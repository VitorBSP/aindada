"""Gate do artefato da Série B antes do deploy (ADR-0010, Decisão 5). Saída só com ids e contagens."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

from brasileirao.contracts import BRASILIA_TIMEZONE, PUBLISHABLE_LICENSE_STATUSES, AllowedUse, LicenseStatus
from brasileirao.serie_b.schema import SERIE_B_SCHEMA_VERSION, SerieBForecast, TeamForecast

TOLERANCE = 1e-6
FORBIDDEN_DIRS = ("raw", "silver", "gold", "snapshots", "editorial")


def _clinch_findings(team: TeamForecast) -> list[str]:
    """Toda marcação aritmética tem de valer em todas as simulações (a página mostra "subiu", "caiu", "0%")."""
    clinched = team.clinched
    checks = (
        (
            clinched.promoted_direct,
            team.promotion_direct >= 1 - TOLERANCE,
            "subiu pela aritmética e simulado fora do top 2",
        ),
        (clinched.top6, team.promotion_direct + team.playoff >= 1 - TOLERANCE, "top 6 pela aritmética e simulado fora"),
        (
            clinched.out_of_top2,
            team.promotion_direct <= TOLERANCE and team.title <= TOLERANCE,
            "fora do top 2 pela aritmética e simulado dentro",
        ),
        (
            clinched.out_of_top6,
            team.promotion <= TOLERANCE and team.playoff <= TOLERANCE,
            "fora do top 6 pela aritmética e simulado dentro",
        ),
        (clinched.relegated, team.relegation >= 1 - TOLERANCE, "rebaixado pela aritmética e simulado fora da zona"),
        (clinched.safe, team.relegation <= TOLERANCE, "livre pela aritmética e simulado na zona"),
    )
    return [f"{team.club_id}: {message}" for flagged, holds, message in checks if flagged and not holds]


def check_forecast_core(forecast: SerieBForecast, today: date) -> list[str]:
    """Checagens que não dependem do sources.json (também usadas no fallback do workflow)."""
    findings: list[str] = []
    if forecast.schema_version != SERIE_B_SCHEMA_VERSION:
        findings.append(f"schema_version {forecast.schema_version} != {SERIE_B_SCHEMA_VERSION}")
    if date.fromisoformat(forecast.reference_date) > today:
        findings.append(f"reference_date {forecast.reference_date} no futuro (hoje: {today})")
    n_clubs = len(forecast.teams)
    rules = forecast.rules
    playoff_slots = max(worse for _, worse in rules["playoff_groups"]) - int(rules["direct_promotion"])
    for metric, expected in (
        ("title", 1.0),
        ("promotion_direct", float(rules["direct_promotion"])),
        ("playoff", float(playoff_slots)),
        ("promotion_playoff", float(len(rules["playoff_groups"]))),
        ("relegation", float(rules["relegation"])),
    ):
        total = sum(getattr(team, metric) for team in forecast.teams)
        if not math.isclose(total, expected, abs_tol=1e-3):
            findings.append(f"soma de {metric} = {total:.4f}; esperado {expected}")
    matches_per_club = 2 * (n_clubs - 1)
    for team in forecast.teams:
        if len(team.position_probabilities) != n_clubs or not math.isclose(
            sum(team.position_probabilities), 1.0, abs_tol=TOLERANCE
        ):
            findings.append(f"{team.club_id}: posições não somam 1")
        if team.promotion > 1 + TOLERANCE or team.promotion_playoff > team.playoff + TOLERANCE:
            findings.append(f"{team.club_id}: acesso incoerente com playoff")
        findings.extend(_clinch_findings(team))
        if team.played + team.remaining != matches_per_club:
            findings.append(f"{team.club_id}: {team.played} jogos + {team.remaining} restantes != {matches_per_club}")
    played_total = sum(team.played for team in forecast.teams)
    if played_total != 2 * forecast.observed_matches:
        findings.append("jogos observados não batem com a tabela")
    if len(forecast.remaining) != forecast.remaining_matches:
        findings.append("jogos restantes sem probabilidade")
    return findings


def check_forecast(forecast: SerieBForecast, sources: dict[str, Any], today: date) -> list[str]:
    findings = check_forecast_core(forecast, today)
    reference_date = date.fromisoformat(forecast.reference_date)
    if reference_date != date.fromisoformat(str(sources["reference_date"])):
        findings.append("reference_date difere do sources.json")
    for item in sources["sources"]:
        status = LicenseStatus(item["license_status"])
        if (
            status not in PUBLISHABLE_LICENSE_STATUSES
            or AllowedUse.PUBLIC_DISPLAY_DERIVED.value not in item["allowed_uses"]
        ):
            findings.append(f"fonte {item['tag']} sem uso público")
        if not item.get("attribution"):
            findings.append(f"fonte {item['tag']} sem atribuição")
        current_season_source = str(item["version"]).startswith(f"{forecast.season}-")
        collected_on = datetime.fromisoformat(str(item["retrieved_at"])).astimezone(BRASILIA_TIMEZONE).date()
        if current_season_source and reference_date > collected_on:
            findings.append(f"reference_date {reference_date} posterior à coleta de {item['tag']} ({collected_on})")
    credited = {(source.source_name, source.version) for source in forecast.sources}
    for item in sources["sources"]:
        if (item["source_name"], item["version"]) not in credited:
            findings.append(f"fonte {item['tag']} usada e não creditada")
    return findings


def check_artifact(
    site_dir: Path, sources: dict[str, Any] | None, today: date, live_reference_date: date | None = None
) -> list[str]:
    """Sem `sources` (fallback do workflow, sem ingestão), só as checagens do próprio forecast."""
    forecast_path = site_dir / "data" / "forecast.json"
    if not forecast_path.exists():
        return [f"{forecast_path} ausente"]
    try:
        forecast = SerieBForecast.model_validate_json(forecast_path.read_text(encoding="utf-8"))
    except ValueError as error:
        return [f"forecast.json fora do esquema: {type(error).__name__}"]
    findings = check_forecast_core(forecast, today) if sources is None else check_forecast(forecast, sources, today)
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
        f"Série B {payload['season']} | referência {payload['reference_date']} | modelo {payload['model_version']} | "
        f"dados {payload['data_version']} | {payload['observed_matches']} jogos observados, "
        f"{payload['remaining_matches']} restantes | {payload['n_simulations']} simulações"
    )
