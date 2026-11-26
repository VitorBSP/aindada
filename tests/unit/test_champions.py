"""Champions League (ADR-0012). Todos os dados são sintéticos (synthetic)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from brasileirao.contracts import Club
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.europe.forecast import build_forecast, current_stage, knockout_ties
from brasileirao.europe.gate import check_forecast_core, check_knockout
from brasileirao.europe.ingest import current_records, decided_score
from brasileirao.europe.knockout import (
    PLAYOFF_SECTIONS,
    ROUND_OF_16_SECTIONS,
    KnockoutFormatError,
    check_progression,
    consistent_configs,
    read_knockout,
)
from brasileirao.europe.ratings import GlobalElo, GlobalEloParams
from brasileirao.europe.simulation import STAGES, ChampionsSimulation, ChampionsSimulator, LeaguePhase
from brasileirao.europe.sources import parse_cup
from brasileirao.leagues.sources import SourceFormatError
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


# ---------------------------------------------------------------- Mata-mata real (sintético)

REFERENCE = pd.Timestamp("2041-03-20")
KNOCKOUT_DAYS = {
    "PLAYOFFS": ("2041-02-10", "2041-02-17"),
    "LAST_16": ("2041-03-03", "2041-03-10"),
    "QUARTER_FINALS": ("2041-04-07", "2041-04-14"),
    "SEMI_FINALS": ("2041-04-28", "2041-05-05"),
}


def _league_rows(phase: LeaguePhase) -> list[dict[str, object]]:
    rows = []
    for match in pd.concat([phase.observed, phase.remaining]).itertuples(index=False):
        played = match.home_goals is not None and not pd.isna(match.home_goals)
        rows.append(
            {
                "match_id": match.match_id,
                "stage": "LEAGUE_STAGE",
                "round": int(match.round),
                "match_date": pd.Timestamp("2040-10-01") + pd.Timedelta(days=7 * int(match.round)),
                "home_id": match.home_id,
                "away_id": match.away_id,
                "home_goals": match.home_goals if played else None,
                "away_goals": match.away_goals if played else None,
                "status": "finished" if played else "scheduled",
            }
        )
    return rows


def _leg(stage: str, number: int, home: str, away: str, score: tuple[int, int] | None,
         extra: tuple[int, int] | None = None, penalties: tuple[int, int] | None = None,
         day: str | None = None) -> dict[str, object]:  # fmt: skip
    return {
        "match_id": f"{stage}-{home}-{away}-{number}",
        "stage": stage,
        "match_date": pd.Timestamp(day or KNOCKOUT_DAYS[stage][number - 1]),
        "home_id": home,
        "away_id": away,
        "home_goals": None if score is None else score[0],
        "away_goals": None if score is None else score[1],
        "extra_time_home": None if extra is None else extra[0],
        "extra_time_away": None if extra is None else extra[1],
        "penalties_home": None if penalties is None else penalties[0],
        "penalties_away": None if penalties is None else penalties[1],
        "status": "scheduled" if score is None else "finished",
    }


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in ("extra_time_home", "extra_time_away", "penalties_home", "penalties_away", "kickoff_utc"):
        if column not in frame:
            frame[column] = None
    for column in (
        "home_goals",
        "away_goals",
        "extra_time_home",
        "extra_time_away",
        "penalties_home",
        "penalties_away",
    ):
        frame[column] = frame[column].astype("Int64")
    return frame


@pytest.fixture(scope="module")
def complete_league() -> tuple[ChampionsSimulator, dict[int, str]]:
    phase, ratings = _league(played_rounds=8)
    simulator = ChampionsSimulator(phase, ratings, _model(), 60.0)
    order = simulator.final_league_order()
    return simulator, {rank: phase.club_ids[club] for rank, club in enumerate(order, start=1)}


def _playoff_pairs(at: dict[int, str]) -> list[tuple[str, str]]:
    """Configuração 0: cabeça k contra não cabeça k; (mandante da ida = pior colocado, mandante da volta)."""
    return [(at[unseeded[slot]], at[seeds[slot]]) for seeds, unseeded in PLAYOFF_SECTIONS for slot in (0, 1)]


def _round_of_16_pairs(at: dict[int, str], playoff_winners: dict[int, str]) -> list[tuple[str, str]]:
    """Seção com seeds (a, b) e seção do playoff p: a contra o vencedor do confronto do cabeça a da seção p."""
    pairs = []
    for seeds, playoff_section in ROUND_OF_16_SECTIONS:
        for slot in (0, 1):
            pairs.append((playoff_winners[PLAYOFF_SECTIONS[playoff_section][0][slot]], at[seeds[slot]]))
    return pairs


def _state(simulator: ChampionsSimulator, rows: list[dict[str, object]], reference: pd.Timestamp = REFERENCE
           ) -> tuple[pd.DataFrame, dict[str, list], dict[str, int]]:  # fmt: skip
    champions = _frame(_league_rows(simulator.phase) + rows)
    ties, done = knockout_ties(champions, reference)
    assert done
    order = simulator.final_league_order()
    position = {simulator.phase.club_ids[club]: rank for rank, club in enumerate(order, start=1)}
    check_progression(ties, position)
    return champions, ties, position


def _run(simulator: ChampionsSimulator, ties: dict[str, list], position: dict[str, int]) -> ChampionsSimulation:
    return simulator.run_knockout(4000, 11, ties, consistent_configs(ties, position))


def _stage(result: ChampionsSimulation, stage: str, club: str) -> float:
    return float(result.stage_counts[stage][result.club_ids.index(club)])


@pytest.fixture(scope="module")
def mid_playoffs(complete_league):  # type: ignore[no-untyped-def]
    """Idas do playoff disputadas; o 23º fez 0 x 4 em casa contra o 9º."""
    simulator, at = complete_league
    rows = []
    for index, (host_first, host_second) in enumerate(_playoff_pairs(at)):
        rows.append(_leg("PLAYOFFS", 1, host_first, host_second, (0, 4) if index == 0 else (1, 1)))
        rows.append(_leg("PLAYOFFS", 2, host_second, host_first, None))
    _, ties, position = _state(simulator, rows)
    return simulator, at, ties, position, _run(simulator, ties, position)


def test_mid_playoffs_keeps_the_bracket_totals(mid_playoffs) -> None:  # type: ignore[no-untyped-def]
    result = mid_playoffs[4]
    assert [round(float(result.stage_counts[stage].sum()), 6) for stage in STAGES] == [16.0, 8.0, 4.0, 2.0, 1.0]


def test_mid_playoffs_top8_is_already_in_the_round_of_16(mid_playoffs) -> None:  # type: ignore[no-untyped-def]
    result, at = mid_playoffs[4], mid_playoffs[1]
    assert all(_stage(result, "round_of_16", at[rank]) == 1.0 for rank in range(1, 9))


def test_mid_playoffs_eliminated_clubs_never_play_the_knockout(mid_playoffs) -> None:  # type: ignore[no-untyped-def]
    result, at = mid_playoffs[4], mid_playoffs[1]
    assert sum(_stage(result, "round_of_16", at[rank]) for rank in range(25, 37)) == 0.0


def test_four_goal_first_leg_lead_makes_the_ninth_a_big_favourite(mid_playoffs) -> None:  # type: ignore[no-untyped-def]
    result, at = mid_playoffs[4], mid_playoffs[1]
    assert _stage(result, "round_of_16", at[9]) > 0.95


def test_known_playoff_draw_fixes_the_playoff_bits(mid_playoffs) -> None:  # type: ignore[no-untyped-def]
    assert len(consistent_configs(mid_playoffs[2], mid_playoffs[3])) == 2**8


def _decided_playoffs(at: dict[int, str]) -> tuple[list[dict[str, object]], dict[int, str]]:
    """Cabeças passam, menos o 10º: 0 x 1 na ida e 1 x 0 na volta, 0 x 0 na prorrogação, cai nos pênaltis para o 24º."""
    rows, winners = [], {}
    for host_first, host_second in _playoff_pairs(at):
        seed_rank = next(rank for rank, club in at.items() if club == host_second)
        if seed_rank == 10:
            rows.append(_leg("PLAYOFFS", 1, host_first, host_second, (1, 0)))
            rows.append(_leg("PLAYOFFS", 2, host_second, host_first, (1, 0), extra=(1, 0), penalties=(3, 4)))
            winners[seed_rank] = host_first
        else:
            rows.append(_leg("PLAYOFFS", 1, host_first, host_second, (0, 1)))
            rows.append(_leg("PLAYOFFS", 2, host_second, host_first, (2, 0)))
            winners[seed_rank] = host_second
    return rows, winners


@pytest.fixture(scope="module")
def round_of_16(complete_league):  # type: ignore[no-untyped-def]
    """Playoff decidido, oitavas sorteadas com as idas jogadas e o confronto do 1º já decidido."""
    simulator, at = complete_league
    rows, winners = _decided_playoffs(at)
    for host_first, host_second in _round_of_16_pairs(at, winners):
        if host_second == at[1]:
            rows.append(_leg("LAST_16", 1, host_first, host_second, (2, 0)))
            rows.append(_leg("LAST_16", 2, host_second, host_first, (0, 1)))
        else:
            rows.append(_leg("LAST_16", 1, host_first, host_second, (1, 1)))
            rows.append(_leg("LAST_16", 2, host_second, host_first, None, day="2041-03-25"))
    _, ties, position = _state(simulator, rows)
    return simulator, at, winners, ties, _run(simulator, ties, position)


def test_penalty_shootout_decides_the_playoff(round_of_16) -> None:  # type: ignore[no-untyped-def]
    ties = round_of_16[3]["PLAYOFFS"]
    shootout = next(tie for tie in ties if round_of_16[1][10] in tie.clubs)
    assert (shootout.winner, shootout.aggregate) == (round_of_16[1][24], (1, 1))


def test_playoff_loser_is_out_of_the_round_of_16(round_of_16) -> None:  # type: ignore[no-untyped-def]
    assert _stage(round_of_16[4], "round_of_16", round_of_16[1][10]) == 0.0


def test_playoff_winner_is_in_the_round_of_16(round_of_16) -> None:  # type: ignore[no-untyped-def]
    assert _stage(round_of_16[4], "round_of_16", round_of_16[1][24]) == 1.0


def test_decided_round_of_16_tie_is_not_simulated(round_of_16) -> None:  # type: ignore[no-untyped-def]
    result, at = round_of_16[4], round_of_16[1]
    assert (_stage(result, "quarter_finals", at[1]), _stage(result, "winner", at[1])) == (0.0, 0.0)


def test_round_of_16_totals_still_close(round_of_16) -> None:  # type: ignore[no-untyped-def]
    result = round_of_16[4]
    assert [round(float(result.stage_counts[stage].sum()), 6) for stage in STAGES] == [16.0, 8.0, 4.0, 2.0, 1.0]


def test_current_stage_is_the_round_of_16(round_of_16) -> None:  # type: ignore[no-untyped-def]
    assert current_stage(round_of_16[3]) == "LAST_16"


def _path_to_final(at: dict[int, str]) -> tuple[list[dict[str, object]], str, str]:
    """Todos os cabeças passam até a semifinal; a chave escolhida põe 1º e 2º em lados opostos (configuração 0)."""
    rows, winners = _decided_playoffs(at)
    r16_winners = {}
    for host_first, host_second in _round_of_16_pairs(at, winners):
        rows.append(_leg("LAST_16", 1, host_first, host_second, (0, 1)))
        rows.append(_leg("LAST_16", 2, host_second, host_first, (1, 0)))
        r16_winners[next(rank for rank, club in at.items() if club == host_second)] = host_second
    # Configuração 0: lado 0 = seeds 1, 3, 5, 7; quartas 1 x 7 e 3 x 5; semifinal (1/7) x (3/5); lado 1 com 2, 4, 6, 8.
    for side in ((1, 7, 3, 5), (2, 8, 4, 6)):
        a, d, b, c = side
        for better, worse in ((a, d), (b, c)):
            rows.append(_leg("QUARTER_FINALS", 1, at[worse], at[better], (0, 0)))
            rows.append(_leg("QUARTER_FINALS", 2, at[better], at[worse], (1, 0)))
        rows.append(_leg("SEMI_FINALS", 1, at[b], at[a], (0, 0)))
        rows.append(_leg("SEMI_FINALS", 2, at[a], at[b], (2, 1)))
    return rows, at[1], at[2]


def test_final_only_has_the_two_finalists(complete_league) -> None:  # type: ignore[no-untyped-def]
    simulator, at = complete_league
    rows, first, second = _path_to_final(at)
    rows.append(_leg("FINAL", 1, first, second, None, day="2041-05-30"))
    _, ties, position = _state(simulator, rows, pd.Timestamp("2041-05-10"))
    result = _run(simulator, ties, position)
    assert round(_stage(result, "winner", first) + _stage(result, "winner", second), 6) == 1.0


def test_finished_final_decided_on_penalties_has_one_champion(complete_league) -> None:  # type: ignore[no-untyped-def]
    simulator, at = complete_league
    rows, first, second = _path_to_final(at)
    rows.append(_leg("FINAL", 1, first, second, (1, 1), extra=(2, 2), penalties=(5, 4), day="2041-05-30"))
    _, ties, position = _state(simulator, rows, pd.Timestamp("2041-05-31"))
    assert _stage(_run(simulator, ties, position), "winner", first) == 1.0


def test_known_semifinals_leave_only_the_mirrored_bracket(complete_league) -> None:  # type: ignore[no-untyped-def]
    """Trocar os dois lados da chave inteira dá a mesma chave: sobram 2 configurações equivalentes."""
    simulator, at = complete_league
    rows, _, _ = _path_to_final(at)
    _, ties, position = _state(simulator, rows, pd.Timestamp("2041-05-10"))
    assert len(consistent_configs(ties, position)) == 2


def test_round_of_16_between_two_seeds_is_refused(complete_league) -> None:  # type: ignore[no-untyped-def]
    simulator, at = complete_league
    rows, _ = _decided_playoffs(at)
    rows.append(_leg("LAST_16", 1, at[2], at[1], None))
    _, ties, position = _state(simulator, rows)
    with pytest.raises(KnockoutFormatError):
        consistent_configs(ties, position)


def test_playoff_loser_in_the_round_of_16_is_refused(complete_league) -> None:  # type: ignore[no-untyped-def]
    simulator, at = complete_league
    rows, _ = _decided_playoffs(at)
    rows.append(_leg("LAST_16", 1, at[10], at[1], None))
    with pytest.raises(KnockoutFormatError):
        _state(simulator, rows)


def test_knockout_during_the_league_phase_is_refused() -> None:
    phase, _ = _league(played_rounds=7)
    rows = [*_league_rows(phase), _leg("PLAYOFFS", 1, "c00", "c01", None)]
    with pytest.raises(KnockoutFormatError):
        knockout_ties(_frame(rows), REFERENCE)


def test_unknown_stage_keeps_the_safety_lock() -> None:
    with pytest.raises(KnockoutFormatError):
        read_knockout(_frame([_leg("PLAYOFFS", 1, "a", "b", None) | {"stage": "GROUP_STAGE"}]), REFERENCE)


def test_penalties_without_a_tied_aggregate_are_refused() -> None:
    rows = [
        _leg("PLAYOFFS", 1, "a", "b", (2, 0)),
        _leg("PLAYOFFS", 2, "b", "a", (1, 0), extra=(1, 0), penalties=(4, 3)),
    ]
    with pytest.raises(KnockoutFormatError):
        read_knockout(_frame(rows), REFERENCE)


def test_second_leg_must_swap_the_home_side() -> None:
    rows = [_leg("PLAYOFFS", 1, "a", "b", (2, 0)), _leg("PLAYOFFS", 2, "a", "b", None)]
    with pytest.raises(KnockoutFormatError):
        read_knockout(_frame(rows), REFERENCE)


def test_scheduled_leg_never_gets_a_score() -> None:
    tie = read_knockout(_frame([_leg("PLAYOFFS", 1, "a", "b", None)]), REFERENCE)["PLAYOFFS"][0]
    assert (tie.legs[0].home_goals, tie.aggregate) == (None, None)


def test_league_phase_forecast_stays_on_the_old_path() -> None:
    phase, _ = _league(played_rounds=5)
    ties, done = knockout_ties(_frame(_league_rows(phase)), REFERENCE)
    assert (done, sum(len(stage) for stage in ties.values())) == (False, 0)


# ---------------------------------------------------------------- Ingestão do football-data.org (sintético)


def _api_match(match_id: int, stage: str, home: int | None, away: int | None, score: dict[str, object],
               status: str = "FINISHED") -> dict[str, object]:  # fmt: skip
    return {
        "id": match_id,
        "utcDate": "2041-02-17T20:00:00Z",
        "status": status,
        "matchday": None,
        "stage": stage,
        "homeTeam": {"id": home, "name": None if home is None else f"Sintético {home}"},
        "awayTeam": {"id": away, "name": None if away is None else f"Sintético {away}"},
        "score": score,
    }


SHOOTOUT = {
    "duration": "PENALTY_SHOOTOUT",
    "fullTime": {"home": 6, "away": 5},
    "regularTime": {"home": 1, "away": 1},
    "extraTime": {"home": 0, "away": 0},
    "penalties": {"home": 5, "away": 4},
}


def test_shootout_keeps_the_90_minute_score_for_the_model() -> None:
    assert decided_score({"id": 1, "score": SHOOTOUT}) == ((1, 1), (1, 1), (5, 4))


def test_extra_time_without_regular_time_is_refused() -> None:
    with pytest.raises(SourceFormatError):
        decided_score({"id": 1, "score": {"duration": "EXTRA_TIME", "fullTime": {"home": 2, "away": 1}}})


def test_undefined_knockout_slot_is_not_a_match() -> None:
    registry = ClubRegistry(clubs={}, alias_index={"fd:1": "c01", "fd:2": "c02"})
    payload = {
        "matches": [
            _api_match(10, "PLAYOFFS", 1, 2, SHOOTOUT),
            _api_match(11, "LAST_16", 1, None, {"fullTime": {"home": None, "away": None}}, "TIMED"),
        ]
    }
    records, _ = current_records(payload, "CL", 2040, "Europe/London", registry, "synthetic")
    assert [(row["stage"], row["home_goals"], row["penalties_home"]) for row in records] == [("PLAYOFFS", 1, 5)]


# ---------------------------------------------------------------- Previsão completa e gate (sintético)


def _history(clubs: list[str]) -> list[dict[str, object]]:
    """Quatro temporadas sintéticas de copa para treinar o modelo de gols e aquecer o Elo."""
    generator = np.random.default_rng(21)
    rows = []
    for season in range(2036, 2040):
        for index in range(220):
            home, away = generator.choice(len(clubs), size=2, replace=False)
            rows.append(
                {
                    "match_id": f"hist-{season}-{index}",
                    "season": season,
                    "competition": "CL",
                    "stage": "League",
                    "match_date": pd.Timestamp(f"{season}-10-01") + pd.Timedelta(days=int(index)),
                    "home_id": clubs[home],
                    "away_id": clubs[away],
                    "home_goals": int(generator.poisson(1.5 + 0.02 * (away - home))),
                    "away_goals": int(generator.poisson(1.1)),
                    "neutral": False,
                    "status": "finished",
                }
            )
    return rows


def _forecast_inputs(knockout_rows: list[dict[str, object]], played_rounds: int, reference: pd.Timestamp
                     ) -> tuple[pd.DataFrame, dict[str, object], ClubRegistry, dict[str, str]]:  # fmt: skip
    phase, _ = _league(played_rounds=played_rounds)
    clubs = list(phase.club_ids)
    current = [row | {"season": 2040, "competition": "CL", "neutral": row["stage"] == "FINAL"}
               for row in _league_rows(phase) + knockout_rows]  # fmt: skip
    matches_data = _frame(_history(clubs) + current).sort_values(["match_date", "match_id"]).reset_index(drop=True)
    matches_data["kickoff_utc"] = None
    registry = ClubRegistry(
        clubs={
            club: Club(
                club_id=club, display_name=f"Sintético {club}", short_name=club.upper()[:4], state="EN", aliases=()
            )
            for club in clubs
        },
        alias_index={},
    )
    sources = {
        "reference_date": reference.date().isoformat(),
        "sources": [
            {
                "tag": "synthetic@1",
                "source_name": "synthetic",
                "version": "1",
                "origin": "https://example.invalid/synthetic",
                "license_name": "synthetic",
                "attribution": "Dados sintéticos de teste",
                "retrieved_at": "2041-06-01T00:00:00+00:00",
            }
        ],
    }
    return matches_data, sources, registry, {club: "ENG" for club in clubs}


def _forecast(knockout_rows: list[dict[str, object]], played_rounds: int, reference: pd.Timestamp):  # type: ignore[no-untyped-def]
    matches_data, sources, registry, countries = _forecast_inputs(knockout_rows, played_rounds, reference)
    return build_forecast(matches_data, sources, registry, countries, GlobalEloParams(), 2040, 3000, 5)


def test_league_phase_forecast_passes_the_gate() -> None:
    forecast = _forecast([], 5, pd.Timestamp("2040-11-20"))
    assert (forecast.phase, check_forecast_core(forecast, date(2041, 6, 1))) == ("league", [])


@pytest.fixture(scope="module")
def knockout_forecast(complete_league):  # type: ignore[no-untyped-def]
    _, at = complete_league
    rows = []
    for index, (host_first, host_second) in enumerate(_playoff_pairs(at)):
        rows.append(_leg("PLAYOFFS", 1, host_first, host_second, (0, 4) if index == 0 else (1, 1)))
        rows.append(_leg("PLAYOFFS", 2, host_second, host_first, None, day="2041-03-25"))
    return _forecast(rows, 8, REFERENCE)


def test_mid_playoffs_forecast_passes_the_gate(knockout_forecast) -> None:  # type: ignore[no-untyped-def]
    assert check_forecast_core(knockout_forecast, date(2041, 6, 1)) == []


def test_mid_playoffs_forecast_publishes_the_real_ties(knockout_forecast) -> None:  # type: ignore[no-untyped-def]
    ties = knockout_forecast.knockout
    assert (knockout_forecast.phase, knockout_forecast.current_stage, len(ties)) == ("knockout", "PLAYOFFS", 8)


def test_second_leg_has_model_probabilities_and_no_score(knockout_forecast) -> None:  # type: ignore[no-untyped-def]
    leg = knockout_forecast.knockout[0].legs[1]
    assert (leg.status, leg.home_goals, round(leg.p_home + leg.p_draw + leg.p_away, 6)) == ("scheduled", None, 1.0)


def test_gate_catches_a_score_on_a_scheduled_leg(knockout_forecast) -> None:  # type: ignore[no-untyped-def]
    broken = knockout_forecast.model_copy(deep=True)
    broken.knockout[0].legs[1].home_goals = 0
    assert any("por disputar com placar" in finding for finding in check_knockout(broken))
