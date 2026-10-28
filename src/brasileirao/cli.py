"""Linha de comando: `python -m brasileirao.cli <comando>`."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from brasileirao.competition_rules.season_rules import load_season_rules
from brasileirao.config import PATHS, SimulationConfig
from brasileirao.data_pipeline.adaoduque import AdaoDuqueFilesError, AdaoDuqueSource
from brasileirao.data_pipeline.clubs import load_club_registry
from brasileirao.data_pipeline.composition import (
    CompositionError,
    CompositionMode,
    compose,
    latest_ingestion,
    load_source_input,
    normalized_frame,
    publication_plan,
    write_composition,
)
from brasileirao.data_pipeline.conference import CONFERENCE_PAIRS, compare_sources, counts_table
from brasileirao.data_pipeline.corrections import load_corrections
from brasileirao.data_pipeline.football_data_org import (
    AwardedMatchError,
    FootballDataOrgSource,
    MissingTokenError,
)
from brasileirao.data_pipeline.ingest import append_changes, ingest_raw, read_matches, write_gold
from brasileirao.data_pipeline.sources import BrasileiraoDatasetSource
from brasileirao.data_pipeline.validation import (
    load_awarded_results,
    load_known_exceptions,
    run_quality_checks,
)
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
from brasileirao.provenance import ProvenanceError
from brasileirao.publication_gate import GateInputs, run_publication_gate
from brasileirao.storage.snapshots import SnapshotStore
from brasileirao.validation.report import run_backtest_report

LOGGER = get_logger("brasileirao.cli")
DEFAULT_CHECKOUT = PATHS.raw / "_sources" / "brasileirao-dataset"
DEFAULT_ADAODUQUE_DIR = PATHS.raw / "adaoduque" / "v18"
SOURCE_PINS = PATHS.reference / "source_pins.json"
BRASILIA = ZoneInfo("America/Sao_Paulo")


def _ingest_research(arguments: argparse.Namespace) -> None:
    """Só pesquisa local: `brasileirao-dataset` (Sofascore em 2024+), nunca publicável (ADR-0008)."""
    source = BrasileiraoDatasetSource(Path(arguments.checkout))
    snapshot = source.fetch(arguments.revision) if arguments.fetch else source.snapshot_from_checkout()
    raw_dir = ingest_raw(snapshot, PATHS.raw)
    source_input = load_source_input(raw_dir)
    seasons = {match.season: source.source_name for match in source_input.matches}
    composition = compose({source.source_name: source_input}, seasons, load_club_registry(), CompositionMode.RESEARCH)
    write_composition(composition, PATHS.silver, load_corrections(PATHS.reference / "manual_corrections.csv"))
    write_gold(PATHS.silver, PATHS.gold)
    print(f"ingestão de PESQUISA concluída (não publicável): {raw_dir}")


def _football_data_seasons(publication_seasons: list[int]) -> list[int]:
    conference_seasons = [
        season
        for pair in CONFERENCE_PAIRS
        if FootballDataOrgSource.source_name in (pair.candidate, pair.reference)
        for season in pair.seasons
    ]
    return sorted(set(publication_seasons) | set(conference_seasons))


def command_ingest(arguments: argparse.Namespace) -> None:
    if arguments.research_source:
        _ingest_research(arguments)
        return
    plan = publication_plan(arguments.season)
    awarded = load_awarded_results(PATHS.reference / "known_exceptions.csv", FootballDataOrgSource.source_name)
    try:
        adaoduque_raw = ingest_raw(AdaoDuqueSource(Path(arguments.adaoduque_dir), SOURCE_PINS).snapshot(), PATHS.raw)
        if arguments.fetch:
            publication_seasons = [season for season, name in plan.items() if name == FootballDataOrgSource.source_name]
            football_data = FootballDataOrgSource.from_environment()
            football_raw = ingest_raw(
                football_data.fetch(_football_data_seasons(publication_seasons), PATHS.raw, awarded), PATHS.raw
            )
        else:
            football_raw = latest_ingestion(PATHS.raw, FootballDataOrgSource.source_name)
        inputs = {
            AdaoDuqueSource.source_name: load_source_input(adaoduque_raw),
            FootballDataOrgSource.source_name: load_source_input(football_raw, awarded),
        }
        composition = compose(inputs, plan, load_club_registry())
    except (AdaoDuqueFilesError, MissingTokenError, AwardedMatchError, CompositionError) as error:
        raise SystemExit(f"ingestão de publicação interrompida, nada foi gravado na silver/gold: {error}") from error
    write_composition(composition, PATHS.silver, load_corrections(PATHS.reference / "manual_corrections.csv"))
    write_gold(PATHS.silver, PATHS.gold)
    for season, source_name in sorted(plan.items()):
        n_matches = sum(1 for record in composition.records if record.season == season)
        print(f"{season}: {source_name} ({n_matches} partidas)")
    print("ingestão de publicação concluída; composição em data/silver/sources.json")


def command_pin_adaoduque(arguments: argparse.Namespace) -> None:
    try:
        hashes = AdaoDuqueSource(Path(arguments.adaoduque_dir), SOURCE_PINS).pin_current_files()
    except AdaoDuqueFilesError as error:
        raise SystemExit(str(error)) from error
    for name, digest in hashes.items():
        print(f"{digest}  {name}")
    print(f"hashes gravados em {SOURCE_PINS}; confira contra o espelho do GitHub antes de versionar")


def command_conference(arguments: argparse.Namespace) -> None:
    registry = load_club_registry()
    awarded = load_awarded_results(PATHS.reference / "known_exceptions.csv", FootballDataOrgSource.source_name)
    frames = {}
    for source_name in sorted({name for pair in CONFERENCE_PAIRS for name in (pair.candidate, pair.reference)}):
        try:
            frames[source_name] = normalized_frame(
                load_source_input(latest_ingestion(PATHS.raw, source_name), awarded), registry
            )
        except CompositionError as error:
            print(f"sem conferência com {source_name}: {error}")
    reports = [
        compare_sources(frames[pair.candidate], frames[pair.reference], pair)
        for pair in CONFERENCE_PAIRS
        if pair.candidate in frames and pair.reference in frames
    ]
    if not reports:
        raise SystemExit("nenhum par de fontes disponível para conferência")
    PATHS.silver.mkdir(parents=True, exist_ok=True)
    (PATHS.silver / "conference_report.json").write_text(
        json.dumps([report.model_dump() for report in reports], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    append_changes(PATHS.silver, [entry for report in reports for entry in report.divergences])
    print(json.dumps(counts_table(reports), indent=2, ensure_ascii=False))


def command_validate(arguments: argparse.Namespace) -> None:
    matches_data = read_matches(PATHS.gold / "matches_model.csv")
    reference = (
        date.fromisoformat(arguments.reference_date)
        if arguments.reference_date
        else datetime.now(tz=UTC).astimezone(BRASILIA).date()
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


def _composition_mode(arguments: argparse.Namespace) -> CompositionMode:
    return CompositionMode.RESEARCH if arguments.research else CompositionMode.PUBLICATION


def command_simulate(arguments: argparse.Namespace) -> None:
    reference = date.fromisoformat(arguments.reference_date) if arguments.reference_date else None
    store = SnapshotStore(PATHS.snapshots_db)
    try:
        saved = run_season_snapshots(
            arguments.season,
            arguments.simulations,
            arguments.seed,
            reference,
            arguments.history_from_round,
            arguments.history_simulations,
            store,
            _composition_mode(arguments),
        )
    except ProvenanceError as error:
        raise SystemExit(f"simulação interrompida, nenhum snapshot salvo: {error}") from error
    print(f"snapshots salvos: {saved}")
    _export_publication(store, arguments)


def command_review_rounds(arguments: argparse.Namespace) -> None:
    store = SnapshotStore(PATHS.snapshots_db)
    try:
        review = run_round_review(
            arguments.season, arguments.simulations, arguments.seed, store, _composition_mode(arguments)
        )
    except ProvenanceError as error:
        raise SystemExit(f"revisão interrompida, nada foi salvo: {error}") from error
    print(f"revisão salva: {len(review.rounds)} visões (rodadas 0 a {review.rounds[-1].round_number})")
    _export_publication(store, arguments)


def _export_publication(store: SnapshotStore, arguments: argparse.Namespace) -> None:
    """O export estático é artefato publicável: em modo pesquisa ele não é regenerado."""
    if _composition_mode(arguments) == CompositionMode.RESEARCH:
        print("modo pesquisa: export estático não atualizado (snapshots de pesquisa nunca vão para apps/web/data)")
        return
    export_static_api(store, arguments.season)


def command_export_web(arguments: argparse.Namespace) -> None:
    for path in export_static_api(SnapshotStore(PATHS.snapshots_db), arguments.season):
        print(f"exportado: {path}")


def command_publication_gate(arguments: argparse.Namespace) -> None:
    """Gate G1 a G5 do ADR-0008; código de saída 1 se qualquer regra falhar (o 07 chama no workflow)."""
    inputs = GateInputs(
        gold_matches=Path(arguments.gold),
        composition=Path(arguments.composition),
        predictions=Path(
            arguments.predictions
            or PATHS.web_static_data / "api" / "seasons" / str(arguments.season) / "predictions.json"
        ),
        artifact_dir=Path(arguments.artifact_dir),
    )
    findings = run_publication_gate(inputs)
    for finding in findings:
        print(f"[{finding.rule}] {finding.detail}")
    print(f"gate de publicação: {'REPROVADO' if findings else 'aprovado'} ({len(findings)} achados)")
    if findings:
        raise SystemExit(1)


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

    ingest = commands.add_parser(
        "ingest", help="ingestão raw → silver → gold (publicação: Adão Duque v18 até 2025 e football-data.org 2026+)"
    )
    ingest.add_argument("--season", type=int, default=datetime.now(tz=UTC).astimezone(BRASILIA).year)
    ingest.add_argument("--adaoduque-dir", default=str(DEFAULT_ADAODUQUE_DIR), help="arquivos da v18 do Kaggle")
    ingest.add_argument(
        "--fetch",
        action="store_true",
        help="consulta a football-data.org (FOOTBALL_DATA_ORG_TOKEN); sem ela, usa a última ingestão raw",
    )
    ingest.add_argument(
        "--research-source",
        choices=["brasileirao_dataset"],
        default=None,
        help="SÓ PESQUISA LOCAL: ingere o brasileirao-dataset (não publicável)",
    )
    ingest.add_argument("--checkout", default=str(DEFAULT_CHECKOUT), help="clone local do brasileirao-dataset")
    ingest.add_argument("--revision", default=None, help="commit do brasileirao-dataset (pesquisa)")
    ingest.set_defaults(handler=command_ingest)

    pin = commands.add_parser("pin-adaoduque", help="fixa o SHA-256 dos arquivos da v18 do Adão Duque")
    pin.add_argument("--adaoduque-dir", default=str(DEFAULT_ADAODUQUE_DIR))
    pin.set_defaults(handler=command_pin_adaoduque)

    conference = commands.add_parser("conference", help="conferência local entre fontes (só contagens na saída)")
    conference.set_defaults(handler=command_conference)

    validate = commands.add_parser("validate", help="checagens de integridade")
    validate.add_argument("--reference-date", default=None)
    validate.set_defaults(handler=command_validate)

    backtest = commands.add_parser("backtest", help="ajuste de hiperparâmetros e backtesting temporal")
    backtest.add_argument("--rules-season", type=int, default=2026)
    backtest.add_argument("--simulations", type=int, default=2000)
    backtest.set_defaults(handler=command_backtest)

    simulate = commands.add_parser("simulate", help="gera snapshots de previsão")
    simulate.add_argument("--season", type=int, default=2026)
    simulate.add_argument("--simulations", type=int, default=SimulationConfig().n_simulations)
    simulate.add_argument("--seed", type=int, default=SimulationConfig().seed)
    simulate.add_argument("--reference-date", default=None)
    simulate.add_argument("--history-from-round", type=int, default=None)
    simulate.add_argument("--history-simulations", type=int, default=2000)
    simulate.add_argument(
        "--research",
        action="store_true",
        help="SÓ PESQUISA LOCAL: aceita sources.json com mode=research; o snapshot nunca é publicável",
    )
    simulate.set_defaults(handler=command_simulate)

    review = commands.add_parser("review-rounds", help="visões rodada a rodada e atribuição das mudanças")
    review.add_argument("--season", type=int, default=2026)
    review.add_argument("--simulations", type=int, default=SimulationConfig().round_review_simulations)
    review.add_argument("--seed", type=int, default=SimulationConfig().seed)
    review.add_argument(
        "--research",
        action="store_true",
        help="SÓ PESQUISA LOCAL: aceita sources.json com mode=research; o snapshot nunca é publicável",
    )
    review.set_defaults(handler=command_review_rounds)

    gate = commands.add_parser("publication-gate", help="gate G1 a G5 do ADR-0008 antes do deploy")
    gate.add_argument("--season", type=int, default=2026)
    gate.add_argument("--gold", default=str(PATHS.gold / "matches_model.csv"))
    gate.add_argument("--composition", default=str(PATHS.silver / "sources.json"))
    gate.add_argument("--predictions", default=None, help="predictions.json exportado (padrão: o da temporada)")
    gate.add_argument("--artifact-dir", default=str(PATHS.root / "apps" / "web"), help="pasta do artefato do Pages")
    gate.set_defaults(handler=command_publication_gate)

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
