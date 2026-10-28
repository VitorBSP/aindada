"""Modelos de gols: Poisson independente (Modelo A), correção Dixon-Coles (Modelo B), inflação de empates e
dispersão dos gols (Conway-Maxwell-Poisson com média preservada)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import poisson
from sklearn.linear_model import PoissonRegressor

FloatArray = npt.NDArray[np.float64]

FEATURE_SETS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "intercept_only": ((), ()),
    "elo_only": (("elo_diff",), ("elo_diff",)),
    "attack_defense_only": (("ad_log_home",), ("ad_log_away",)),
    "elo_attack_defense": (("elo_diff", "ad_log_home"), ("elo_diff", "ad_log_away")),
    "full": (("elo_diff", "ad_log_home", "form_diff"), ("elo_diff", "ad_log_away", "form_diff")),
}

FEATURE_SCALES = {"elo_diff": 100.0, "ad_log_home": 1.0, "ad_log_away": 1.0, "form_diff": 1.0}


def _design(features: pd.DataFrame | dict[str, FloatArray], columns: tuple[str, ...]) -> FloatArray:
    if not columns:
        n_rows = len(next(iter(features.values()))) if isinstance(features, dict) else len(features)
        return np.zeros((n_rows, 0))
    return np.column_stack(
        [np.asarray(features[column], dtype=np.float64) / FEATURE_SCALES[column] for column in columns]
    )


def dixon_coles_tau(
    home_goals: npt.NDArray[np.int64],
    away_goals: npt.NDArray[np.int64],
    home_rate: FloatArray,
    away_rate: FloatArray,
    rho: float,
) -> FloatArray:
    tau = np.ones_like(home_rate, dtype=np.float64)
    tau = np.where((home_goals == 0) & (away_goals == 0), 1.0 - home_rate * away_rate * rho, tau)
    tau = np.where((home_goals == 0) & (away_goals == 1), 1.0 + home_rate * rho, tau)
    tau = np.where((home_goals == 1) & (away_goals == 0), 1.0 + away_rate * rho, tau)
    return np.where((home_goals == 1) & (away_goals == 1), 1.0 - rho, tau)


GOAL_DISPERSION_BOUNDS = (0.5, 2.0)
_LOG_LAMBDA_GRID = np.linspace(-8.0, 6.0, 7001)


def goal_pmf(rate: FloatArray, max_goals: int, dispersion: float = 1.0) -> FloatArray:
    """P(k gols), k = 0..max_goals, com shape (..., max_goals+1).

    `dispersion` é o ν do Conway-Maxwell-Poisson, P(k) ∝ λ^k / (k!)^ν: 1 reproduz a Poisson, ν > 1 dá
    variância menor que a média e ν < 1, maior. Para ν ≠ 1, λ é escolhido para que a média da
    distribuição (truncada em `max_goals`) seja igual a `rate`: o ν muda só a forma, não os gols esperados.
    """
    goals = np.arange(max_goals + 1)
    rates = np.asarray(rate, dtype=np.float64)
    if dispersion == 1.0:
        poisson_pmf: FloatArray = poisson.pmf(goals, rates[..., None])
        return poisson_pmf
    log_weights = -dispersion * gammaln(goals + 1.0)
    grid_logits = _LOG_LAMBDA_GRID[:, None] * goals[None, :] + log_weights[None, :]
    grid_probabilities = np.exp(grid_logits - grid_logits.max(axis=1, keepdims=True))
    grid_means = (grid_probabilities @ goals) / grid_probabilities.sum(axis=1)
    log_lambda = np.interp(rates, grid_means, _LOG_LAMBDA_GRID)
    logits = log_lambda[..., None] * goals + log_weights
    weights = np.exp(logits - logits.max(axis=-1, keepdims=True))
    pmf: FloatArray = weights / weights.sum(axis=-1, keepdims=True)
    return pmf


def score_matrix(
    home_rate: FloatArray,
    away_rate: FloatArray,
    rho: float,
    max_goals: int,
    draw_inflation: float = 0.0,
    goal_dispersion: float = 1.0,
) -> FloatArray:
    """Probabilidades de placar com shape (..., max_goals+1, max_goals+1), normalizadas.

    `draw_inflation` multiplica a diagonal (empates) por 1 + draw_inflation antes da normalização.
    `goal_dispersion` é o ν das marginais de gols (ver `goal_pmf`); 1 = Poisson.
    """
    home_pmf = goal_pmf(home_rate, max_goals, goal_dispersion)
    away_pmf = goal_pmf(away_rate, max_goals, goal_dispersion)
    matrix = home_pmf[..., :, None] * away_pmf[..., None, :]
    if rho != 0.0:
        home_rates = np.asarray(home_rate, dtype=np.float64)
        away_rates = np.asarray(away_rate, dtype=np.float64)
        matrix = matrix.copy()
        matrix[..., 0, 0] *= np.clip(1.0 - home_rates * away_rates * rho, 1e-9, None)
        matrix[..., 0, 1] *= np.clip(1.0 + home_rates * rho, 1e-9, None)
        matrix[..., 1, 0] *= np.clip(1.0 + away_rates * rho, 1e-9, None)
        matrix[..., 1, 1] *= max(1.0 - rho, 1e-9)
    if draw_inflation != 0.0:
        matrix = matrix.copy()
        diagonal = np.arange(max_goals + 1)
        matrix[..., diagonal, diagonal] *= 1.0 + draw_inflation
    normalized: FloatArray = matrix / matrix.sum(axis=(-2, -1), keepdims=True)
    return normalized


def top_scores(matrix: FloatArray, n_scores: int = 3) -> list[tuple[int, int, float]]:
    """Os `n_scores` placares mais prováveis de uma matriz (mandante, visitante, probabilidade).

    Ordem decrescente de probabilidade; empates exatos ficam na ordem da matriz (menos gols do
    mandante, depois menos gols do visitante), a mesma regra do `argmax` do placar mais provável.
    """
    flat = np.asarray(matrix, dtype=np.float64).reshape(-1)
    size = matrix.shape[-1]
    order = np.argsort(-flat, kind="stable")[:n_scores]
    return [(int(index // size), int(index % size), float(flat[index])) for index in order]


def total_goals_at_least(matrix: FloatArray, minimum_goals: int) -> FloatArray:
    """P(gols do mandante + gols do visitante >= minimum_goals), com shape (...)."""
    goals = np.arange(matrix.shape[-1])
    reaches_minimum = (goals[:, None] + goals[None, :]) >= minimum_goals
    probability: FloatArray = (matrix * reaches_minimum).sum(axis=(-2, -1))
    return probability


def outcome_probabilities(matrix: FloatArray) -> FloatArray:
    """(..., 3): vitória do mandante, empate, vitória do visitante."""
    home_win = np.tril(np.ones(matrix.shape[-2:]), k=-1)
    draw = np.eye(matrix.shape[-1])
    away_win = np.triu(np.ones(matrix.shape[-2:]), k=1)
    return np.stack(
        [
            (matrix * home_win).sum(axis=(-2, -1)),
            (matrix * draw).sum(axis=(-2, -1)),
            (matrix * away_win).sum(axis=(-2, -1)),
        ],
        axis=-1,
    )


def _coefficient_covariance(design: FloatArray, fitted_rate: FloatArray, alpha: float) -> list[list[float]]:
    """Inversa da informação de Fisher da regressão Poisson (intercepto + coeficientes penalizados)."""
    full_design = np.column_stack([np.ones(len(design)), design])
    information = full_design.T @ (full_design * fitted_rate[:, None])
    penalty = np.diag([0.0] + [alpha * len(design)] * design.shape[1])
    covariance: FloatArray = np.linalg.inv(information + penalty)
    return [[float(value) for value in row] for row in covariance]


def _sample_normal(
    intercept: float,
    coefficients: list[float],
    covariance: list[list[float]],
    n_draws: int,
    generator: np.random.Generator,
) -> FloatArray:
    mean = np.array([intercept, *coefficients], dtype=np.float64)
    if not covariance:
        return np.tile(mean, (n_draws, 1))
    draws: FloatArray = generator.multivariate_normal(mean, np.asarray(covariance), size=n_draws, method="cholesky")
    return draws


@dataclass
class GoalsModel:
    feature_set: str
    home_features: tuple[str, ...] = ()
    away_features: tuple[str, ...] = ()
    home_intercept: float = 0.0
    home_coefficients: list[float] = field(default_factory=list)
    away_intercept: float = 0.0
    away_coefficients: list[float] = field(default_factory=list)
    rho: float = 0.0
    draw_inflation: float = 0.0
    goal_dispersion: float = 1.0
    home_covariance: list[list[float]] = field(default_factory=list)
    away_covariance: list[list[float]] = field(default_factory=list)
    max_goals: int = 10
    training_seasons: list[int] = field(default_factory=list)
    n_training_matches: int = 0

    @classmethod
    def fit(
        cls,
        training_features: pd.DataFrame,
        feature_set: str = "full",
        alpha: float = 1e-3,
        dixon_coles: bool = True,
        max_goals: int = 10,
        draw_inflation: bool = False,
        goal_dispersion: bool = False,
    ) -> GoalsModel:
        home_columns, away_columns = FEATURE_SETS[feature_set]
        home_regressor = PoissonRegressor(alpha=alpha, max_iter=1000)
        away_regressor = PoissonRegressor(alpha=alpha, max_iter=1000)
        home_design = _design(training_features, home_columns)
        away_design = _design(training_features, away_columns)
        home_target = training_features["home_goals"].to_numpy(dtype=np.float64)
        away_target = training_features["away_goals"].to_numpy(dtype=np.float64)
        model = cls(
            feature_set=feature_set,
            home_features=home_columns,
            away_features=away_columns,
            max_goals=max_goals,
            training_seasons=sorted(int(season) for season in training_features["season"].unique()),
            n_training_matches=len(training_features),
        )
        if home_columns:
            home_regressor.fit(home_design, home_target)
            away_regressor.fit(away_design, away_target)
            model.home_intercept = float(home_regressor.intercept_)
            model.home_coefficients = [float(value) for value in home_regressor.coef_]
            model.away_intercept = float(away_regressor.intercept_)
            model.away_coefficients = [float(value) for value in away_regressor.coef_]
        else:
            model.home_intercept = float(np.log(home_target.mean()))
            model.away_intercept = float(np.log(away_target.mean()))
        fitted_home_rate, fitted_away_rate = model.expected_goals(training_features)
        model.home_covariance = _coefficient_covariance(home_design, fitted_home_rate, alpha)
        model.away_covariance = _coefficient_covariance(away_design, fitted_away_rate, alpha)
        if dixon_coles:
            model.rho = model.fit_rho(training_features)
        if goal_dispersion:
            model.goal_dispersion = model.fit_goal_dispersion(training_features)
        if draw_inflation:
            model.draw_inflation = model.fit_draw_inflation(training_features)
        return model

    def expected_goals(self, features: pd.DataFrame | dict[str, FloatArray]) -> tuple[FloatArray, FloatArray]:
        home_design = _design(features, self.home_features)
        away_design = _design(features, self.away_features)
        home_rate = np.exp(self.home_intercept + home_design @ np.asarray(self.home_coefficients or np.zeros(0)))
        away_rate = np.exp(self.away_intercept + away_design @ np.asarray(self.away_coefficients or np.zeros(0)))
        return home_rate, away_rate

    def fit_rho(self, training_features: pd.DataFrame) -> float:
        home_rate, away_rate = self.expected_goals(training_features)
        home_goals = training_features["home_goals"].to_numpy(dtype=np.int64)
        away_goals = training_features["away_goals"].to_numpy(dtype=np.int64)

        def negative_log_likelihood(rho: float) -> float:
            tau = dixon_coles_tau(home_goals, away_goals, home_rate, away_rate, rho)
            if np.any(tau <= 0):
                return float("inf")
            return float(-np.sum(np.log(tau)))

        optimum = minimize_scalar(negative_log_likelihood, bounds=(-0.25, 0.25), method="bounded")
        return float(optimum.x)

    def fit_draw_inflation(self, training_features: pd.DataFrame) -> float:
        """Máxima verossimilhança do placar observado, com os demais parâmetros fixos."""
        home_rate, away_rate = self.expected_goals(training_features)
        home_goals = np.minimum(training_features["home_goals"].to_numpy(dtype=np.int64), self.max_goals)
        away_goals = np.minimum(training_features["away_goals"].to_numpy(dtype=np.int64), self.max_goals)
        rows = np.arange(len(home_goals))

        def negative_log_likelihood(draw_inflation: float) -> float:
            matrix = score_matrix(home_rate, away_rate, self.rho, self.max_goals, draw_inflation, self.goal_dispersion)
            return float(-np.sum(np.log(matrix[rows, home_goals, away_goals])))

        optimum = minimize_scalar(negative_log_likelihood, bounds=(-0.5, 1.0), method="bounded")
        return float(optimum.x)

    def fit_goal_dispersion(self, training_features: pd.DataFrame) -> float:
        """ν por máxima verossimilhança do placar observado, com médias (regressões) e ρ fixos."""
        home_rate, away_rate = self.expected_goals(training_features)
        home_goals = np.minimum(training_features["home_goals"].to_numpy(dtype=np.int64), self.max_goals)
        away_goals = np.minimum(training_features["away_goals"].to_numpy(dtype=np.int64), self.max_goals)
        rows = np.arange(len(home_goals))

        def negative_log_likelihood(dispersion: float) -> float:
            matrix = score_matrix(home_rate, away_rate, self.rho, self.max_goals, self.draw_inflation, dispersion)
            return float(-np.sum(np.log(matrix[rows, home_goals, away_goals])))

        optimum = minimize_scalar(negative_log_likelihood, bounds=GOAL_DISPERSION_BOUNDS, method="bounded")
        return float(optimum.x)

    def sample_parameters(self, n_draws: int, generator: np.random.Generator) -> tuple[FloatArray, FloatArray]:
        """Sorteios (intercepto, coeficientes) da normal assintótica, com shape (n_draws, 1 + p)."""
        return (
            _sample_normal(self.home_intercept, self.home_coefficients, self.home_covariance, n_draws, generator),
            _sample_normal(self.away_intercept, self.away_coefficients, self.away_covariance, n_draws, generator),
        )

    def expected_goals_by_draw(
        self,
        features: pd.DataFrame | dict[str, FloatArray],
        home_parameters: FloatArray,
        away_parameters: FloatArray,
    ) -> tuple[FloatArray, FloatArray]:
        """Gols esperados (n_draws, n_rows / n_draws): linha i das features usa o sorteio i // n_rows."""
        n_draws = len(home_parameters)
        home_design = _design(features, self.home_features).reshape(n_draws, -1, len(self.home_features))
        away_design = _design(features, self.away_features).reshape(n_draws, -1, len(self.away_features))
        home_log_rate = home_parameters[:, :1] + np.einsum("srp,sp->sr", home_design, home_parameters[:, 1:])
        away_log_rate = away_parameters[:, :1] + np.einsum("srp,sp->sr", away_design, away_parameters[:, 1:])
        return np.exp(home_log_rate), np.exp(away_log_rate)

    def score_probabilities(self, features: pd.DataFrame | dict[str, FloatArray]) -> FloatArray:
        home_rate, away_rate = self.expected_goals(features)
        return score_matrix(home_rate, away_rate, self.rho, self.max_goals, self.draw_inflation, self.goal_dispersion)

    def outcome_probabilities(self, features: pd.DataFrame | dict[str, FloatArray]) -> FloatArray:
        return outcome_probabilities(self.score_probabilities(features))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
