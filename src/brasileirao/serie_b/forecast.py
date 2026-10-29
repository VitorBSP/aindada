"""Previsão da Série B: tabela por Monte Carlo (motor da Série A) + playoffs do Art. 13."""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from brasileirao.competition_rules.standings import rank_table
from brasileirao.config import MODEL_VERSION, ModelTrainingConfig
from brasileirao.contracts import MatchStatus
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.pipeline import ModelConfig, prepare_simulation
from brasileirao.serie_b.playoffs import pair_rates, simulate_playoffs
from brasileirao.serie_b.rules import SerieBRules
from brasileirao.serie_b.schema import (
    Clinched,
    PlayoffPairing,
    RemainingMatch,
    SerieBForecast,
    SourceCredit,
    TeamForecast,
)
from brasileirao.simulation.summary import position_distribution

IntArray = npt.NDArray[np.int64]

SERIE_B_MODEL_VERSION = f"serie-b-0.1.0+{MODEL_VERSION}"
SERIE_B_TRAINING = ModelTrainingConfig(first_training_season=2019)
PLAYOFF_SEED_STREAM = 3
GROUP_LABELS = ("A", "B", "C", "D")


def clinched_flags(points: IntArray, remaining: IntArray, rules: SerieBRules) -> list[Clinched]:
    """Condições suficientes, ignorando que os confrontos diretos ligam os pontos de dois clubes.

    Um clube termina abaixo de k rivais com certeza se k rivais já têm mais pontos do que ele pode
    alcançar; termina entre os k primeiros se no máximo k - 1 rivais ainda podem empatar ou passar.
    """
    max_points = points + rules.points_win * remaining
    n_clubs = len(points)
    playoff_last = max((worse for _, worse in rules.playoff_groups), default=rules.direct_promotion_count)
    safe_limit = n_clubs - rules.relegation_count
    flags = []
    for club in range(n_clubs):
        others = np.arange(n_clubs) != club
        surely_above = int((points[others] > max_points[club]).sum())
        can_reach = int((max_points[others] >= points[club]).sum())
        flags.append(
            Clinched(
                promoted_direct=can_reach <= rules.direct_promotion_count - 1,
                top6=can_reach <= playoff_last - 1,
                out_of_top2=surely_above >= rules.direct_promotion_count,
                out_of_top6=surely_above >= playoff_last,
                relegated=surely_above >= safe_limit,
                safe=can_reach <= safe_limit - 1,
            )
        )
    return flags


def data_version(sources: dict[str, Any]) -> str:
    tags = sorted(str(item["tag"]) for item in sources["sources"])
    return hashlib.sha256("|".join(tags).encode("utf-8")).hexdigest()[:12]


