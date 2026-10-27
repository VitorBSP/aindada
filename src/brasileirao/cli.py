"""Linha de comando: `python -m brasileirao.cli <comando>`."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

from brasileirao.competition_rules.season_rules import load_season_rules
from brasileirao.config import PATHS
from brasileirao.data_pipeline.clubs import load_club_registry
from brasileirao.data_pipeline.ingest import ingest_raw, read_matches, write_gold, write_silver
from brasileirao.data_pipeline.sources import BrasileiraoDatasetSource
from brasileirao.data_pipeline.validation import load_known_exceptions, run_quality_checks
from brasileirao.insights.criteria import load_criteria
from brasileirao.insights.editorial import (
    EditorialError,
    EditorialStore,
    export_published,
    publish_latest,
    review_candidate,
)
from brasileirao.insights.generator import generate
from brasileirao.logging_utils import configure_logging, get_logger
from brasileirao.pipeline import export_static_api, run_round_review, run_season_snapshots
from brasileirao.storage.snapshots import SnapshotStore
from brasileirao.validation.report import run_backtest_report

LOGGER = get_logger("brasileirao.cli")
DEFAULT_CHECKOUT = PATHS.raw / "_sources" / "brasileirao-dataset"


def command_ingest(arguments: argparse.Namespace) -> None:
    source = BrasileiraoDatasetSource(Path(arguments.checkout))
    snapshot = source.fetch(arguments.revision) if arguments.fetch else source.snapshot_from_checkout()
    raw_dir = ingest_raw(snapshot, PATHS.raw)
    registry = load_club_registry()
    write_silver(raw_dir, registry, PATHS.silver)
    write_gold(PATHS.silver, PATHS.gold)
    print(f"ingestão concluída: {raw_dir}")


def command_validate(arguments: argparse.Namespace) -> None:
    matches_data = read_matches(PATHS.gold / "matches_model.csv")
    reference = (
        date.fromisoformat(arguments.reference_date) if arguments.reference_date else datetime.now(tz=UTC).date()
    )
    report = run_quality_checks(
        matches_data, reference, load_known_exceptions(PATHS.reference / "known_exceptions.csv")
    )
    (PATHS.gold / "quality_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    for issue in report.issues:
        print(f"[{issue.severity}] {issue.season} {issue.code}: {issue.detail}")
    print(f"temporadas: {len(report.seasons)} | erros: {report.has_errors}")
    if report.has_errors:
        raise SystemExit(1)


def command_backtest(arguments: argparse.Namespace) -> None:
    matches_data = read_matches(PATHS.gold / "matches_model.csv")
    report = run_backtest_report(
        matches_data, load_season_rules(arguments.rules_season), PATHS.gold, n_simulations=arguments.simulations
    )
    print(json.dumps({key: report[key] for key in ("chosen_feature_set", "validation_log_loss")}, indent=2))


def command_simulate(arguments: argparse.Namespace) -> None:
    reference = date.fromisoformat(arguments.reference_date) if arguments.reference_date else None
    store = SnapshotStore(PATHS.snapshots_db)
    saved = run_season_snapshots(
        arguments.season,
        arguments.simulations,
        arguments.seed,
        reference,
        arguments.history_from_round,
        arguments.history_simulations,
        store,
    )
    print(f"snapshots salvos: {saved}")
    export_static_api(store, arguments.season)


def command_review_rounds(arguments: argparse.Namespace) -> None:
    store = SnapshotStore(PATHS.snapshots_db)
    review = run_round_review(arguments.season, arguments.simulations, arguments.seed, store)
    print(f"revisão salva: {len(review.rounds)} visões (rodadas 0 a {review.rounds[-1].round_number})")
    export_static_api(store, arguments.season)


def command_export_web(arguments: argparse.Namespace) -> None:
    for path in export_static_api(SnapshotStore(PATHS.snapshots_db), arguments.season):
        print(f"exportado: {path}")


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def command_insights_generate(arguments: argparse.Namespace) -> None:
    editorial = EditorialStore(PATHS.editorial, arguments.season)
    batch, gate_reviews = generate(
        SnapshotStore(PATHS.snapshots_db), editorial, arguments.season, load_criteria(), _now()
    )
    rejected = {review.insight_id: review.reason for review in gate_reviews}
    print(f"lote {batch.batch_id}: {len(batch.candidates)} candidato(s), {len(rejected)} reprovado(s) nos portões")
    for candidate in batch.candidates:
        state = f"REPROVADO ({rejected[candidate.insight_id]})" if candidate.insight_id in rejected else "candidato"
        print(f"- {candidate.insight_id} [{candidate.rule_id}] {state} · nota {candidate.relevance.score:.2f}")
        print(f"  {candidate.headline}\n  {candidate.body}")


def command_insights_list(arguments: argparse.Namespace) -> None:
    editorial = EditorialStore(PATHS.editorial, arguments.season)
    batch = editorial.latest_batch()
    if batch is None:
        print("nenhum lote gerado; rode insights-generate")
        return
    print(f"lote {batch.batch_id} (dados até {batch.snapshot_ref.reference_date})")
    for candidate in batch.candidates:
        review = editorial.latest_review(candidate.insight_id, candidate.insight_version)
        state = "aguardando revisão" if review is None else f"{review.decision} por {review.editor}: {review.reason}"
        print(f"- {candidate.insight_id} [{candidate.rule_id}] {state}\n  {candidate.headline}")


def command_insights_review(arguments: argparse.Namespace) -> None:
    editorial = EditorialStore(PATHS.editorial, arguments.season)
    batch = editorial.latest_batch()
    if batch is None:
        raise SystemExit("nenhum lote gerado; rode insights-generate")
    try:
        review = review_candidate(
            editorial,
            batch,
            arguments.insight_id,
            arguments.decision,
            arguments.reason,
            arguments.editor,
            _now(),
            failed_checks=set(arguments.fail),
            placement=arguments.placement,
            priority=arguments.priority,
            edited_headline=arguments.headline,
            edited_body=arguments.body,
        )
    except (EditorialError, ValueError) as error:
        raise SystemExit(f"revisão recusada: {error}") from error
    print(f"{review.insight_id}: {review.decision} ({review.reason})")


def command_insights_publish(arguments: argparse.Namespace) -> None:
    editorial = EditorialStore(PATHS.editorial, arguments.season)
    try:
        active = publish_latest(editorial, _now())
    except EditorialError as error:
        raise SystemExit(str(error)) from error
    target = export_published(editorial.published(), PATHS.web_static_data, arguments.season)
    print(f"{len(active)} insight(s) no ar; exportado em {target}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brasileirao", description="Previsões da Série A")
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="ingestão raw → silver → gold")
    ingest.add_argument("--checkout", default=str(DEFAULT_CHECKOUT), help="clone local do brasileirao-dataset")
    ingest.add_argument("--fetch", action="store_true", help="clona/atualiza o repositório antes")
    ingest.add_argument("--revision", default=None, help="commit específico (reprodutibilidade)")
    ingest.set_defaults(handler=command_ingest)

    validate = commands.add_parser("validate", help="checagens de integridade")
    validate.add_argument("--reference-date", default=None)
    validate.set_defaults(handler=command_validate)

    backtest = commands.add_parser("backtest", help="ajuste de hiperparâmetros e backtesting temporal")
    backtest.add_argument("--rules-season", type=int, default=2026)
    backtest.add_argument("--simulations", type=int, default=2000)
    backtest.set_defaults(handler=command_backtest)

    simulate = commands.add_parser("simulate", help="gera snapshots de previsão")
    simulate.add_argument("--season", type=int, default=2026)
    simulate.add_argument("--simulations", type=int, default=10_000)
    simulate.add_argument("--seed", type=int, default=2026)
    simulate.add_argument("--reference-date", default=None)
    simulate.add_argument("--history-from-round", type=int, default=None)
    simulate.add_argument("--history-simulations", type=int, default=2000)
    simulate.set_defaults(handler=command_simulate)

    review = commands.add_parser("review-rounds", help="visões rodada a rodada e atribuição das mudanças")
    review.add_argument("--season", type=int, default=2026)
    review.add_argument("--simulations", type=int, default=10_000)
    review.add_argument("--seed", type=int, default=2026)
    review.set_defaults(handler=command_review_rounds)

    export = commands.add_parser("export-web", help="exporta JSON estático para apps/web/data")
    export.add_argument("--season", type=int, default=2026)
    export.set_defaults(handler=command_export_web)

    insights_generate = commands.add_parser(
        "insights-generate", help="08A: gera candidatos a insight do snapshot atual"
    )
    insights_generate.add_argument("--season", type=int, default=2026)
    insights_generate.set_defaults(handler=command_insights_generate)

    insights_list = commands.add_parser("insights-list", help="lista candidatos do último lote e o estado editorial")
    insights_list.add_argument("--season", type=int, default=2026)
    insights_list.set_defaults(handler=command_insights_list)

    insights_review = commands.add_parser("insights-review", help="08: registra a revisão editorial de um candidato")
    insights_review.add_argument("--season", type=int, default=2026)
    insights_review.add_argument("--insight-id", required=True)
    insights_review.add_argument("--decision", required=True, choices=["approved", "needs_revision", "rejected"])
    insights_review.add_argument("--reason", required=True)
    insights_review.add_argument("--fail", nargs="*", default=[], help="itens do checklist que falharam")
    insights_review.add_argument(
        "--placement", choices=["home_lead", "home_secondary", "club", "round", "matches", "season"], default=None
    )
    insights_review.add_argument("--priority", type=int, default=None)
    insights_review.add_argument("--headline", default=None, help="título editado")
    insights_review.add_argument("--body", default=None, help="texto editado")
    insights_review.add_argument("--editor", default="agente-08")
    insights_review.set_defaults(handler=command_insights_review)

    insights_publish = commands.add_parser("insights-publish", help="publica os aprovados do último lote")
    insights_publish.add_argument("--season", type=int, default=2026)
    insights_publish.set_defaults(handler=command_insights_publish)
    return parser


def main(argv: list[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    configure_logging(logging.DEBUG if arguments.verbose else logging.INFO)
    arguments.handler(arguments)


if __name__ == "__main__":
    main()
