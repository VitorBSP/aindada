"""Gate do artefato de uma liga europeia antes do deploy (ADR-0011, Decisão 5). Saída só com ids e contagens."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

from brasileirao.contracts import BRASILIA_TIMEZONE, PUBLISHABLE_LICENSE_STATUSES, AllowedUse, LicenseStatus
from brasileirao.leagues.schema import HISTORY_SCHEMA_VERSION, LEAGUE_SCHEMA_VERSION, CompetitionHistory, LeagueForecast
from brasileirao.ratings.examples import EXAMPLES_FILE_NAME, check_examples_file

TOLERANCE = 1e-6
FORBIDDEN_DIRS = ("raw", "silver", "gold", "snapshots", "editorial")
HISTORY_FILE_NAME = "history.json"
ALLOWED_DATA_FILES = frozenset({"forecast.json", HISTORY_FILE_NAME, EXAMPLES_FILE_NAME})
HISTORY_TOLERANCE = 5e-3


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


def check_history(
    history: CompetitionHistory,
    competition: str,
    reference_date: str,
    club_ids: set[str],
    zone_sizes: dict[str, int],
    model_version: str,
    data_version: str,
    today: date,
    ends_at_reference: bool = True,
) -> list[str]:
    """Contrato do `history.json`: a evolução precisa fechar com a edição publicada e marcar o que é reconstrução."""
    findings: list[str] = []
    if history.schema_version != HISTORY_SCHEMA_VERSION:
        findings.append(f"history: schema_version {history.schema_version} != {HISTORY_SCHEMA_VERSION}")
    if history.competition != competition:
        findings.append(f"history de {history.competition} publicado em /{competition}/")
    if (history.model_version, history.data_version) != (model_version, data_version):
        findings.append("history: modelo ou dados diferentes do forecast.json")
    if not history.points:
        return [*findings, "history sem nenhum ponto"]
    dates = [point.reference_date for point in history.points]
    if dates != sorted(set(dates)):
        findings.append("history: datas fora de ordem ou repetidas")
    if date.fromisoformat(dates[-1]) > today:
        findings.append(f"history: ponto de {dates[-1]} no futuro (hoje: {today})")
    if ends_at_reference and dates[-1] != reference_date:
        findings.append(f"history termina em {dates[-1]}; a edição é de {reference_date}")
    if not ends_at_reference and dates[-1] > reference_date:
        findings.append(f"history termina em {dates[-1]}, depois da edição de {reference_date}")
    reconstructed = [point.reconstructed for point in history.points]
    if (history.history_mode == "reconstructed") != any(reconstructed):
        findings.append("history: history_mode não bate com os pontos reconstruídos")
    if not all(reconstructed[:-1]):
        findings.append("history: ponto anterior à edição sem a marca reconstructed (R18)")
    previous_observed = 0
    for point in history.points:
        label = f"history {point.reference_date}"
        if point.observed_matches < previous_observed:
            findings.append(f"{label}: jogos observados diminuíram")
        previous_observed = point.observed_matches
        if set(point.teams) != club_ids:
            findings.append(f"{label}: clubes diferentes dos da previsão")
            continue
        if sorted(team.position for team in point.teams.values()) != list(range(1, len(club_ids) + 1)):
            findings.append(f"{label}: posições não são 1 a {len(club_ids)}")
        for zone_id, size in zone_sizes.items():
            values = [team.zones.get(zone_id, -1.0) for team in point.teams.values()]
            if any(value < 0 or value > 1 for value in values):
                findings.append(f"{label}: zona {zone_id} com probabilidade fora de 0 a 1")
            elif not math.isclose(sum(values), size, abs_tol=HISTORY_TOLERANCE * len(values)):
                findings.append(f"{label}: soma da zona {zone_id} = {sum(values):.3f}; esperado {size}")
        winners = [team.stages["winner"] for team in point.teams.values() if team.stages and "winner" in team.stages]
        if winners and not math.isclose(sum(winners), 1.0, abs_tol=HISTORY_TOLERANCE * len(winners)):
            findings.append(f"{label}: chances de título somam {sum(winners):.3f}")
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
    extra = sorted(path.name for path in (site_dir / "data").iterdir() if path.name not in ALLOWED_DATA_FILES)
    if extra:
        findings.append(f"arquivos inesperados em data/: {extra}")
    findings.extend(check_examples_file(site_dir / "data" / EXAMPLES_FILE_NAME, competition, forecast.reference_date))
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
                    competition,
                    forecast.reference_date,
                    {team.club_id for team in forecast.teams},
                    {zone.zone_id: zone.last - zone.first + 1 for zone in forecast.zones},
                    forecast.model_version,
                    forecast.data_version,
                    today,
                )
            )
    return findings


def summary_line(site_dir: Path) -> str:
    payload = json.loads((site_dir / "data" / "forecast.json").read_text(encoding="utf-8"))
    return (
        f"{payload['competition_name']} | referência {payload['reference_date']} | modelo {payload['model_version']} | "
        f"dados {payload['data_version']} | {payload['observed_matches']} jogos observados, "
        f"{payload['remaining_matches']} restantes | {payload['n_simulations']} simulações"
    )
