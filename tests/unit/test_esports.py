"""Mundial de LoL (ADR-0013). Todos os dados são sintéticos (synthetic)."""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path

import pytest

from brasileirao.esports.forecast import LolForecast, SeriesOutlook, TeamOutlook
from brasileirao.esports.gate import check_forecast
from brasileirao.esports.model import LeagueTeamElo, LeagueTeamParams, map_probability, series_probability
from brasileirao.esports.sources import Series, SourceFormatError, load_teams, parse_series
from brasileirao.esports.worlds import QUARTERFINALS, SWISS, SwissRecord, WorldsSimulator, complete_only, swiss_records

WIKITEXT_SYNTHETIC = """== Swiss stage ==
=== Round 1 ===
{{Esports match
| match = Match 1
| date = 15 October
| year = 2040
| team1 = [[Alfa Gaming]]
| team2 = Beta Esports
| team1score = 1
| team2score = 0
| map1 = Alfa wins
}}
{{Esports match
| match = Match 2
| date = October 16
| year = 2040
| team1 = TBD
| team2 = TBD
| team1score =
| team2score =
}}
== Knockout stage ==
=== Final ===
{{Esports match
| match = Final
| date = 9 November
| year = 2040
| team1 = Alfa Gaming
| team2 = Beta Esports
| team1score =
| team2score =
| map1 =
| map2 =
| map3 =
}}
"""


def _series(
    team1: str, team2: str, score1: int | None, score2: int | None, section: str = f"{SWISS} / Round 1"
) -> Series:
    return Series("Evento sintético", section, "M", date(2040, 10, 15), team1, team2, score1, score2, 1)


def test_parser_keeps_section_with_its_round() -> None:
    assert parse_series(WIKITEXT_SYNTHETIC, "x")[0].section == "Swiss stage / Round 1"


def test_parser_reads_date_in_both_orders() -> None:
    assert [item.match_date for item in parse_series(WIKITEXT_SYNTHETIC, "x")[:2]] == [
        date(2040, 10, 15),
        date(2040, 10, 16),
    ]


def test_unplayed_series_has_no_score_instead_of_zero() -> None:
    final = parse_series(WIKITEXT_SYNTHETIC, "x")[2]
    assert (final.score1, final.score2, final.played) == (None, None, False)


def test_parser_counts_listed_maps() -> None:
    assert parse_series(WIKITEXT_SYNTHETIC, "x")[2].maps_listed == 3


def test_unknown_team_fails_instead_of_being_guessed(tmp_path: Path) -> None:
    teams = tmp_path / "teams.csv"
    teams.write_text("team_id,display_name,short_name,league,aliases\nalfa,Alfa Gaming,ALF,LKA,\n", encoding="utf-8")
    with pytest.raises(SourceFormatError):
        load_teams(teams).resolve(parse_series(WIKITEXT_SYNTHETIC, "x"))


def test_series_probability_of_even_maps_is_half() -> None:
    assert series_probability(0.5, 5) == pytest.approx(0.5)


def test_best_of_five_amplifies_the_favorite() -> None:
    assert series_probability(0.6, 5) > series_probability(0.6, 3) > 0.6


def test_hundred_elo_points_give_about_64_percent() -> None:
    assert map_probability(100.0, 0.0) == pytest.approx(0.640, abs=0.001)


def test_cross_league_win_moves_the_league_strength() -> None:
    elo = LeagueTeamElo(LeagueTeamParams(k_league=20.0, k_team=0.0), {"a": "L1", "b": "L2"})
    elo.run([_series("a", "b", 2, 0)])
    assert elo.league_strength["L1"] == pytest.approx(20.0)


def test_same_league_series_leaves_league_strength_untouched() -> None:
    elo = LeagueTeamElo(LeagueTeamParams(k_league=20.0, k_team=8.0), {"a": "L1", "b": "L1"})
    elo.run([_series("a", "b", 2, 0)])
    assert elo.league_strength["L1"] == 0.0


def test_team_adjustment_resets_at_year_change() -> None:
    leagues = {"a": "L1", "b": "L1", "c": "L1", "d": "L1"}
    elo = LeagueTeamElo(LeagueTeamParams(k_league=0.0, k_team=8.0, team_regression=1.0), leagues)
    later = Series("Evento sintético", f"{SWISS} / Round 1", "M", date(2041, 5, 1), "c", "d", 1, 0, 1)
    elo.run([_series("a", "b", 1, 0), later])
    assert elo.team_adjustment["a"] == 0.0


def test_swiss_record_counts_wins_and_losses() -> None:
    records = swiss_records([_series("a", "b", 1, 0), _series("a", "c", 2, 1, f"{SWISS} / Round 2")])
    assert (records["a"].wins, records["b"].losses, records["c"].losses) == (2, 1, 1)


