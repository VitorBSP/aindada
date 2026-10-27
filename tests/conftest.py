from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from brasileirao.competition_rules.season_rules import ExternalContext, SeasonRules, load_season_rules
from brasileirao.data_pipeline.clubs import ClubRegistry, load_club_registry
from tests.fixtures.synthetic import SYNTHETIC_CLUBS_CSV, synthetic_history


@pytest.fixture(scope="session")
def rules_2026() -> SeasonRules:
    return load_season_rules(2026)


@pytest.fixture(scope="session")
def synthetic_rules(rules_2026: SeasonRules) -> SeasonRules:
    external = ExternalContext(
        as_of="2032-10-01",
        libertadores_champion="",
        libertadores_finalists=("sintetico-03", "foreign:Estrangeiro FC"),
        sudamericana_champion="",
        sudamericana_finalists=(),
        cup_champion="",
        cup_runner_up="",
        cup_semifinals=(("sintetico-03", "sintetico-10"), ("sintetico-15", "sintetico-20")),
        notes=("cenário sintético",),
        sources=(),
    )
    return replace(rules_2026, season=2032, external=external)


@pytest.fixture(scope="session")
def synthetic_matches() -> pd.DataFrame:
    return synthetic_history()


@pytest.fixture(scope="session")
def synthetic_registry() -> ClubRegistry:
    return load_club_registry(SYNTHETIC_CLUBS_CSV)


@pytest.fixture(scope="session")
def real_registry() -> ClubRegistry:
    return load_club_registry()


@pytest.fixture
def twenty_clubs() -> list[str]:
    return [f"c{index:02d}" for index in range(1, 21)]
