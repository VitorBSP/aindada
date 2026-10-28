"""Esquema do snapshot publicado (contrato entre modelagem, API e frontend)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ScenarioRange(BaseModel):
    """Probabilidade que depende de torneios externos: faixa e valor por cenário."""

    min: float
    max: float
    by_scenario: dict[str, float]


class ExternalScenarioInfo(BaseModel):
    scenario_id: str
    libertadores_champion: str
    sudamericana_champion: str
    cup_champion: str
    cup_runner_up: str


class ExternalContextInfo(BaseModel):
    as_of: str
    notes: list[str]
    sources: list[str]
    libertadores_finalists: list[str]
    sudamericana_finalists: list[str]
    cup_semifinals: list[list[str]]
    cup_redirect_policy: str


class StandingEntry(BaseModel):
    position: int
    club_id: str
    name: str
    short_name: str
    played: int
    points: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int


class RatingsInfo(BaseModel):
    elo: float
    attack: float
    defense: float
    form: float


class SudamericanaRace(BaseModel):
    """Corrida pela Sul-Americana sem pesos para os cenários externos.

    `all_scenarios`/`any_scenario`: probabilidade de a vaga valer em todos / em pelo menos um cenário.
    `midpoint`: centro da faixa mín.–máx. por cenário (só ordena; não é probabilidade).
    `rank`: posição na classificação da corrida; `rank_best`/`rank_worst`: extremos entre cenários.
    """

    all_scenarios: float
    any_scenario: float
    midpoint: float
    rank: int
    rank_best: int
    rank_worst: int


class ScheduleMatchInfo(BaseModel):
    match_id: str
    round: int | None
    match_date: str
    opponent_id: str
    venue: str
    p_win: float
    p_draw: float
    p_loss: float
    expected_points: float
    average_team_points: float
    difficulty: float
    opponent_strength: float


class ScheduleInfo(BaseModel):
    """Jogos restantes do clube: pontos esperados e dificuldade (0–100, 50 = tabela média da liga)."""

    remaining_matches: int
    home_matches: int
    away_matches: int
    expected_points: float
    expected_points_home: float
    expected_points_away: float
    average_team_points: float
    difficulty: float | None
    opponent_strength: float | None
    difficulty_home: float | None
    difficulty_away: float | None
    difficulty_rank: int | None
    difficulty_home_rank: int | None
    difficulty_away_rank: int | None
    matches: list[ScheduleMatchInfo]


class ScheduleScaleInfo(BaseModel):
    """Âncoras do índice de dificuldade, em pontos por jogo de um clube de força média."""

    reference_points: float
    reference_points_home: float
    reference_points_away: float
    half_range_points: float


class TeamPrediction(BaseModel):
    club_id: str
    name: str
    short_name: str
    current_position: int
    current_points: int
    played: int
    expected_points: float
    median_points: float
    points_interval_90: tuple[float, float]
    expected_goals_for: float
    expected_goals_against: float
    expected_position: float
    position_probabilities: list[float] = Field(min_length=1)
    title: float
    runner_up: float
    top4: float
    relegation: float
    libertadores_groups: ScenarioRange
    libertadores_prelim: ScenarioRange
    libertadores_total: ScenarioRange
    sudamericana: ScenarioRange
    sudamericana_race: SudamericanaRace | None = None
    schedule: ScheduleInfo | None = None
    ratings: RatingsInfo


class ScoreProbability(BaseModel):
    home_goals: int
    away_goals: int
    probability: float


class MatchPrediction(BaseModel):
    match_id: str
    round: int | None
    match_date: str
    home_id: str
    away_id: str
    status: str
    home_goals: int | None = None
    away_goals: int | None = None
    p_home: float | None = None
    p_draw: float | None = None
    p_away: float | None = None
    xg_home: float | None = None
    xg_away: float | None = None
    most_likely_score: str | None = None
    most_likely_score_probability: float | None = None
    top_scores: list[ScoreProbability] | None = None
    p_three_plus_goals: float | None = None


class ModelInfo(BaseModel):
    model_version: str
    feature_set: str
    rho: float
    draw_inflation: float = 0.0
    goal_dispersion: float = 1.0
    simulation_uncertainty: dict[str, float] = Field(default_factory=dict)
    home_coefficients: list[float]
    away_coefficients: list[float]
    training_seasons: list[int]
    rating_params: dict[str, dict[str, float]]


class DataInfo(BaseModel):
    source: str
    version: str
    license_status: str
    retrieved_at: str
    warnings: list[str]


class PredictionSnapshot(BaseModel):
    schema_version: str
    season: int
    reference_date: str
    generated_at: str
    n_simulations: int
    seed: int
    dynamic_ratings: bool
    observed_matches: int
    remaining_matches: int
    is_synthetic: bool = False
    model: ModelInfo
    data: DataInfo
    regulation: dict[str, str]
    external_context: ExternalContextInfo
    scenarios: list[ExternalScenarioInfo]
    schedule_scale: ScheduleScaleInfo | None = None
    standings: list[StandingEntry]
    teams: list[TeamPrediction]
    matches: list[MatchPrediction]


ClubMetricValues = dict[str, dict[str, float]]


class ClubLabel(BaseModel):
    name: str
    short_name: str


class MatchImpactInfo(BaseModel):
    match_id: str
    round: int
    match_date: str
    home_id: str
    away_id: str
    home_goals: int
    away_goals: int
    outcome: str
    pre_match: dict[str, float]
    impacts: ClubMetricValues
    stakes: ClubMetricValues


class MoverInfo(BaseModel):
    club_id: str
    delta: float


class RoundSummaryInfo(BaseModel):
    risers: dict[str, list[MoverInfo]]
    fallers: dict[str, list[MoverInfo]]
    total_movement: dict[str, float]
    results_movement: dict[str, float]
    strength_movement: dict[str, float]
    residual_movement: dict[str, float]
    expected_noise_movement: dict[str, float]
    decisive_match_id: str | None = None
    surprise_match_id: str | None = None


class RoundViewInfo(BaseModel):
    round_number: int
    reference_date: date
    partial: bool
    observed_matches: int
    teams: ClubMetricValues
    matches: list[MatchImpactInfo] = Field(default_factory=list)
    changes: ClubMetricValues = Field(default_factory=dict)
    results_effect: ClubMetricValues = Field(default_factory=dict)
    strength_effect: ClubMetricValues = Field(default_factory=dict)
    residual: ClubMetricValues = Field(default_factory=dict)
    summary: RoundSummaryInfo | None = None


class RoundReview(BaseModel):
    """Visões rodada a rodada e atribuição das mudanças de probabilidade a cada jogo."""

    schema_version: str
    season: int
    generated_at: str
    model_version: str
    data_version: str
    data_until: str
    n_simulations: int
    seed: int
    metrics: list[str]
    clubs: dict[str, ClubLabel]
    rounds: list[RoundViewInfo]
