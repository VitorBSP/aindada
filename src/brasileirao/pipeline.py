"""Orquestração ponta a ponta (Agente 00).

Fluxo: ingestão → validação → ratings → modelo → simulação → regras → snapshot → publicação.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from brasileirao.competition_rules.scenarios import enumerate_external_scenarios
from brasileirao.competition_rules.season_rules import SeasonRules, load_season_rules
from brasileirao.competition_rules.standings import rank_table
from brasileirao.config import (
    MODEL_VERSION,
    PATHS,
    ROUND_REVIEW_SCHEMA_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    ModelTrainingConfig,
    RatingParams,
    SimulationUncertainty,
)
from brasileirao.contracts import MatchStatus
from brasileirao.data_pipeline.clubs import ClubRegistry, load_club_registry
from brasileirao.data_pipeline.composition import CompositionMode
from brasileirao.data_pipeline.ingest import card_totals_as_of, read_matches
from brasileirao.data_pipeline.validation import (
    QualityReport,
    Severity,
    load_known_exceptions,
    run_quality_checks,
)
from brasileirao.frame_values import as_int, as_timestamp
from brasileirao.logging_utils import get_logger
from brasileirao.prediction.goals_model import GoalsModel, outcome_probabilities, top_scores, total_goals_at_least
from brasileirao.prediction.schedule import build_schedules
from brasileirao.provenance import ProvenanceError, load_data_info, read_composition
from brasileirao.publication_gate import check_g1_gold_sources
from brasileirao.ratings.history import RatingEngine, RatingState, build_state_as_of
from brasileirao.simulation.engine import SeasonSimulator, SimulationResult
from brasileirao.simulation.round_review import METRICS, RoundView, build_round_view, round_cutoffs
from brasileirao.simulation.summary import build_team_summaries
from brasileirao.storage.schema import (
    ClubLabel,
    DataInfo,
    ExternalContextInfo,
    ExternalScenarioInfo,
    MatchPrediction,
    ModelInfo,
    PredictionSnapshot,
    RatingsInfo,
    RoundReview,
    RoundViewInfo,
    ScenarioRange,
    ScheduleInfo,
    ScheduleScaleInfo,
    ScoreProbability,
    StandingEntry,
    SudamericanaRace,
    TeamPrediction,
)
from brasileirao.storage.snapshots import SnapshotStore
from brasileirao.validation.backtest import training_window
from brasileirao.validation.report import rating_params_from_dict

LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class ModelConfig:
    feature_set: str
    rating_params: RatingParams
    dynamic_ratings: bool
    draw_inflation: bool = False
    uncertainty: SimulationUncertainty = field(default_factory=SimulationUncertainty)
    goal_dispersion: bool = False


def load_model_config(gold_dir: Path = PATHS.gold) -> ModelConfig:
    config_path = gold_dir / "model_config.json"
    if not config_path.exists():
        LOGGER.warning("model_config_missing_using_defaults", extra={"path": str(config_path)})
        return ModelConfig("elo_only", RatingParams(), True)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return ModelConfig(
        feature_set=str(payload["feature_set"]),
        rating_params=rating_params_from_dict(payload["rating_params"]),
        dynamic_ratings=bool(payload.get("dynamic_ratings_in_simulation", True)),
        draw_inflation=bool(payload.get("draw_inflation", False)),
        uncertainty=SimulationUncertainty(**payload.get("simulation_uncertainty", {})),
        goal_dispersion=bool(payload.get("goal_dispersion", False)),
    )


def _scenario_range(values: dict[str, float]) -> ScenarioRange:
    return ScenarioRange(
        min=values["min"],
        max=values["max"],
        by_scenario={key: value for key, value in values.items() if key not in ("min", "max")},
    )


def _quality_warnings(report: QualityReport, season: int) -> list[str]:
    return [issue.detail for issue in report.issues if issue.season == season and issue.severity != Severity.INFO]


@dataclass(frozen=True)
class PreparedSimulation:
    engine: RatingEngine
    model: GoalsModel
    simulator: SeasonSimulator
    card_warning: str | None


def prepare_simulation(
    matches_data: pd.DataFrame,
    season: int,
    reference_date: date,
    rules: SeasonRules,
    model_config: ModelConfig,
    cards_by_match: pd.DataFrame | None = None,
    training: ModelTrainingConfig | None = None,
    rating_state: RatingState | None = None,
) -> PreparedSimulation:
    """Estado dos ratings, modelo de gols treinado e simulador, todos restritos à data de referência.

    `rating_state` substitui a força dos clubes na data (usado para isolar o efeito dos resultados).
    """
    training_config = training or ModelTrainingConfig()
    engine, features = build_state_as_of(matches_data, reference_date, season, model_config.rating_params)
    model = GoalsModel.fit(
        training_window(
            features, season, training_config.training_seasons_window, training_config.first_training_season
        ),
        model_config.feature_set,
        alpha=training_config.poisson_alpha,
        max_goals=training_config.max_goals,
        draw_inflation=model_config.draw_inflation,
        goal_dispersion=model_config.goal_dispersion,
    )
    card_totals, card_warning = _usable_card_totals(cards_by_match, matches_data, season, reference_date)
    season_matches = matches_data[matches_data["season"] == season]
    simulator = SeasonSimulator(
        season_matches,
        reference_date,
        rating_state or engine.state,
        model,
        model_config.rating_params,
        rules,
        card_totals,
    )
    return PreparedSimulation(engine, model, simulator, card_warning)


def build_snapshot(
    matches_data: pd.DataFrame,
    season: int,
    reference_date: date,
    n_simulations: int,
    seed: int,
    rules: SeasonRules,
    registry: ClubRegistry,
    model_config: ModelConfig,
    data_info: DataInfo,
    cards_by_match: pd.DataFrame | None = None,
    training: ModelTrainingConfig | None = None,
) -> PredictionSnapshot:
    prepared = prepare_simulation(matches_data, season, reference_date, rules, model_config, cards_by_match, training)
    engine, model = prepared.engine, prepared.model
    if prepared.card_warning:
        data_info = data_info.model_copy(update={"warnings": [*data_info.warnings, prepared.card_warning]})
    result = prepared.simulator.run(n_simulations, seed, model_config.dynamic_ratings, model_config.uncertainty)
    scenarios = enumerate_external_scenarios(rules, registry.display_name)
    summaries, _ = build_team_summaries(result, rules, scenarios)
    schedules, scale = build_schedules(
        result.remaining_matches, engine.state, model, result.club_ids, rules.points_win, rules.points_draw
    )
    schedule_by_club = {schedule.club_id: schedule for schedule in schedules}

    table = result.observed_table
    current_order = rank_table(table, rules)
    standings = []
    for position, club_id in enumerate(current_order, start=1):
        club = table.club_ids.index(club_id)
        standings.append(
            StandingEntry(
                position=position,
                club_id=club_id,
                name=registry.display_name(club_id),
                short_name=registry.clubs[club_id].short_name,
                played=int(table.played[club]),
                points=int(table.points[club]),
                wins=int(table.wins[club]),
                draws=int(table.draws[club]),
                losses=int(table.losses[club]),
                goals_for=int(table.goals_for[club]),
                goals_against=int(table.goals_against[club]),
                goal_difference=int(table.goal_difference[club]),
            )
        )
    standing_by_club = {entry.club_id: entry for entry in standings}

    teams = []
    for summary in summaries:
        rating = engine.state.ratings[summary.club_id]
        standing = standing_by_club[summary.club_id]
        teams.append(
            TeamPrediction(
                club_id=summary.club_id,
                name=standing.name,
                short_name=standing.short_name,
                current_position=standing.position,
                current_points=standing.points,
                played=standing.played,
                expected_points=summary.expected_points,
                median_points=summary.median_points,
                points_interval_90=summary.points_interval_90,
                expected_goals_for=summary.expected_goals_for,
                expected_goals_against=summary.expected_goals_against,
                expected_position=summary.expected_position,
                position_probabilities=summary.position_probabilities,
                title=summary.title,
                runner_up=summary.runner_up,
                top4=summary.top4,
                relegation=summary.relegation,
                libertadores_groups=_scenario_range(summary.libertadores_groups),
                libertadores_prelim=_scenario_range(summary.libertadores_prelim),
                libertadores_total=_scenario_range(summary.libertadores_total),
                sudamericana=_scenario_range(summary.sudamericana),
                sudamericana_race=(
                    SudamericanaRace.model_validate(asdict(summary.sudamericana_race))
                    if summary.sudamericana_race
                    else None
                ),
                schedule=ScheduleInfo.model_validate(asdict(schedule_by_club[summary.club_id])),
                ratings=RatingsInfo(elo=rating.elo, attack=rating.attack, defense=rating.defense, form=rating.form),
            )
        )

    matches = _match_predictions(result.observed_matches, result.remaining_matches, engine, model)
    external = rules.external
    return PredictionSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        season=season,
        reference_date=reference_date.isoformat(),
        generated_at=datetime.now(tz=UTC).isoformat(),
        n_simulations=n_simulations,
        seed=seed,
        dynamic_ratings=model_config.dynamic_ratings,
        observed_matches=len(result.observed_matches),
        remaining_matches=len(result.remaining_matches),
        model=ModelInfo(
            model_version=MODEL_VERSION,
            feature_set=model.feature_set,
            rho=model.rho,
            draw_inflation=model.draw_inflation,
            goal_dispersion=model.goal_dispersion,
            simulation_uncertainty={key: float(value) for key, value in asdict(model_config.uncertainty).items()},
            home_coefficients=model.home_coefficients,
            away_coefficients=model.away_coefficients,
            training_seasons=model.training_seasons,
            rating_params={
                name: {key: float(value) for key, value in group.items()}
                for name, group in asdict(model_config.rating_params).items()
            },
        ),
        data=data_info,
        regulation={"title": rules.regulation_title, "url": rules.regulation_url, "date": rules.regulation_date},
        external_context=ExternalContextInfo(
            as_of=external.as_of,
            notes=list(external.notes),
            sources=list(external.sources),
            libertadores_finalists=list(external.libertadores_finalists),
            sudamericana_finalists=list(external.sudamericana_finalists),
            cup_semifinals=[list(pair) for pair in external.cup_semifinals],
            cup_redirect_policy=rules.cup_redirect_policy.value,
        ),
        scenarios=[ExternalScenarioInfo(scenario_id=scenario.scenario_id, **scenario.labels) for scenario in scenarios],
        schedule_scale=ScheduleScaleInfo.model_validate(asdict(scale)),
        standings=standings,
        teams=sorted(teams, key=lambda team: (-team.expected_points, team.name)),
        matches=matches,
    )


MIN_CARD_COVERAGE = 0.95


def _usable_card_totals(
    cards_by_match: pd.DataFrame | None, matches_data: pd.DataFrame, season: int, reference_date: date
) -> tuple[dict[str, tuple[int, int]], str | None]:
    """Cartões só entram no desempate se cobrirem praticamente todos os jogos observados."""
    if cards_by_match is None:
        return {}, "Sem dados de cartões: critérios 5 e 6 do Art. 15 substituídos por sorteio."
    observed_ids = set(
        matches_data.loc[
            (matches_data["season"] == season)
            & (matches_data["status"] == MatchStatus.FINISHED.value)
            & (matches_data["match_date"].dt.date <= reference_date),
            "match_id",
        ]
    )
    covered = observed_ids & set(cards_by_match.loc[cards_by_match["season"] == season, "match_id"])
    coverage = len(covered) / len(observed_ids) if observed_ids else 0.0
    if coverage < MIN_CARD_COVERAGE:
        return {}, (
            f"Cartões disponíveis para {len(covered)} de {len(observed_ids)} jogos observados; "
            "critérios 5 e 6 do Art. 15 (cartões) substituídos por sorteio."
        )
    totals = card_totals_as_of(cards_by_match, matches_data, season, reference_date)
    return {item.club_id: (item.red_cards, item.yellow_cards) for item in totals}, None


TOP_SCORES_PER_MATCH = 3


def _match_predictions(
    observed: pd.DataFrame, remaining: pd.DataFrame, engine: Any, model: GoalsModel
) -> list[MatchPrediction]:
    predictions: list[MatchPrediction] = []
    for match in observed.itertuples(index=False):
        predictions.append(
            MatchPrediction(
                match_id=str(match.match_id),
                round=None if pd.isna(match.round) else as_int(match.round),
                match_date=as_timestamp(match.match_date).date().isoformat(),
                home_id=str(match.home_id),
                away_id=str(match.away_id),
                status=MatchStatus.FINISHED.value,
                home_goals=as_int(match.home_goals),
                away_goals=as_int(match.away_goals),
            )
        )
    if len(remaining):
        feature_rows = pd.DataFrame(
            [
                engine.pre_match_features(str(match.home_id), str(match.away_id))
                for match in remaining.itertuples(index=False)
            ]
        )
        matrices = model.score_probabilities(feature_rows)
        home_rate, away_rate = model.expected_goals(feature_rows)
        outcome = outcome_probabilities(matrices)
        three_plus_goals = total_goals_at_least(matrices, 3)
        for position, match in enumerate(remaining.itertuples(index=False)):
            best_scores = [
                ScoreProbability(home_goals=home_goals, away_goals=away_goals, probability=probability)
                for home_goals, away_goals, probability in top_scores(matrices[position], TOP_SCORES_PER_MATCH)
            ]
            predictions.append(
                MatchPrediction(
                    match_id=str(match.match_id),
                    round=None if pd.isna(match.round) else as_int(match.round),
                    match_date=as_timestamp(match.match_date).date().isoformat(),
                    home_id=str(match.home_id),
                    away_id=str(match.away_id),
                    status=MatchStatus.SCHEDULED.value,
                    p_home=float(outcome[position, 0]),
                    p_draw=float(outcome[position, 1]),
                    p_away=float(outcome[position, 2]),
                    xg_home=float(home_rate[position]),
                    xg_away=float(away_rate[position]),
                    most_likely_score=f"{best_scores[0].home_goals}-{best_scores[0].away_goals}",
                    most_likely_score_probability=best_scores[0].probability,
                    top_scores=best_scores,
                    p_three_plus_goals=float(three_plus_goals[position]),
                )
            )
    return predictions


def load_inputs(
    season: int, mode: CompositionMode = CompositionMode.PUBLICATION
) -> tuple[pd.DataFrame, pd.DataFrame | None, SeasonRules, ClubRegistry, DataInfo, QualityReport]:
    """Gold, regras e proveniência pela composição `data/silver/sources.json` (ADR-0008, passo 10).

    Em modo publicação, composição ausente, de pesquisa ou gold fora da composição (G1) fazem falhar.
    """
    matches_data = read_matches(PATHS.gold / "matches_model.csv")
    if mode == CompositionMode.PUBLICATION:
        findings = check_g1_gold_sources(matches_data, read_composition(PATHS.silver))
        if findings:
            raise ProvenanceError("; ".join(finding.detail for finding in findings))
    cards_path = PATHS.silver / "cards_by_match.csv"
    cards_by_match = pd.read_csv(cards_path) if cards_path.exists() else None
    rules = load_season_rules(season)
    registry = load_club_registry()
    quality = run_quality_checks(
        matches_data,
        datetime.now(tz=UTC).date(),
        load_known_exceptions(PATHS.reference / "known_exceptions.csv"),
    )
    data_info = load_data_info(PATHS.silver, PATHS.raw, mode, _quality_warnings(quality, season))
    return matches_data, cards_by_match, rules, registry, data_info, quality


def default_reference_date(matches_data: pd.DataFrame, season: int) -> date:
    finished = matches_data[(matches_data["season"] == season) & (matches_data["status"] == MatchStatus.FINISHED.value)]
    return finished["match_date"].max().date() if len(finished) else datetime.now(tz=UTC).date()


def round_reference_dates(matches_data: pd.DataFrame, season: int, up_to: date, first_round: int) -> list[date]:
    """Último dia de cada rodada já completamente observada até `up_to`."""
    season_matches = matches_data[matches_data["season"] == season]
    dates: list[date] = []
    for round_number, round_matches in season_matches.groupby("round"):
        if int(str(round_number)) < first_round:
            continue
        finished = round_matches[round_matches["status"] == MatchStatus.FINISHED.value]
        if not len(finished):
            continue
        last_date = finished["match_date"].max().date()
        if last_date <= up_to:
            dates.append(last_date)
    return sorted(set(dates))


def run_season_snapshots(
    season: int,
    n_simulations: int,
    seed: int,
    reference_date: date | None = None,
    history_from_round: int | None = None,
    history_simulations: int = 2000,
    store: SnapshotStore | None = None,
    mode: CompositionMode = CompositionMode.PUBLICATION,
) -> list[int]:
    matches_data, cards_by_match, rules, registry, data_info, quality = load_inputs(season, mode)
    (PATHS.gold / "quality_report.json").write_text(quality.model_dump_json(indent=2), encoding="utf-8")
    snapshot_store = store or SnapshotStore(PATHS.snapshots_db)
    model_config = load_model_config()
    final_date = reference_date or default_reference_date(matches_data, season)
    history_dates = (
        [day for day in round_reference_dates(matches_data, season, final_date, history_from_round) if day < final_date]
        if history_from_round is not None
        else []
    )
    saved_ids: list[int] = []
    for snapshot_date, simulations in [
        *((day, history_simulations) for day in history_dates),
        (final_date, n_simulations),
    ]:
        snapshot = build_snapshot(
            matches_data,
            season,
            snapshot_date,
            simulations,
            seed,
            rules,
            registry,
            model_config,
            data_info,
            cards_by_match,
        )
        saved_ids.append(snapshot_store.save(snapshot))
        LOGGER.info(
            "snapshot_saved",
            extra={"season": season, "reference_date": snapshot_date.isoformat(), "n_simulations": simulations},
        )
    return saved_ids


def probability_history(store: SnapshotStore, season: int) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for record in store.latest_per_reference_date(season):
        snapshot = store.load(record.snapshot_id)
        history.append(
            {
                "reference_date": snapshot.reference_date,
                "observed_matches": snapshot.observed_matches,
                "n_simulations": snapshot.n_simulations,
                "teams": {
                    team.club_id: {
                        "title": team.title,
                        "top4": team.top4,
                        "relegation": team.relegation,
                        "libertadores_total_min": team.libertadores_total.min,
                        "libertadores_total_max": team.libertadores_total.max,
                        "expected_points": team.expected_points,
                    }
                    for team in snapshot.teams
                },
            }
        )
    return history


def export_static_api(store: SnapshotStore, season: int, output_dir: Path = PATHS.web_static_data) -> list[Path]:
    """Espelho estático dos endpoints GET, para servir o frontend sem backend."""
    snapshot = store.latest(season)
    if snapshot is None:
        raise RuntimeError(f"nenhum snapshot para {season}")
    documents: dict[str, Any] = {
        "api/seasons.json": [{"season": season, "latest_reference_date": snapshot.reference_date}],
        f"api/seasons/{season}/predictions.json": snapshot.model_dump(mode="json"),
        f"api/seasons/{season}/probability-history.json": probability_history(store, season),
    }
    metrics_path = PATHS.gold / "backtest_report.json"
    if metrics_path.exists():
        report = json.loads(metrics_path.read_text(encoding="utf-8"))
        report.pop("tuning_records", None)
        report.get("season_simulation", {}).pop("records", None)
        documents["api/models/metrics.json"] = report
    review = store.latest_round_review(season)
    if review is not None:
        documents[f"api/seasons/{season}/rounds.json"] = review.model_dump(mode="json")
    written: list[Path] = []
    for relative_path, document in documents.items():
        target = output_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        written.append(target)
    return written


def build_round_review(
    matches_data: pd.DataFrame,
    season: int,
    data_until: date,
    n_simulations: int,
    seed: int,
    rules: SeasonRules,
    registry: ClubRegistry,
    model_config: ModelConfig,
    data_info: DataInfo,
    cards_by_match: pd.DataFrame | None = None,
) -> RoundReview:
    """Uma visão por rodada desde a pré-temporada, com a atribuição das mudanças a cada jogo."""
    season_matches = matches_data[matches_data["season"] == season]
    views: list[RoundView] = []
    previous: tuple[RoundView, SimulationResult] | None = None
    previous_state: RatingState | None = None
    settings = (n_simulations, seed, model_config.dynamic_ratings, model_config.uncertainty)
    for cutoff in round_cutoffs(season_matches, data_until):
        prepared = prepare_simulation(matches_data, season, cutoff.reference_date, rules, model_config, cards_by_match)
        result = prepared.simulator.run(*settings)
        results_only = None
        if previous_state is not None:
            intermediate = prepare_simulation(
                matches_data,
                season,
                cutoff.reference_date,
                rules,
                model_config,
                cards_by_match,
                rating_state=previous_state,
            )
            results_only = intermediate.simulator.run(*settings)
        view = build_round_view(cutoff, result, rules, previous, season_matches, results_only)
        views.append(view)
        previous, previous_state = (view, result), prepared.engine.state
        LOGGER.info(
            "round_view_built",
            extra={"season": season, "round": cutoff.round_number, "reference_date": cutoff.reference_date.isoformat()},
        )
    clubs = sorted(set(season_matches["home_id"]) | set(season_matches["away_id"]))
    return RoundReview(
        schema_version=ROUND_REVIEW_SCHEMA_VERSION,
        season=season,
        generated_at=datetime.now(tz=UTC).isoformat(),
        model_version=MODEL_VERSION,
        data_version=data_info.version,
        data_until=data_until.isoformat(),
        n_simulations=n_simulations,
        seed=seed,
        composition_mode=data_info.composition_mode,
        license_status=data_info.license_status,
        metrics=list(METRICS),
        clubs={
            club: ClubLabel(name=registry.display_name(club), short_name=registry.clubs[club].short_name)
            for club in clubs
        },
        rounds=[RoundViewInfo.model_validate(asdict(view)) for view in views],
    )


def run_round_review(
    season: int,
    n_simulations: int,
    seed: int,
    store: SnapshotStore | None = None,
    mode: CompositionMode = CompositionMode.PUBLICATION,
) -> RoundReview:
    matches_data, cards_by_match, rules, registry, data_info, _ = load_inputs(season, mode)
    review = build_round_review(
        matches_data,
        season,
        default_reference_date(matches_data, season),
        n_simulations,
        seed,
        rules,
        registry,
        load_model_config(),
        data_info,
        cards_by_match,
    )
    (store or SnapshotStore(PATHS.snapshots_db)).save_round_review(review)
    return review
