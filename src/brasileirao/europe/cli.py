"""Linha de comando da Champions League: `python -m brasileirao.europe.cli <comando>` (ADR-0012)."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import shutil
import time
import urllib.request
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from brasileirao.config import PATHS, SimulationConfig
from brasileirao.contracts import BRASILIA_TIMEZONE
from brasileirao.data_pipeline.clubs import load_club_registry
from brasileirao.europe.forecast import CHAMPIONS_MODEL_VERSION, build_forecast
from brasileirao.europe.gate import check_artifact, summary_line
from brasileirao.europe.ingest import compose, fetch_openfootball_files, load_europe_pins, read_silver, write_silver
from brasileirao.europe.ratings import GlobalEloParams
from brasileirao.europe.validation import TEST_SEASONS, match_report, season_backtest, tune
from brasileirao.leagues.sources import MIN_SECONDS_BETWEEN_CALLS, fetch_football_data
from brasileirao.logging_utils import configure_logging
from brasileirao.ratings.examples import (
    EXAMPLES_FILE_NAME,
    champions_examples,
    copy_examples,
    display_names,
    info_from_forecast,
    write_examples,
)

CODE = "champions-league"
MODEL_CONFIG = PATHS.gold / "champions_model_config.json"
TUNING_REPORT = PATHS.gold / "champions_tuning_report.json"


def _data_dir() -> Path:
    return PATHS.league_data(CODE)


def _countries() -> dict[str, str]:
    with PATHS.europe_clubs_reference.open(encoding="utf-8") as handle:
        return {row["club_id"]: row["country"] for row in csv.DictReader(handle)}


def _params() -> GlobalEloParams:
    if not MODEL_CONFIG.exists():
        raise SystemExit(f"{MODEL_CONFIG.name} ausente: rode o comando tune antes")
    return GlobalEloParams(**json.loads(MODEL_CONFIG.read_text(encoding="utf-8"))["elo"])


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "AIndaDa/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload: bytes = response.read()
    return payload


def backtest_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Resumo exibido no site: só agregados do teste, sem clubes nem jogos."""
    seasons = report["season_level"]
    late_matchday = max(record["matchday"] for record in seasons)
    late = [record for record in seasons if record["matchday"] == late_matchday]

    def mean(key: str) -> float:
        return float(sum(record[key] for record in late) / len(late))

    match_level = report["match_level"]
    return {
        "model_version": report["model_version"],
        "test_seasons": report["test_seasons"],
        "n_matches": int(match_level["elo_only"]["test"]["n_matches"]),
        "log_loss": float(match_level["elo_only"]["test"]["log_loss"]),
        "log_loss_base_rate": float(match_level["base_rate"]["test"]["log_loss"]),
        "late_matchday": late_matchday,
        "top8_brier": mean("top8_brier"),
        "top8_brier_base": mean("top8_brier_base"),
        "quarter_finals_brier": mean("quarter_finals_brier"),
        "quarter_finals_brier_base": mean("quarter_finals_brier_base"),
        "winner_log_loss": mean("winner_log_loss"),
        "winner_log_loss_uniform": mean("winner_log_loss_uniform"),
    }


def command_ingest(arguments: argparse.Namespace) -> None:
    pins = load_europe_pins(PATHS.europe_source_pins)
    raw_dir = _data_dir() / "raw"
    if arguments.fetch:
        fetch_openfootball_files(raw_dir, pins, _get)
        for position, code in enumerate(pins.football_data):
            if position:
                time.sleep(MIN_SECONDS_BETWEEN_CALLS)
            fetch_football_data(raw_dir, code, [pins.current_season])
    registry = load_club_registry(PATHS.europe_clubs_reference)
    composition = compose(raw_dir, pins, registry)
    write_silver(composition, _data_dir() / "silver")
    matches = composition.matches
    current_cl = matches[(matches["competition"] == "CL") & (matches["season"] == pins.current_season)]
    print(
        f"{len(matches)} jogos ({matches['competition'].nunique()} competições); Champions {pins.current_season}: "
        f"{int((current_cl['status'] == 'finished').sum())} de {len(current_cl)} encerrados; "
        f"referência {composition.reference_date}; W.O. fora: {composition.sources['awarded_skipped']}"
    )


