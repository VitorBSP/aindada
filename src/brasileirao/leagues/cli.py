"""Linha de comando das ligas europeias: `python -m brasileirao.leagues.cli <liga> <comando>` (ADR-0011)."""

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
from brasileirao.leagues.forecast import LEAGUE_MODEL_CONFIG, LEAGUE_MODEL_VERSION, build_forecast
from brasileirao.leagues.gate import check_artifact, summary_line
from brasileirao.leagues.ingest import LeaguePins, compose, load_league_pins, read_silver, write_silver
from brasileirao.leagues.rules import LeagueRules, load_league_rules
from brasileirao.leagues.sources import fetch_football_data, fetch_openfootball
from brasileirao.leagues.validation import backtest_summary, run_tuning
from brasileirao.logging_utils import configure_logging
from brasileirao.pipeline import ModelConfig, load_model_config

LEAGUES = ("premier-league", "la-liga")


def _pins(code: str) -> LeaguePins:
    return load_league_pins(PATHS.league_source_pins, code)


def _rules(pins: LeaguePins) -> LeagueRules:
    return load_league_rules(pins.code, pins.current_season)


def _tuning_report(code: str) -> Path:
    return PATHS.gold / f"league_tuning_report_{code}.json"


def _model_config(code: str) -> ModelConfig:
    file_name = LEAGUE_MODEL_CONFIG.format(code=code)
    if not (PATHS.gold / file_name).exists():
        raise SystemExit(f"{file_name} ausente: rode `tune` antes")
    return load_model_config(PATHS.gold, file_name)


def command_ingest(arguments: argparse.Namespace) -> None:
    pins = _pins(arguments.league)
    rules = _rules(pins)
    raw_dir = PATHS.league_data(pins.code) / "raw"
    if arguments.fetch:
        fetch_openfootball(
            raw_dir,
            pins.openfootball_repo,
            pins.openfootball_path,
            pins.openfootball_commit,
            list(pins.history_seasons),
            pins.openfootball_sha256,
        )
        seasons = [*pins.conference_seasons, pins.current_season] if arguments.conference else [pins.current_season]
        fetch_football_data(raw_dir, pins.football_data_code, seasons)
    registry = load_club_registry(PATHS.reference / pins.clubs_file)
    composition = compose(raw_dir, pins, registry, rules.timezone)
    write_silver(composition, PATHS.league_data(pins.code) / "silver")
    current = composition.matches[composition.matches["season"] == pins.current_season]
    print(
        f"{pins.code}: {len(composition.matches)} jogos em {composition.matches['season'].nunique()} temporadas; "
        f"{pins.current_season}: {int((current['status'] == 'finished').sum())} encerrados; "
        f"referência {composition.reference_date}"
    )
    for result in composition.sources["conference"]:
        print(
            f"conferência {result['season']}: {result['matched']} jogos iguais em data e placar, "
            f"{result['only_one_source']} só numa fonte"
        )


def command_tune(arguments: argparse.Namespace) -> None:
    pins = _pins(arguments.league)
    matches_data, _ = read_silver(PATHS.league_data(pins.code) / "silver")
    report = run_tuning(
        matches_data,
        _rules(pins),
        load_model_config(),
        pins.history_seasons[0],
        LEAGUE_MODEL_VERSION,
        n_simulations=arguments.simulations,
    )
    _tuning_report(pins.code).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PATHS.gold / LEAGUE_MODEL_CONFIG.format(code=pins.code)).write_text(
        json.dumps(report["model_config"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = backtest_summary(report)
    print(
        f"{pins.code}: ratings {report['chosen_rating_params']}, incerteza {report['chosen_uncertainty']}; "
        f"log loss no teste {summary['log_loss']:.4f} (taxa base {summary['log_loss_base_rate']:.4f})"
    )


def command_forecast(arguments: argparse.Namespace) -> None:
    pins = _pins(arguments.league)
    matches_data, sources = read_silver(PATHS.league_data(pins.code) / "silver")
    report_path = _tuning_report(pins.code)
    summary = backtest_summary(json.loads(report_path.read_text(encoding="utf-8"))) if report_path.exists() else None
    forecast = build_forecast(
        matches_data,
        sources,
        _rules(pins),
        load_club_registry(PATHS.reference / pins.clubs_file),
        _model_config(pins.code),
        arguments.simulations,
        arguments.seed,
        pins.history_seasons[0],
        backtest_summary=summary,
    )
    target = PATHS.league_data(pins.code) / "forecast" / "forecast.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(forecast.model_dump_json(indent=1) + "\n", encoding="utf-8")
    print(f"{pins.code}: previsão em {target} ({forecast.n_simulations} simulações, semente {forecast.seed})")


def command_export_web(arguments: argparse.Namespace) -> None:
    target_dir = Path(arguments.target)
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PATHS.league_data(arguments.league) / "forecast" / "forecast.json", target_dir / "forecast.json")
    print(f"exportado em {target_dir / 'forecast.json'}")


def command_gate(arguments: argparse.Namespace) -> None:
    sources = None if arguments.standalone else read_silver(PATHS.league_data(arguments.league) / "silver")[1]
    live = date.fromisoformat(arguments.live_reference_date) if arguments.live_reference_date else None
    site_dir = Path(arguments.site_dir)
    today = datetime.now(tz=UTC).astimezone(BRASILIA_TIMEZONE).date()
    findings = check_artifact(site_dir, sources, today, arguments.league, live)
    if findings:
        for finding in findings:
            print(f"REPROVADO: {finding}")
        raise SystemExit(1)
    print(f"{summary_line(site_dir)} | gate aprovado, 0 achados")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brasileirao-ligas", description="Previsões das ligas europeias")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("league", choices=LEAGUES)
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="openfootball (fixado) + football-data.org → silver")
    ingest.add_argument("--fetch", action="store_true", help="baixa as fontes (FOOTBALL_DATA_ORG_TOKEN)")
    ingest.add_argument("--conference", action="store_true", help="baixa e confere também as temporadas em comum")
    ingest.set_defaults(handler=command_ingest)

    tune = commands.add_parser("tune", help="calibração na validação e backtest no teste")
    tune.add_argument("--simulations", type=int, default=2000)
    tune.set_defaults(handler=command_tune)

    forecast = commands.add_parser("forecast", help="simula o restante da temporada")
    forecast.add_argument("--simulations", type=int, default=SimulationConfig().n_simulations)
    forecast.add_argument("--seed", type=int, default=SimulationConfig().seed)
    forecast.set_defaults(handler=command_forecast)

    export = commands.add_parser("export-web", help="copia o forecast.json para a pasta do site")
    export.add_argument("--target", required=True)
    export.set_defaults(handler=command_export_web)

    gate = commands.add_parser("gate", help="checa o artefato da liga antes do deploy")
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
