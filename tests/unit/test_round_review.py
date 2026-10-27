"""Revisão rodada a rodada: cortes, atribuição por jogo e decomposição (Agente 06)."""

from __future__ import annotations

import itertools
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from brasileirao.competition_rules.season_rules import SeasonRules
from brasileirao.config import RatingParams
from brasileirao.prediction.goals_model import GoalsModel
from brasileirao.ratings.history import build_state_as_of
from brasileirao.simulation.engine import SeasonSimulator, SimulationResult
from brasileirao.simulation.round_review import (
    METRICS,
    MatchImpact,
    Mover,
    RoundCutoff,
    build_round_view,
    match_impacts,
    metric_difference,
    played_between,
    round_cutoffs,
    summarize_round,
    team_metrics,
)

SEASON = 2032


def _season(matches: pd.DataFrame) -> pd.DataFrame:
    return matches[matches["season"] == SEASON]


def _round_start(matches: pd.DataFrame, round_number: int) -> date:
    season = _season(matches)
    return pd.Timestamp(season.loc[season["round"] == round_number, "match_date"].min()).date()


def _simulate(
    matches: pd.DataFrame, rules: SeasonRules, reference: date, n_simulations: int = 3000
) -> SimulationResult:
    params = RatingParams()
    engine, features = build_state_as_of(matches, reference, SEASON, params)
    model = GoalsModel.fit(features[features["season"] < SEASON], "elo_attack_defense")
    simulator = SeasonSimulator(_season(matches), reference, engine.state, model, params, rules)
    return simulator.run(n_simulations, seed=4)


@pytest.fixture(scope="module")
def pre_round_two(synthetic_matches: pd.DataFrame) -> date:
    return _round_start(synthetic_matches, 2) - timedelta(days=1)


@pytest.fixture(scope="module")
def before_round_two(
    synthetic_matches: pd.DataFrame, synthetic_rules: SeasonRules, pre_round_two: date
) -> SimulationResult:
    return _simulate(synthetic_matches, synthetic_rules, pre_round_two)


@pytest.fixture(scope="module")
def round_two_matches(synthetic_matches: pd.DataFrame, pre_round_two: date) -> pd.DataFrame:
    return played_between(
        _season(synthetic_matches), pre_round_two, _round_start(synthetic_matches, 3) - timedelta(days=1)
    )


def test_first_cutoff_is_pre_season(synthetic_matches: pd.DataFrame) -> None:
    first = round_cutoffs(_season(synthetic_matches), date(2032, 12, 31))[0]
    assert first == RoundCutoff(0, _round_start(synthetic_matches, 1) - timedelta(days=1), False)


def test_cutoffs_are_strictly_increasing(synthetic_matches: pd.DataFrame) -> None:
    dates = [cutoff.reference_date for cutoff in round_cutoffs(_season(synthetic_matches), date(2032, 12, 31))]
    assert all(later > earlier for earlier, later in itertools.pairwise(dates))


def test_cutoff_before_next_round_is_partial(synthetic_matches: pd.DataFrame) -> None:
    mid_round = _round_start(synthetic_matches, 3)
    assert round_cutoffs(_season(synthetic_matches), mid_round)[-1].partial


def test_cutoffs_stop_at_data_date(synthetic_matches: pd.DataFrame) -> None:
    data_until = _round_start(synthetic_matches, 3)
    assert round_cutoffs(_season(synthetic_matches), data_until)[-1].reference_date == data_until


def test_played_between_excludes_previous_window(synthetic_matches: pd.DataFrame, pre_round_two: date) -> None:
    window = played_between(_season(synthetic_matches), pre_round_two, _round_start(synthetic_matches, 3))
    assert (window["match_date"].dt.date > pre_round_two).all()


def test_impacts_cover_every_played_match(
    before_round_two: SimulationResult, synthetic_rules: SeasonRules, round_two_matches: pd.DataFrame
) -> None:
    assert len(match_impacts(before_round_two, synthetic_rules, round_two_matches)) == len(round_two_matches)


def test_impacts_average_to_zero_over_outcomes(
    before_round_two: SimulationResult, synthetic_rules: SeasonRules, round_two_matches: pd.DataFrame
) -> None:
    """Lei da probabilidade total: Σ P(resultado) · [P(X | resultado) − P(X)] = 0."""
    one_match = round_two_matches.head(1)
    weighted = np.zeros(len(before_round_two.club_ids))
    for home_goals, away_goals in ((2, 0), (1, 1), (0, 2)):
        scored = one_match.assign(home_goals=home_goals, away_goals=away_goals)
        impact = match_impacts(before_round_two, synthetic_rules, scored)[0]
        weighted += impact.outcome_probability * np.array(
            [impact.impacts[club]["title"] for club in before_round_two.club_ids]
        )
    assert np.allclose(weighted, 0.0, atol=1e-4)


