"""Champions League (ADR-0012). Todos os dados são sintéticos (synthetic)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from brasileirao.europe.forecast import KnockoutStartedError, ensure_league_phase_only
from brasileirao.europe.ratings import GlobalElo, GlobalEloParams
from brasileirao.europe.simulation import STAGES, ChampionsSimulator, LeaguePhase
from brasileirao.europe.sources import parse_cup
from brasileirao.prediction.goals_model import GoalsModel

CUP_SYNTHETIC = """= Copa sintética (synthetic)

▪ League, Matchday 1
  Tue Sep 16 2040
    21:00  Alfa FC (ENG)           v Beta CF (ESP)            2-1 (1-0)
           Gama SC (POR)           v Delta AC (ITA)           0-3    [awarded]
▪ Finals, Final
  Sat May 31 2041
    21:00  Alfa FC (ENG)           v Beta CF (ESP)            4-2 pen. 1-1 a.e.t. (1-1, 0-1)
"""


def test_cup_parser_keeps_country_and_90_minute_score() -> None:
    first = parse_cup(CUP_SYNTHETIC, "CL", 2040)[0]
    assert (first.home_country, first.home_goals, first.away_goals) == ("ENG", 2, 1)


def test_cup_parser_skips_awarded_result() -> None:
    assert len(parse_cup(CUP_SYNTHETIC, "CL", 2040)) == 2


def test_cup_parser_reads_extra_time_and_penalties() -> None:
    final = parse_cup(CUP_SYNTHETIC, "CL", 2040)[1]
    assert (final.home_goals, final.extra_time, final.penalties, final.match_date) == (
        1,
        (1, 1),
        (4, 2),
        date(2041, 5, 31),
    )


def _matches(rows: list[tuple[str, int, str, str, str, int, int, bool]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "match_id": f"m{index}",
                "match_date": pd.Timestamp(day),
                "season": season,
                "competition": competition,
                "home_id": home,
                "away_id": away,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "neutral": neutral,
                "status": "finished",
            }
            for index, (day, season, competition, home, away, home_goals, away_goals, neutral) in enumerate(rows)
        ]
    )


COUNTRIES = {"a1": "ENG", "a2": "ENG", "a3": "ENG", "a4": "ENG", "b1": "SCO"}


def test_first_season_domestic_clubs_start_equal() -> None:
    engine = GlobalElo(GlobalEloParams(), COUNTRIES)
    features = engine.run(
        _matches(
            [("2030-08-01", 2030, "ENG", "a1", "a2", 1, 0, False), ("2030-08-01", 2030, "ENG", "a3", "a4", 0, 0, False)]
        )
    )
    assert features["elo_diff"].tolist() == [60.0, 60.0]


def test_unknown_country_starts_below_base() -> None:
    engine = GlobalElo(GlobalEloParams(unknown_offset=150.0), COUNTRIES)
    engine.run(_matches([("2030-09-01", 2030, "CL", "a1", "b1", 1, 1, False)]))
    assert engine.state.ratings["b1"] < 1500.0


def test_neutral_match_has_no_home_advantage() -> None:
    engine = GlobalElo(GlobalEloParams(), COUNTRIES)
    features = engine.run(_matches([("2030-08-01", 2030, "ENG", "a1", "a2", 1, 1, True)]))
    assert features["elo_diff"].iloc[0] == 0.0


def test_promoted_club_starts_below_country_mean() -> None:
    engine = GlobalElo(GlobalEloParams(newcomer_offset=100.0, season_regression=0.0), COUNTRIES)
    engine.run(
        _matches(
            [
                ("2030-08-01", 2030, "ENG", "a1", "a2", 0, 0, False),
                ("2030-08-01", 2030, "ENG", "a3", "a2", 0, 0, False),
                ("2031-08-01", 2031, "ENG", "a4", "a1", 0, 0, False),
            ]
        )
    )
    assert engine.state.ratings["a4"] < 1500.0 - 90.0


def _league(n_clubs: int = 36, played_rounds: int = 3) -> tuple[LeaguePhase, dict[str, float]]:
    clubs = [f"c{index:02d}" for index in range(n_clubs)]
    rows = []
    generator = np.random.default_rng(5)
    for round_number in range(8):
        shift = round_number + 1
        for index in range(0, n_clubs, 2):
            home, away = clubs[(index + shift) % n_clubs], clubs[(index + shift + 1) % n_clubs]
            if round_number % 2:
                home, away = away, home
            played = round_number < played_rounds
            rows.append(
                {
                    "match_id": f"r{round_number}-{index}",
                    "home_id": home,
                    "away_id": away,
                    "home_goals": int(generator.integers(0, 4)) if played else None,
                    "away_goals": int(generator.integers(0, 4)) if played else None,
                    "round": round_number + 1,
                }
            )
    frame = pd.DataFrame(rows)
    observed = frame[frame["round"] <= played_rounds]
    remaining = frame[frame["round"] > played_rounds]
    ratings = {club: 1500.0 + 10.0 * (n_clubs - index) for index, club in enumerate(clubs)}
    return LeaguePhase(tuple(sorted(clubs)), observed, remaining), ratings


def _model() -> GoalsModel:
    return GoalsModel(
        feature_set="elo_only",
        home_features=("elo_diff",),
        away_features=("elo_diff",),
        home_intercept=0.3,
        home_coefficients=[0.4],
        away_intercept=0.1,
        away_coefficients=[-0.4],
        max_goals=8,
    )


@pytest.fixture(scope="module")
def simulation():  # type: ignore[no-untyped-def]
    phase, ratings = _league()
    return ChampionsSimulator(phase, ratings, _model(), 60.0).run(2000, 3)


def test_stage_totals_follow_the_bracket(simulation) -> None:  # type: ignore[no-untyped-def]
    totals = [round(float(simulation.stage_counts[stage].sum()), 6) for stage in STAGES]
    assert totals == [16.0, 8.0, 4.0, 2.0, 1.0]


def test_each_position_has_one_club(simulation) -> None:  # type: ignore[no-untyped-def]
    assert (np.sort(simulation.positions, axis=1) == np.arange(36)).all()


def test_stronger_club_wins_more_often(simulation) -> None:  # type: ignore[no-untyped-def]
    winners = simulation.stage_counts["winner"]
    assert winners[0] > winners[-1]


def test_away_goals_break_a_tie_in_the_league_phase() -> None:
    observed = pd.DataFrame(
        [
            {"home_id": "x", "away_id": "z1", "home_goals": 1, "away_goals": 0},
            {"home_id": "z2", "away_id": "y", "home_goals": 0, "away_goals": 1},
        ]
    )
    phase = LeaguePhase(("x", "y", "z1", "z2"), observed, observed.iloc[0:0])
    simulator = ChampionsSimulator(phase, {club: 1500.0 for club in phase.club_ids}, _model(), 60.0)
    order, _ = simulator._league_phase(50, np.random.default_rng(1))
    assert (order[:, 0] == phase.club_ids.index("y")).all()


def test_forecast_refuses_to_run_once_the_real_knockout_exists() -> None:
    champions = pd.DataFrame({"stage": ["LEAGUE_STAGE", "PLAYOFFS"]})
    with pytest.raises(KnockoutStartedError):
        ensure_league_phase_only(champions)