def build_forecast(
    matches_data: pd.DataFrame,
    sources: dict[str, Any],
    rules: SerieBRules,
    registry: ClubRegistry,
    model_config: ModelConfig,
    n_simulations: int,
    seed: int,
    backtest_summary: dict[str, object] | None = None,
) -> SerieBForecast:
    reference_date = date.fromisoformat(str(sources["reference_date"]))
    league_rules = rules.league_rules()
    prepared = prepare_simulation(
        matches_data, rules.season, reference_date, league_rules, model_config, None, SERIE_B_TRAINING
    )
    result = prepared.simulator.run(n_simulations, seed, model_config.dynamic_ratings, model_config.uncertainty)
    club_ids = result.club_ids
    state = prepared.engine.state
    rates = pair_rates(state, prepared.model, club_ids)
    playoffs = simulate_playoffs(
        result.final_order,
        rules.playoff_groups,
        rates,
        prepared.model,
        np.random.default_rng((seed, PLAYOFF_SEED_STREAM)),
    )
    distribution = position_distribution(result)
    n_clubs = len(club_ids)
    direct = rules.direct_promotion_count
    playoff_last = max(worse for _, worse in rules.playoff_groups)
    relegation_start = n_clubs - rules.relegation_count
    playoff_wins = np.zeros(n_clubs)
    for group in range(len(rules.playoff_groups)):
        playoff_wins += np.bincount(playoffs.winners[:, group], minlength=n_clubs)
    playoff_wins /= n_simulations

    table = result.observed_table
    order = rank_table(table, league_rules)
    remaining_counts = np.zeros(n_clubs, dtype=np.int64)
    for column in ("home_id", "away_id"):
        for club_id in result.remaining_matches[column]:
            remaining_counts[club_ids.index(str(club_id))] += 1
    flags = clinched_flags(table.points.astype(np.int64), remaining_counts, rules)

    teams = []
    for position, club_id in enumerate(order, start=1):
        club = club_ids.index(club_id)
        club_points = result.points[:, club]
        playoff_probability = float(distribution[club, direct:playoff_last].sum())
        teams.append(
            TeamForecast(
                club_id=club_id,
                name=registry.display_name(club_id),
                short_name=registry.clubs[club_id].short_name,
                position=position,
                played=int(table.played[club]),
                points=int(table.points[club]),
                wins=int(table.wins[club]),
                draws=int(table.draws[club]),
                losses=int(table.losses[club]),
                goals_for=int(table.goals_for[club]),
                goals_against=int(table.goals_against[club]),
                remaining=int(remaining_counts[club]),
                expected_points=float(club_points.mean()),
                points_interval_90=(float(np.percentile(club_points, 5)), float(np.percentile(club_points, 95))),
                expected_position=float(result.positions[:, club].mean() + 1),
                position_probabilities=[float(value) for value in distribution[club]],
                title=float(distribution[club, 0]),
                promotion_direct=float(distribution[club, :direct].sum()),
                playoff=playoff_probability,
                promotion_playoff=float(playoff_wins[club]),
                promotion=float(distribution[club, :direct].sum() + playoff_wins[club]),
                playoff_win_if_qualified=float(playoff_wins[club] / playoff_probability)
                if playoff_probability > 0
                else None,
                relegation=float(distribution[club, relegation_start:].sum()),
                clinched=flags[club],
                elo=float(state.ratings[club_id].elo),
            )
        )

    likely = []
    for group, (better_position, worse_position) in enumerate(rules.playoff_groups):
        pairs = Counter(zip(playoffs.better[:, group].tolist(), playoffs.worse[:, group].tolist(), strict=True))
        (better_club, worse_club), count = pairs.most_common(1)[0]
        selected = (playoffs.better[:, group] == better_club) & (playoffs.worse[:, group] == worse_club)
        likely.append(
            PlayoffPairing(
                group=GROUP_LABELS[group],
                better_position=better_position,
                worse_position=worse_position,
                better_club_id=club_ids[better_club],
                worse_club_id=club_ids[worse_club],
                probability=count / n_simulations,
                better_advances=float((playoffs.winners[selected, group] == better_club).mean()),
            )
        )

    remaining = []
    if len(result.remaining_matches):
        feature_rows = pd.DataFrame(
            [
                prepared.engine.pre_match_features(str(match.home_id), str(match.away_id))
                for match in result.remaining_matches.itertuples(index=False)
            ]
        )
        outcome = prepared.model.outcome_probabilities(feature_rows)
        home_rate, away_rate = prepared.model.expected_goals(feature_rows)
        for position, match in enumerate(result.remaining_matches.itertuples(index=False)):
            if str(match.status) == MatchStatus.FINISHED.value:
                continue
            remaining.append(
                RemainingMatch(
                    match_id=str(match.match_id),
                    home_id=str(match.home_id),
                    away_id=str(match.away_id),
                    p_home=float(outcome[position, 0]),
                    p_draw=float(outcome[position, 1]),
                    p_away=float(outcome[position, 2]),
                    expected_home_goals=float(home_rate[position]),
                    expected_away_goals=float(away_rate[position]),
                )
            )

    season_sources = {str(item["tag"]): item for item in sources["sources"]}
    return SerieBForecast(
        competition=rules.name,
        season=rules.season,
        reference_date=reference_date.isoformat(),
        generated_at=datetime.now(tz=UTC).isoformat(),
        n_simulations=n_simulations,
        seed=seed,
        observed_matches=len(result.observed_matches),
        remaining_matches=len(result.remaining_matches),
        model_version=SERIE_B_MODEL_VERSION,
        data_version=data_version(sources),
        regulation={"title": rules.regulation_title, "url": rules.regulation_url, "date": rules.regulation_date},
        rules={
            "direct_promotion": direct,
            "playoff_groups": [list(group) for group in rules.playoff_groups],
            "relegation": rules.relegation_count,
            "tiebreak_order": list(rules.tiebreak_order),
        },
        warnings=[
            "Sem dados de cartões: os critérios 5 e 6 do Art. 12 são substituídos por sorteio.",
            "A ordem dos jogos de 2026 não está na fonte; os ratings usam uma ordem aproximada.",
            "Datas dos jogos restantes não estão na fonte: o restante da temporada é simulado com ratings fixos.",
        ],
        sources=[
            SourceCredit(
                source_name=str(item["source_name"]),
                version=str(item["version"]),
                origin=str(item["origin"]),
                license_name=item.get("license_name"),
                attribution=item.get("attribution"),
                retrieved_at=str(item["retrieved_at"]),
            )
            for item in season_sources.values()
        ],
        teams=teams,
        likely_playoffs=likely,
        remaining=remaining,
        backtest=backtest_summary,
    )
