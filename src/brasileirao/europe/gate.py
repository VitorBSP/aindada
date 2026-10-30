"""Gate do artefato da Champions League antes do deploy (ADR-0012). Saída só com ids e contagens."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from brasileirao.contracts import BRASILIA_TIMEZONE, PUBLISHABLE_LICENSE_STATUSES, AllowedUse, LicenseStatus
from brasileirao.europe.forecast import CHAMPIONS_SCHEMA_VERSION, ChampionsForecast
from brasileirao.ratings.examples import EXAMPLES_FILE_NAME, check_examples_file

TOLERANCE = 1e-6
STAGE_TOTALS = {"round_of_16": 16.0, "quarter_finals": 8.0, "semi_finals": 4.0, "final": 2.0, "winner": 1.0}
FORBIDDEN_DIRS = ("raw", "silver", "gold", "snapshots", "editorial")
ALLOWED_DATA_FILES = frozenset({"forecast.json", EXAMPLES_FILE_NAME})


def check_forecast_core(forecast: ChampionsForecast, today: date) -> list[str]:
    findings: list[str] = []
    if forecast.schema_version != CHAMPIONS_SCHEMA_VERSION:
        findings.append(f"schema_version {forecast.schema_version} != {CHAMPIONS_SCHEMA_VERSION}")
    if date.fromisoformat(forecast.reference_date) > today:
        findings.append(f"reference_date {forecast.reference_date} no futuro (hoje: {today})")
    if forecast.backtest is not None and forecast.backtest.get("model_version") != forecast.model_version:
        findings.append(f"backtest de {forecast.backtest.get('model_version')} exibido com {forecast.model_version}")
    if len(forecast.clubs) != 36:
        findings.append(f"{len(forecast.clubs)} clubes; esperado 36")
    for zone in forecast.zones:
        total = sum(club.zones[zone["zone_id"]] for club in forecast.clubs)
        expected = zone["last"] - zone["first"] + 1
        if not math.isclose(total, expected, abs_tol=1e-3):
            findings.append(f"soma da zona {zone['zone_id']} = {total:.4f}; esperado {expected}")
    for stage, expected in STAGE_TOTALS.items():
        total = sum(club.stages[stage] for club in forecast.clubs)
        if not math.isclose(total, expected, abs_tol=1e-3):
            findings.append(f"soma da fase {stage} = {total:.4f}; esperado {expected}")
    stages = list(STAGE_TOTALS)
    for club in forecast.clubs:
        if not math.isclose(sum(club.position_probabilities), 1.0, abs_tol=TOLERANCE):
            findings.append(f"{club.club_id}: posições não somam 1")
        for earlier, later in pairwise(stages):
            if club.stages[later] > club.stages[earlier] + TOLERANCE:
                findings.append(f"{club.club_id}: chance de {later} maior que a de {earlier}")
        for zone_id, state in club.clinched.items():
            probability = club.zones[zone_id]
            if (state == "in" and probability < 1 - TOLERANCE) or (state == "out" and probability > TOLERANCE):
                findings.append(f"{club.club_id}: zona {zone_id} '{state}' pela aritmética e contrariada na simulação")
    if sum(club.played for club in forecast.clubs) != 2 * forecast.observed_matches:
        findings.append("jogos observados não batem com a tabela")
    if forecast.observed_matches + forecast.remaining_matches != 144:
        findings.append("fase de liga não tem 144 jogos")
    if len(forecast.remaining) != forecast.remaining_matches:
        findings.append("jogos restantes sem probabilidade")
    return findings


def check_forecast(forecast: ChampionsForecast, sources: dict[str, Any], today: date) -> list[str]:
    findings = check_forecast_core(forecast, today)
    reference_date = date.fromisoformat(forecast.reference_date)
    if reference_date != date.fromisoformat(str(sources["reference_date"])):
        findings.append("reference_date difere do sources.json")
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
    site_dir: Path, sources: dict[str, Any] | None, today: date, live_reference_date: date | None = None
) -> list[str]:
    forecast_path = site_dir / "data" / "forecast.json"
    if not forecast_path.exists():
        return [f"{forecast_path} ausente"]
    try:
        forecast = ChampionsForecast.model_validate_json(forecast_path.read_text(encoding="utf-8"))
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
    extra = sorted(path.name for path in (site_dir / "data").iterdir() if path.name not in ALLOWED_DATA_FILES)
    if extra:
        findings.append(f"arquivos inesperados em data/: {extra}")
    findings.extend(
        check_examples_file(site_dir / "data" / EXAMPLES_FILE_NAME, "champions-league", forecast.reference_date)
    )
    return findings


def summary_line(site_dir: Path) -> str:
    payload = json.loads((site_dir / "data" / "forecast.json").read_text(encoding="utf-8"))
    return (
        f"{payload['competition_name']} | referência {payload['reference_date']} | modelo {payload['model_version']} | "
        f"dados {payload['data_version']} | {payload['observed_matches']} jogos observados, "
        f"{payload['remaining_matches']} restantes na fase de liga | {payload['n_simulations']} simulações"
    )
