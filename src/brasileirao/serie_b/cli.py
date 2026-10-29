"""Linha de comando da Série B: `python -m brasileirao.serie_b.cli <comando>` (ADR-0010)."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from brasileirao.config import PATHS, SimulationConfig
from brasileirao.contracts import BRASILIA_TIMEZONE
from brasileirao.data_pipeline.clubs import load_club_registry
from brasileirao.logging_utils import configure_logging, get_logger
from brasileirao.pipeline import ModelConfig, load_model_config
from brasileirao.serie_b.backtest import backtest_summary, run_backtest
from brasileirao.serie_b.forecast import SERIE_B_MODEL_CONFIG, SERIE_B_MODEL_VERSION, build_forecast
from brasileirao.serie_b.gate import check_artifact, summary_line
from brasileirao.serie_b.ingest import compose, load_pins, read_silver, write_silver
from brasileirao.serie_b.rules import load_serie_b_rules
from brasileirao.serie_b.sources import fetch_openfootball, fetch_wikipedia
from brasileirao.serie_b.tuning import run_tuning

LOGGER = get_logger(__name__)
BACKTEST_REPORT = PATHS.gold / "serie_b_backtest_report.json"
TUNING_REPORT = PATHS.gold / "serie_b_tuning_report.json"


def _model_config() -> ModelConfig:
    if not (PATHS.gold / SERIE_B_MODEL_CONFIG).exists():
        raise SystemExit(f"{SERIE_B_MODEL_CONFIG} ausente: rode `tune` antes")
    return load_model_config(PATHS.gold, SERIE_B_MODEL_CONFIG)


def _raw_dir() -> Path:
    return PATHS.serie_b_data / "raw"


def _silver_dir() -> Path:
    return PATHS.serie_b_data / "silver"


def _forecast_path() -> Path:
    return PATHS.serie_b_data / "forecast" / "forecast.json"


def command_ingest(arguments: argparse.Namespace) -> None:
    pins = load_pins(PATHS.serie_b_source_pins)
    if arguments.fetch:
        fetch_openfootball(
            _raw_dir(), pins.openfootball_commit, list(pins.openfootball_seasons), pins.openfootball_sha256
        )
        for season, revision_id in pins.wikipedia_closed_seasons.items():
            fetch_wikipedia(_raw_dir(), season, revision_id)
        fetch_wikipedia(_raw_dir(), pins.current_season)
    composition = compose(_raw_dir(), pins, load_club_registry(PATHS.serie_b_clubs_reference))
    write_silver(composition, _silver_dir())
    matches = composition.matches
    current = matches[matches["season"] == pins.current_season]
    print(
        f"{len(matches)} jogos em {matches['season'].nunique()} temporadas; {pins.current_season}: "
        f"{int((current['status'] == 'finished').sum())} encerrados, {int((current['status'] != 'finished').sum())} "
        f"sem placar; referência {composition.reference_date}"
    )
    for conference in composition.sources["schedule_conference"]:
        print(f"conferência {conference['season']}: {conference['compared']} placares comparados, 0 divergências")
    print(f"conferência {pins.current_season}: matriz e classificação da Wikipédia coincidem")


def command_backtest(arguments: argparse.Namespace) -> None:
    matches_data, _ = read_silver(_silver_dir())
    report = run_backtest(
        matches_data, load_serie_b_rules(arguments.season), _model_config(), n_simulations=arguments.simulations
    )
    BACKTEST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    BACKTEST_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = backtest_summary(report)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def command_tune(arguments: argparse.Namespace) -> None:
    matches_data, _ = read_silver(_silver_dir())
    report = run_tuning(
        matches_data, load_serie_b_rules(arguments.season), load_model_config(), n_simulations=arguments.simulations
    )
    TUNING_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config = {"model_version": SERIE_B_MODEL_VERSION, **report["model_config"]}
    (PATHS.gold / SERIE_B_MODEL_CONFIG).write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"ratings: {report['chosen_rating_params']}; incerteza: {report['chosen_uncertainty']}; "
        f"config em {PATHS.gold / SERIE_B_MODEL_CONFIG}"
    )


def command_forecast(arguments: argparse.Namespace) -> None:
    matches_data, sources = read_silver(_silver_dir())
    summary = None
    if BACKTEST_REPORT.exists():
        summary = backtest_summary(json.loads(BACKTEST_REPORT.read_text(encoding="utf-8")))
    forecast = build_forecast(
        matches_data,
        sources,
        load_serie_b_rules(arguments.season),
        load_club_registry(PATHS.serie_b_clubs_reference),
        _model_config(),
        arguments.simulations,
        arguments.seed,
        summary,
    )
    target = _forecast_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(forecast.model_dump_json(indent=1) + "\n", encoding="utf-8")
    print(f"previsão gravada em {target} ({forecast.n_simulations} simulações, semente {forecast.seed})")


def command_export_web(arguments: argparse.Namespace) -> None:
    target_dir = Path(arguments.target) if arguments.target else PATHS.serie_b_web_static_data
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_forecast_path(), target_dir / "forecast.json")
    print(f"exportado em {target_dir / 'forecast.json'}")


def command_gate(arguments: argparse.Namespace) -> None:
    sources = None if arguments.standalone else read_silver(_silver_dir())[1]
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
    parser = argparse.ArgumentParser(prog="brasileirao-serie-b", description="Previsões da Série B")
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="openfootball (fixado) + Wikipédia → silver da Série B")
    ingest.add_argument("--fetch", action="store_true", help="baixa as fontes; sem ela, usa o raw existente")
    ingest.set_defaults(handler=command_ingest)

    tune = commands.add_parser("tune", help="calibra os hiperparâmetros na Série B (validação 2020–2022)")
    tune.add_argument("--season", type=int, default=2026)
    tune.add_argument("--simulations", type=int, default=2000)
    tune.set_defaults(handler=command_tune)

    backtest = commands.add_parser("backtest", help="backtesting temporal 2023–2025")
    backtest.add_argument("--season", type=int, default=2026)
    backtest.add_argument("--simulations", type=int, default=2000)
    backtest.set_defaults(handler=command_backtest)

    forecast = commands.add_parser("forecast", help="simula o restante da temporada e os playoffs")
    forecast.add_argument("--season", type=int, default=2026)
    forecast.add_argument("--simulations", type=int, default=SimulationConfig().n_simulations)
    forecast.add_argument("--seed", type=int, default=SimulationConfig().seed)
    forecast.set_defaults(handler=command_forecast)

    export = commands.add_parser("export-web", help="copia o forecast.json para apps/web-serie-b/data")
    export.add_argument("--target", default=None)
    export.set_defaults(handler=command_export_web)

    gate = commands.add_parser("gate", help="checa o artefato da Série B antes do deploy")
    gate.add_argument("--site-dir", default=str(PATHS.root / "apps" / "web-serie-b"))
    gate.add_argument("--live-reference-date", default=None)
    gate.add_argument(
        "--standalone", action="store_true", help="sem sources.json: só o forecast (fallback do workflow)"
    )
    gate.set_defaults(handler=command_gate)
    return parser


def main(argv: list[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    configure_logging(logging.DEBUG if arguments.verbose else logging.INFO)
    arguments.handler(arguments)


if __name__ == "__main__":
    main()