def command_tune(arguments: argparse.Namespace) -> None:
    matches_data, _ = read_silver(_data_dir() / "silver")
    countries = _countries()
    params, records = tune(matches_data, countries)
    report = {
        "model_version": CHAMPIONS_MODEL_VERSION,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "protocol": "escolha na validação (2023/24), teste só relatado (2024/25 e 2025/26), ADR-0006",
        "test_seasons": list(TEST_SEASONS),
        "chosen": asdict(params),
        "candidates": records,
        "match_level": match_report(matches_data, countries, params),
        "season_level": season_backtest(matches_data, countries, params, n_simulations=arguments.simulations),
    }
    TUNING_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config = {"model_version": CHAMPIONS_MODEL_VERSION, "elo": asdict(params), "goal_dispersion": True}
    MODEL_CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    summary = backtest_summary(report)
    print(
        f"parâmetros {asdict(params)}; log loss no teste {summary['log_loss']:.4f} "
        f"(taxa base {summary['log_loss_base_rate']:.4f})"
    )


def command_forecast(arguments: argparse.Namespace) -> None:
    matches_data, sources = read_silver(_data_dir() / "silver")
    pins = load_europe_pins(PATHS.europe_source_pins)
    report = json.loads(TUNING_REPORT.read_text(encoding="utf-8")) if TUNING_REPORT.exists() else None
    registry = load_club_registry(PATHS.europe_clubs_reference)
    countries = _countries()
    params = _params()
    forecast = build_forecast(
        matches_data,
        sources,
        registry,
        countries,
        params,
        pins.current_season,
        arguments.simulations,
        arguments.seed,
        backtest=backtest_summary(report) if report else None,
    )
    target = _data_dir() / "forecast" / "forecast.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(forecast.model_dump_json(indent=1) + "\n", encoding="utf-8")
    print(f"previsão em {target} ({forecast.n_simulations} simulações, semente {forecast.seed})")
    examples_path = target.parent / EXAMPLES_FILE_NAME
    if write_examples(
        examples_path,
        lambda: champions_examples(
            info_from_forecast(CODE, forecast), matches_data, params, countries, display_names(registry)
        ),
    ):
        print(f"exemplos do Elo em {examples_path}")


def command_export_web(arguments: argparse.Namespace) -> None:
    target_dir = Path(arguments.target)
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_data_dir() / "forecast" / "forecast.json", target_dir / "forecast.json")
    print(f"exportado em {target_dir / 'forecast.json'}")
    if copy_examples(_data_dir() / "forecast", target_dir):
        print(f"exportado em {target_dir / EXAMPLES_FILE_NAME}")


def command_gate(arguments: argparse.Namespace) -> None:
    sources = None if arguments.standalone else read_silver(_data_dir() / "silver")[1]
    live = date.fromisoformat(arguments.live_reference_date) if arguments.live_reference_date else None
    site_dir = Path(arguments.site_dir)
    today = datetime.now(tz=UTC).astimezone(BRASILIA_TIMEZONE).date()
    findings = check_artifact(site_dir, sources, today, live)
    if findings:
        for finding in findings:
            print(f"REPROVADO: {finding}")
        raise SystemExit(1)
    print(f"{summary_line(site_dir)} | gate aprovado, 0 achados")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brasileirao-champions", description="Previsões da Champions League")
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="openfootball (fixado) + football-data.org → silver")
    ingest.add_argument("--fetch", action="store_true", help="baixa as fontes (FOOTBALL_DATA_ORG_TOKEN)")
    ingest.set_defaults(handler=command_ingest)

    tune_parser = commands.add_parser("tune", help="calibra o Elo (2023/24) e faz o backtest (2024/25 e 2025/26)")
    tune_parser.add_argument("--simulations", type=int, default=20_000)
    tune_parser.set_defaults(handler=command_tune)

    forecast = commands.add_parser("forecast", help="simula a fase de liga e o mata-mata")
    forecast.add_argument("--simulations", type=int, default=SimulationConfig().n_simulations)
    forecast.add_argument("--seed", type=int, default=SimulationConfig().seed)
    forecast.set_defaults(handler=command_forecast)

    export = commands.add_parser("export-web", help="copia o forecast.json para a pasta do site")
    export.add_argument("--target", required=True)
    export.set_defaults(handler=command_export_web)

    gate = commands.add_parser("gate", help="checa o artefato antes do deploy")
    gate.add_argument("--site-dir", required=True)
    gate.add_argument("--live-reference-date", default=None)
    gate.add_argument("--standalone", action="store_true", help="sem sources.json (fallback do workflow)")
    gate.set_defaults(handler=command_gate)
    return parser


def main(argv: list[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    configure_logging(logging.DEBUG if arguments.verbose else logging.INFO)
    arguments.handler(arguments)


if __name__ == "__main__":
    main()
