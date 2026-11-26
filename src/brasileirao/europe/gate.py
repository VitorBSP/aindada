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
from brasileirao.europe.knockout import KNOCKOUT_STAGES, NEXT_STAGE, TIES_PER_STAGE
from brasileirao.leagues.gate import HISTORY_FILE_NAME, check_history
from brasileirao.leagues.schema import CompetitionHistory
from brasileirao.ratings.examples import EXAMPLES_FILE_NAME, check_examples_file

TOLERANCE = 1e-6
STAGE_TOTALS = {"round_of_16": 16.0, "quarter_finals": 8.0, "semi_finals": 4.0, "final": 2.0, "winner": 1.0}
FORBIDDEN_DIRS = ("raw", "silver", "gold", "snapshots", "editorial")
ALLOWED_DATA_FILES = frozenset({"forecast.json", HISTORY_FILE_NAME, EXAMPLES_FILE_NAME})


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
    findings.extend(check_knockout(forecast))
    return findings


def _leg_findings(label: str, leg: Any) -> list[str]:
    findings = []
    scores = (leg.home_goals, leg.away_goals)
    odds = (leg.p_home, leg.p_draw, leg.p_away)
    if leg.status == "finished":
        if None in scores or any(value is not None for value in odds):
            findings.append(f"{label}: jogo encerrado sem placar ou com probabilidade")
    elif leg.status == "scheduled":
        if any(value is not None for value in scores) or leg.extra_time or leg.penalties:
            findings.append(f"{label}: jogo por disputar com placar")
        if None in odds or not math.isclose(sum(odds), 1.0, abs_tol=1e-6):
            findings.append(f"{label}: probabilidades do jogo não somam 1")
    else:
        findings.append(f"{label}: status {leg.status!r}")
    return findings


def check_knockout(forecast: ChampionsForecast) -> list[str]:
    """Mata-mata real: só com a fase de liga encerrada, confrontos no formato, placar só em jogo encerrado e a
    probabilidade de avanço igual à da fase seguinte na tabela fase a fase."""
    if forecast.phase == "league":
        return ["mata-mata publicado com a fase de liga em andamento"] if forecast.knockout else []
    if forecast.phase != "knockout":
        return [f"fase {forecast.phase!r} desconhecida"]
    findings = []
    if forecast.remaining_matches:
        findings.append("mata-mata com jogos da fase de liga por disputar")
    if forecast.current_stage not in KNOCKOUT_STAGES:
        findings.append(f"fase atual {forecast.current_stage!r} fora do mata-mata")
    clubs = {club.club_id: club for club in forecast.clubs}
    for stage in KNOCKOUT_STAGES:
        stage_ties = [tie for tie in forecast.knockout if tie.stage == stage]
        if len(stage_ties) > TIES_PER_STAGE[stage]:
            findings.append(f"{len(stage_ties)} confrontos em {stage}")
        for tie in stage_ties:
            label = f"{stage} {'x'.join(tie.club_ids)}"
            if len(tie.club_ids) != 2 or any(club not in clubs for club in tie.club_ids):
                findings.append(f"{label}: clubes fora da fase de liga")
                continue
            for leg in tie.legs:
                findings.extend(_leg_findings(f"{label} jogo {leg.leg}", leg))
            if not math.isclose(sum(tie.advance.values()), 1.0, abs_tol=1e-3):
                findings.append(f"{label}: probabilidades de avanço não somam 1")
            for club_id in tie.club_ids:
                reached = clubs[club_id].stages[NEXT_STAGE[stage]]
                if not math.isclose(tie.advance.get(club_id, -1.0), reached, abs_tol=TOLERANCE):
                    findings.append(f"{label}: avanço de {club_id} difere da tabela fase a fase")
            if tie.winner_id is not None and tie.advance.get(tie.winner_id) != 1.0:
                findings.append(f"{label}: confronto decidido sem avanço certo do vencedor")
    unknown = {tie.stage for tie in forecast.knockout} - set(KNOCKOUT_STAGES)
    if unknown:
        findings.append(f"fases desconhecidas no mata-mata: {sorted(unknown)}")
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
    history_path = site_dir / "data" / HISTORY_FILE_NAME
    if history_path.exists():
        try:
            history = CompetitionHistory.model_validate_json(history_path.read_text(encoding="utf-8"))
        except ValueError as error:
            findings.append(f"history.json fora do esquema: {type(error).__name__}")
        else:
            findings.extend(
                check_history(
                    history,
                    "champions-league",
                    forecast.reference_date,
                    {club.club_id for club in forecast.clubs},
                    {zone["zone_id"]: zone["last"] - zone["first"] + 1 for zone in forecast.zones},
                    forecast.model_version,
                    forecast.data_version,
                    today,
                    ends_at_reference=forecast.phase == "league",
                )
            )
    return findings


def summary_line(site_dir: Path) -> str:
    payload = json.loads((site_dir / "data" / "forecast.json").read_text(encoding="utf-8"))
    if payload.get("phase") == "knockout":
        ties = payload.get("knockout") or []
        decided = sum(tie["winner_id"] is not None for tie in ties)
        progress = f"mata-mata em {payload.get('current_stage')}, {decided} de {len(ties)} confrontos reais decididos"
    else:
        progress = (
            f"{payload['observed_matches']} jogos observados, {payload['remaining_matches']} restantes na fase de liga"
        )
    return (
        f"{payload['competition_name']} | referência {payload['reference_date']} | modelo {payload['model_version']} | "
        f"dados {payload['data_version']} | {progress} | {payload['n_simulations']} simulações"
    )