def _swiss_after_three_rounds() -> list[Series]:
    """16 times sintéticos com as rodadas 1 a 3 completas (vence sempre o time de número menor)."""
    teams = [f"t{index:02d}" for index in range(16)]
    wins = dict.fromkeys(teams, 0)
    losses = dict.fromkeys(teams, 0)
    played: list[Series] = []
    for round_number in (1, 2, 3):
        groups: dict[tuple[int, int], list[str]] = {}
        for team in teams:
            groups.setdefault((wins[team], losses[team]), []).append(team)
        for group in groups.values():
            for first, second in zip(group[::2], group[1::2], strict=True):
                played.append(_series(first, second, 1, 0, f"{SWISS} / Round {round_number}"))
                wins[first] += 1
                losses[second] += 1
    return played


def test_simulation_sends_exactly_eight_teams_to_the_quarterfinals() -> None:
    result = WorldsSimulator(_swiss_after_three_rounds(), lambda team: 0.0).run(200, 7)
    assert sum(stages["qualify"] for stages in result.stage_probabilities.values()) == pytest.approx(8.0)


def test_simulation_crowns_exactly_one_champion() -> None:
    result = WorldsSimulator(_swiss_after_three_rounds(), lambda team: 0.0).run(200, 7)
    assert sum(stages["champion"] for stages in result.stage_probabilities.values()) == pytest.approx(1.0)


def test_simulation_never_qualifies_an_eliminated_team() -> None:
    result = WorldsSimulator(_swiss_after_three_rounds(), lambda team: 0.0).run(200, 7)
    assert result.stage_probabilities["t15"]["qualify"] == 0.0


def test_simulation_is_reproducible_with_the_seed() -> None:
    series = _swiss_after_three_rounds()
    rating = {f"t{index:02d}": float(-index) for index in range(16)}.__getitem__
    assert WorldsSimulator(series, rating).run(100, 3) == WorldsSimulator(series, rating).run(100, 3)


def _forecast(champion_total: float) -> LolForecast:
    stages = {"qualify": 0.5, "semifinal": 0.25, "final": 0.125, "champion": champion_total / 16}
    teams = [
        TeamOutlook(
            team_id=f"t{index}",
            name=f"Time {index}",
            short_name="T",
            league="L",
            swiss_wins=1,
            swiss_losses=1,
            status="alive",
            rating=0.0,
            league_strength=0.0,
            stages=stages,
        )
        for index in range(16)
    ]
    return LolForecast(
        competition_name="Mundial sintético", reference_date="2040-10-20", generated_at="2040-10-20T00:00:00Z",
        n_simulations=10, seed=1, model_version="lol-test", data_version="x", params={}, league_strength={},
        teams=teams, upcoming=[SeriesOutlook(stage="s", label="m", match_date="2040-10-21", team1="t0", team2="t1",
        best_of=3, p_team1=0.5)], warnings=[], sources=[],
    )  # fmt: skip


def test_gate_accepts_consistent_forecast() -> None:
    assert check_forecast(_forecast(1.0), date(2040, 10, 21)) == []


def test_gate_rejects_champion_total_different_from_one() -> None:
    assert any("champion" in finding for finding in check_forecast(_forecast(0.8), date(2040, 10, 21)))


def test_gate_rejects_reference_date_in_the_future() -> None:
    assert any("futuro" in finding for finding in check_forecast(_forecast(1.0), date(2040, 10, 19)))


def test_partial_score_of_a_decisive_series_stays_scheduled() -> None:
    played = _swiss_after_three_rounds()
    group = sorted({item.team1 for item in played} | {item.team2 for item in played})
    records = swiss_records(played)
    first, second = [team for team in group if (records[team].wins, records[team].losses) == (2, 1)][:2]
    live = _series(first, second, 0, 1, f"{SWISS} / Round 4")
    assert complete_only([*played, live])[-1].played is False


def test_finished_decisive_series_keeps_its_score() -> None:
    played = _swiss_after_three_rounds()
    records = swiss_records(played)
    first, second = [team for team in sorted(records) if (records[team].wins, records[team].losses) == (2, 1)][:2]
    done = _series(first, second, 2, 1, f"{SWISS} / Round 4")
    assert complete_only([*played, done])[-1].played is True


def test_quarterfinal_draw_puts_three_zero_teams_on_opposite_sides() -> None:
    simulator = WorldsSimulator([], lambda team: 0.0)
    losses = {"a": 0, "b": 0, "c": 2, "d": 2, "e": 1, "f": 1, "g": 1, "h": 2}
    records = {team: SwissRecord(3, lost) for team, lost in losses.items()}
    pairs = simulator._quarterfinal_pairs(records, random.Random(1))
    assert {pairs[0][0], pairs[2][0]} == {"a", "b"} and records[pairs[0][1]].losses == 2


def test_played_knockout_result_is_found_in_any_page_position() -> None:
    page = [
        _series("x", "y", 3, 1, QUARTERFINALS),
        _series("a", "b", 1, 3, QUARTERFINALS),
    ]
    simulator = WorldsSimulator(page, lambda team: 1000.0 if team == "a" else 0.0)
    assert simulator._known_or_play(page, "a", "b", random.Random(1)) == "b"


def test_gate_rejects_upcoming_series_with_unknown_team() -> None:
    forecast = _forecast(1.0)
    forecast.upcoming[0].team2 = "desconhecido"
    assert any("fora da lista" in finding for finding in check_forecast(forecast, date(2040, 10, 21)))