def test_stakes_bound_actual_impact(
    before_round_two: SimulationResult, synthetic_rules: SeasonRules, round_two_matches: pd.DataFrame
) -> None:
    impact = match_impacts(before_round_two, synthetic_rules, round_two_matches)[0]
    assert all(
        abs(impact.impacts[club][metric]) <= impact.stakes[club][metric] + 1e-9
        for club in impact.impacts
        for metric in METRICS
    )


def test_title_probabilities_sum_to_one(before_round_two: SimulationResult, synthetic_rules: SeasonRules) -> None:
    teams = team_metrics(before_round_two, synthetic_rules)
    assert sum(values["title"] for values in teams.values()) == pytest.approx(1.0)


def test_round_view_decomposition_is_exact(
    synthetic_matches: pd.DataFrame,
    synthetic_rules: SeasonRules,
    before_round_two: SimulationResult,
    pre_round_two: date,
) -> None:
    after = _round_start(synthetic_matches, 3) - timedelta(days=1)
    previous_cutoff = RoundCutoff(1, pre_round_two, False)
    previous_view = build_round_view(
        previous_cutoff, before_round_two, synthetic_rules, None, _season(synthetic_matches)
    )
    current = _simulate(synthetic_matches, synthetic_rules, after)
    view = build_round_view(
        RoundCutoff(2, after, False),
        current,
        synthetic_rules,
        (previous_view, before_round_two),
        _season(synthetic_matches),
        results_only=current,
    )
    recomposed = {
        club: {metric: view.results_effect[club][metric] + view.strength_effect[club][metric] for metric in METRICS}
        for club in view.changes
    }
    assert all(
        recomposed[club][metric] == pytest.approx(view.changes[club][metric], abs=1e-4)
        for club in view.changes
        for metric in METRICS
    )


def test_pre_season_view_has_no_summary(
    synthetic_matches: pd.DataFrame, synthetic_rules: SeasonRules, before_round_two: SimulationResult
) -> None:
    view = build_round_view(
        RoundCutoff(0, date(2032, 1, 1), False), before_round_two, synthetic_rules, None, _season(synthetic_matches)
    )
    assert view.summary is None


def test_metric_difference_subtracts() -> None:
    difference = metric_difference(
        {"a": {"title": 0.5, "top4": 0.9, "relegation": 0.0}}, {"a": {"title": 0.2, "top4": 0.9, "relegation": 0.1}}
    )
    assert difference == {"a": {"title": 0.3, "top4": 0.0, "relegation": -0.1}}


def _impact(match_id: str, outcome_probability: float, title_delta: float) -> MatchImpact:
    return MatchImpact(
        match_id=match_id,
        round=1,
        match_date="2032-01-01",
        home_id="a",
        away_id="b",
        home_goals=1,
        away_goals=0,
        outcome="home",
        pre_match={"home": outcome_probability, "draw": 0.0, "away": 1 - outcome_probability},
        impacts={"a": {"title": title_delta, "top4": 0.0, "relegation": 0.0}},
        stakes={"a": {"title": abs(title_delta), "top4": 0.0, "relegation": 0.0}},
    )


def test_summary_picks_largest_impact_as_decisive() -> None:
    changes = {"a": {"title": 0.1, "top4": 0.0, "relegation": 0.0}}
    impacts = [_impact("pequeno", 0.5, 0.01), _impact("grande", 0.9, 0.2)]
    summary = summarize_round(changes, impacts, changes, changes, changes, dict.fromkeys(METRICS, 0.0))
    assert summary.decisive_match_id == "grande"


def test_summary_picks_least_likely_result_as_surprise() -> None:
    changes = {"a": {"title": 0.1, "top4": 0.0, "relegation": 0.0}}
    impacts = [_impact("zebra", 0.1, 0.01), _impact("esperado", 0.9, 0.2)]
    summary = summarize_round(changes, impacts, changes, changes, changes, dict.fromkeys(METRICS, 0.0))
    assert summary.surprise_match_id == "zebra"


def test_summary_lists_only_positive_risers() -> None:
    changes = {
        "a": {"title": 0.2, "top4": 0.0, "relegation": 0.0},
        "b": {"title": -0.2, "top4": 0.0, "relegation": 0.0},
    }
    summary = summarize_round(changes, [], changes, changes, changes, dict.fromkeys(METRICS, 0.0))
    assert summary.risers["title"] == [Mover("a", 0.2)]


def test_team_metrics_include_observed_standing(
    before_round_two: SimulationResult, synthetic_rules: SeasonRules
) -> None:
    teams = team_metrics(before_round_two, synthetic_rules)
    assert sorted(values["position"] for values in teams.values()) == [float(position) for position in range(1, 21)]
