"""Linha de comando do Mundial de LoL: `python -m brasileirao.esports.cli <comando>` (ADR-0013)."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from brasileirao.config import PATHS, SimulationConfig
from brasileirao.contracts import BRASILIA_TIMEZONE
from brasileirao.esports.forecast import (
    LOL_MODEL_VERSION,
    build_forecast,
    fetch_all,
    load_pins,
    load_series,
    params_from,
    tune,
)
from brasileirao.esports.gate import check_artifact, summary_line
from brasileirao.esports.sources import Series, load_teams
from brasileirao.logging_utils import configure_logging

MODEL_CONFIG = PATHS.gold / "lol_model_config.json"
TUNING_REPORT = PATHS.gold / "lol_tuning_report.json"
PARAM_KEYS = ("k_league", "k_team", "team_regression")


def _raw_dir() -> Path:
    return PATHS.esports_data / "raw"


def _inputs() -> tuple[dict[str, Any], list[Series], list[Series], list[dict[str, Any]]]:
    pins = load_pins(PATHS.lol_source_pins)
    every, current, sources = load_series(_raw_dir(), pins, load_teams(PATHS.lol_teams_reference))
    return pins, every, current, sources


def command_ingest(arguments: argparse.Namespace) -> None:
    if arguments.fetch:
        fetch_all(_raw_dir(), load_pins(PATHS.lol_source_pins))
    pins, every, current, _sources = _inputs()
    played = [item for item in current if item.played]
    print(f"{len(every)} séries; {pins['current_event']}: {len(played)} jogadas de {len(current)}")


def command_tune(_arguments: argparse.Namespace) -> None:
    pins, every, _, _ = _inputs()
    report = tune(every, pins, load_teams(PATHS.lol_teams_reference))
    TUNING_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MODEL_CONFIG.write_text(
        json.dumps({"model_version": LOL_MODEL_VERSION, **report["chosen"]}, indent=2) + "\n", encoding="utf-8"
    )
    test = report["test"]
    print(
        f"escolhido {report['chosen']}; teste: {test['maps']} mapas, log loss {test['map_log_loss']:.4f} "
        f"(moeda {test['coin_log_loss']:.4f}); série {test['series_log_loss']:.4f}"
    )


def command_forecast(arguments: argparse.Namespace) -> None:
    pins, every, current, sources = _inputs()
    config = json.loads(MODEL_CONFIG.read_text(encoding="utf-8"))
    report = json.loads(TUNING_REPORT.read_text(encoding="utf-8"))
    backtest = {key: report[key] for key in ("model_version", "validation_events", "validation", "test_event", "test")}
    forecast = build_forecast(
        every,
        current,
        sources,
        load_teams(PATHS.lol_teams_reference),
        params_from({key: config[key] for key in PARAM_KEYS}),
        arguments.simulations,
        arguments.seed,
        f"Mundial de League of Legends {pins['season']}",
        backtest,
    )
    target = PATHS.esports_data / "forecast" / "forecast.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(forecast.model_dump_json(indent=1) + "\n", encoding="utf-8")
    print(f"previsão em {target} ({forecast.n_simulations} simulações, semente {forecast.seed})")


def command_export_web(arguments: argparse.Namespace) -> None:
    target_dir = Path(arguments.target)
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PATHS.esports_data / "forecast" / "forecast.json", target_dir / "forecast.json")
    print(f"exportado em {target_dir / 'forecast.json'}")


def command_gate(arguments: argparse.Namespace) -> None:
    live = date.fromisoformat(arguments.live_reference_date) if arguments.live_reference_date else None
    site_dir = Path(arguments.site_dir)
    findings = check_artifact(site_dir, datetime.now(tz=UTC).astimezone(BRASILIA_TIMEZONE).date(), live)
    if findings:
        for finding in findings:
            print(f"REPROVADO: {finding}")
        raise SystemExit(1)
    print(f"{summary_line(site_dir)} | gate aprovado, 0 achados")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brasileirao-lol", description="Previsões do Mundial de LoL")
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="artigos da Wikipédia (revisões fixadas e a mais recente)")
    ingest.add_argument("--fetch", action="store_true")
    ingest.set_defaults(handler=command_ingest)
    commands.add_parser("tune", help="calibra o Elo liga + time").set_defaults(handler=command_tune)
    forecast = commands.add_parser("forecast", help="simula o restante do Mundial")
    forecast.add_argument("--simulations", type=int, default=SimulationConfig().n_simulations)
    forecast.add_argument("--seed", type=int, default=SimulationConfig().seed)
    forecast.set_defaults(handler=command_forecast)
    export = commands.add_parser("export-web", help="copia o forecast.json para a pasta do site")
    export.add_argument("--target", required=True)
    export.set_defaults(handler=command_export_web)
    gate = commands.add_parser("gate", help="checa o artefato antes do deploy")
    gate.add_argument("--site-dir", required=True)
    gate.add_argument("--live-reference-date", default=None)
    gate.set_defaults(handler=command_gate)
    return parser


def main(argv: list[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    configure_logging(logging.DEBUG if arguments.verbose else logging.INFO)
    arguments.handler(arguments)


if __name__ == "__main__":
    main()
