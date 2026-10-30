"""Gate do artefato do Mundial de LoL antes do deploy (ADR-0013). Saída só com ids e contagens."""

from __future__ import annotations

import itertools
import json
import math
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from brasileirao.esports.forecast import LOL_SCHEMA_VERSION, RIOT_NOTICE, LolForecast

TOLERANCE = 1e-6
STAGE_TOTALS = {"qualify": 8.0, "semifinal": 4.0, "final": 2.0, "champion": 1.0}


def check_forecast(forecast: LolForecast, today: date) -> list[str]:
    findings: list[str] = []
    if forecast.schema_version != LOL_SCHEMA_VERSION:
        findings.append(f"schema_version {forecast.schema_version} != {LOL_SCHEMA_VERSION}")
    if date.fromisoformat(forecast.reference_date) > today:
        findings.append(f"reference_date {forecast.reference_date} no futuro (hoje: {today})")
    if forecast.notice != RIOT_NOTICE:
        findings.append("aviso da política de fãs da Riot ausente ou alterado")
    if forecast.backtest is not None and forecast.backtest.get("model_version") != forecast.model_version:
        findings.append("backtest de outra versão do modelo")
    if forecast.n_simulations <= 0:
        findings.append("n_simulations deve ser positivo")
    team_ids = {team.team_id for team in forecast.teams}
    for stage, expected in STAGE_TOTALS.items():
        total = sum(team.stages[stage] for team in forecast.teams)
        if not math.isclose(total, expected, abs_tol=1e-3):
            findings.append(f"soma de {stage} = {total:.4f}; esperado {expected}")
    stages = list(STAGE_TOTALS)
    for team in forecast.teams:
        if any(not 0.0 <= value <= 1.0 for value in team.stages.values()):
            findings.append(f"{team.team_id}: probabilidade fora de [0, 1]")
        for earlier, later in itertools.pairwise(stages):
            if team.stages[later] > team.stages[earlier] + TOLERANCE:
                findings.append(f"{team.team_id}: chance de {later} maior que a de {earlier}")
        if team.status == "eliminated" and team.stages["qualify"] > 0:
            findings.append(f"{team.team_id}: eliminado com chance de classificação")
        if team.status == "qualified" and team.stages["qualify"] < 1 - TOLERANCE:
            findings.append(f"{team.team_id}: classificado sem chance 100%")
    for series in forecast.upcoming:
        if not 0.0 <= series.p_team1 <= 1.0:
            findings.append(f"{series.label}: probabilidade fora de [0, 1]")
        if not {series.team1, series.team2} <= team_ids:
            findings.append(f"{series.label}: time fora da lista de times")
    for source in forecast.sources:
        if not source.get("attribution") or source.get("license_name") != "CC BY-SA 4.0":
            findings.append(f"fonte {source.get('version')} sem licença ou atribuição")
    return findings


def check_artifact(site_dir: Path, today: date, live_reference_date: date | None = None) -> list[str]:
    forecast_path = site_dir / "data" / "forecast.json"
    if not forecast_path.exists():
        return [f"{forecast_path} ausente"]
    try:
        forecast = LolForecast.model_validate_json(forecast_path.read_text(encoding="utf-8"))
    except ValidationError as error:
        return [f"forecast.json fora do esquema: {error.error_count()} erros"]
    findings = check_forecast(forecast, today)
    for required in ("index.html", "app.js", "styles.css"):
        if not (site_dir / required).exists():
            findings.append(f"{required} ausente no artefato")
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
        f"dados {payload['data_version']} | {payload['n_simulations']} simulações"
    )
