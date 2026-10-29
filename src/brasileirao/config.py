"""Configuração central do projeto."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

MODEL_VERSION = "cmp-elo-ad-0.3.0"
SNAPSHOT_SCHEMA_VERSION = "1.3"
ROUND_REVIEW_SCHEMA_VERSION = "1.1"
CURRENT_ROUND_SCHEMA_VERSION = "1.0"

# Rodada atual (ADR-0009, Decisão 3): jogo na janela fica a até ROUND_WINDOW_DAYS dias da âncora da rodada;
# jogo `scheduled` sem placar conta como resolvido STALE_RESULT_HOURS horas depois do início.
ROUND_WINDOW_DAYS = 4
STALE_RESULT_HOURS = 48
INSIGHT_RULES_VERSION = "rules-2026.10.1"

# Fonte de publicação por temporada (primeira, última ou None = em aberto, source_name). ADR-0008, Decisão 1.
# Temporada fora da tabela não tem fonte e faz a ingestão falhar; não há fallback.
PUBLICATION_SOURCE_BY_SEASON: tuple[tuple[int, int | None, str], ...] = (
    (2003, 2025, "adaoduque_kaggle"),
    (2026, None, "football_data_org"),
)


def _project_root() -> Path:
    env_root = os.environ.get("BRASILEIRAO_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ProjectPaths:
    root: Path = field(default_factory=_project_root)

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def silver(self) -> Path:
        return self.data / "silver"

    @property
    def gold(self) -> Path:
        return self.data / "gold"

    @property
    def reference(self) -> Path:
        return self.data / "reference"

    @property
    def snapshots_db(self) -> Path:
        return Path(os.environ.get("BRASILEIRAO_SNAPSHOT_DB", self.data / "snapshots" / "snapshots.sqlite"))

    @property
    def web_static_data(self) -> Path:
        return self.root / "apps" / "web" / "data"

    @property
    def clubs_reference(self) -> Path:
        return self.reference / "clubs.csv"

    @property
    def editorial(self) -> Path:
        return Path(os.environ.get("BRASILEIRAO_EDITORIAL_DIR", self.data / "editorial"))

    @property
    def insight_criteria(self) -> Path:
        return self.root / "docs" / "storytelling" / "contracts" / "insight-criteria.toml"

    @property
    def serie_b_data(self) -> Path:
        """Raw, silver e snapshot da Série B (ADR-0010); fora do git como `data/raw/` e `data/silver/`."""
        return Path(os.environ.get("BRASILEIRAO_SERIE_B_DIR", self.data / "serie_b"))

    @property
    def serie_b_clubs_reference(self) -> Path:
        return self.reference / "clubs_serie_b.csv"

    @property
    def serie_b_source_pins(self) -> Path:
        return self.reference / "serie_b_source_pins.json"

    @property
    def serie_b_web_static_data(self) -> Path:
        return self.root / "apps" / "web-serie-b" / "data"

    def league_data(self, code: str) -> Path:
        """Raw, silver e previsão de uma liga europeia (ADR-0011); fora do git."""
        return Path(os.environ.get("BRASILEIRAO_LEAGUES_DIR", self.data / "leagues")) / code

    @property
    def league_source_pins(self) -> Path:
        return self.reference / "league_source_pins.json"

    @property
    def league_web_app(self) -> Path:
        """App único das ligas europeias; cada liga é publicada em `/<código>/` com o seu `data/forecast.json`."""
        return self.root / "apps" / "web-ligas"


@dataclass(frozen=True)
class EloParams:
    k_factor: float = 20.0
    home_advantage: float = 70.0
    season_regression: float = 0.25
    initial_rating: float = 1500.0
    promoted_offset: float = 0.0


@dataclass(frozen=True)
class AttackDefenseParams:
    learning_rate: float = 0.03
    season_regression: float = 0.3
    global_learning_rate: float = 0.002
    initial_log_goal_rate: float = 0.1
    initial_home_effect: float = 0.3


@dataclass(frozen=True)
class FormParams:
    span_matches: int = 6


@dataclass(frozen=True)
class RatingParams:
    elo: EloParams = field(default_factory=EloParams)
    attack_defense: AttackDefenseParams = field(default_factory=AttackDefenseParams)
    form: FormParams = field(default_factory=FormParams)


@dataclass(frozen=True)
class SimulationUncertainty:
    """Incerteza propagada em cada simulação.

    `coefficient_draws` sorteia os coeficientes do modelo de gols da normal assintótica;
    `strength_sd` soma a cada clube uma força latente N(0, sd²) na escala log dos gols,
    fixa ao longo da temporada simulada.
    """

    coefficient_draws: bool = False
    strength_sd: float = 0.0


@dataclass(frozen=True)
class ModelTrainingConfig:
    training_seasons_window: int = 10
    first_training_season: int = 2006
    poisson_alpha: float = 1e-3
    max_goals: int = 10


@dataclass(frozen=True)
class SimulationConfig:
    """`round_review_simulations` fica abaixo de `n_simulations`: a revisão roda duas simulações da
    temporada inteira por rodada (~25 min com 10 mil; ~4 h estimadas com 100 mil)."""

    n_simulations: int = 100_000
    seed: int = 2026
    dynamic_ratings: bool = True
    round_review_simulations: int = 20_000


PATHS = ProjectPaths()
