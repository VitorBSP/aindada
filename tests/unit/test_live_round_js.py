"""Modo Ao vivo (apps/web/assets/live-round.js) rodando no Node: vagas iguais às do Python e placares coerentes.

Clubes, jogos e placares SINTÉTICOS (synthetic). Sem Node no ambiente, os testes são pulados.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from brasileirao.competition_rules.qualification import ExternalOutcome, allocate_slots
from brasileirao.competition_rules.season_rules import load_season_rules
from tests.fixtures.synthetic import round_robin_rounds

ASSETS = Path(__file__).resolve().parents[2] / "apps" / "web" / "assets"
NODE = shutil.which("node")
CLUBS = [f"sintetico-{index:02d}" for index in range(1, 21)]
OUTCOME_KEYS = ("libertadores_champion", "sudamericana_champion", "cup_champion", "cup_runner_up")

HARNESS = """
const fs = require("fs");
const vm = require("vm");
const [logicPath, simulatorPath, livePath] = process.argv.slice(1);
const context = { setTimeout, console, Math, Date, JSON, Map, Set, Float64Array };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(logicPath, "utf8"), context);
vm.runInContext(fs.readFileSync(simulatorPath, "utf8"), context);
vm.runInContext(fs.readFileSync(livePath, "utf8"), context);
const live = context.LiveRound;
const input = JSON.parse(fs.readFileSync(0, "utf8"));
(async () => {
  const output = {};
  if (input.allocations) {
    output.allocations = input.allocations.map(({ order, outcome }) => {
      const slots = live.allocateSlots(order, outcome);
      return { libertadores: Object.fromEntries(slots.libertadores), sudamericana: slots.sudamericana };
    });
  }
  if (input.rules) output.rules = live.RULES;
  if (input.clock) output.clock = input.clock.map(({ row, now }) => live.clockMinute(row, Date.parse(now)));
  if (input.distribution) {
    const distribution = live.liveDistribution(input.distribution.match, input.distribution.row);
    output.distribution = {
      cells: distribution.cells.map(([, home, away]) => [home, away]),
      odds: live.outcomeChances(distribution),
    };
  }
  if (input.snapshot) {
    const model = live.prepare(input.snapshot, input.rows);
    const result = await live.simulate(model, { simulations: input.simulations, yieldEvery: false });
    const again = await live.simulate(model, { simulations: input.simulations, yieldEvery: false });
    output.model = { round: model.round, live: model.live, ignored: model.ignored };
    output.table = live.tables(model).map((row) => [row.club_id, row.position, row.points, row.before]);
    output.result = Object.fromEntries([...result.clubs].map(([clubId, value]) => [clubId, value]));
    output.repeatable = JSON.stringify([...result.clubs]) === JSON.stringify([...again.clubs]);
  }
  if (input.track) {
    const model = live.prepare(input.track.snapshot, input.track.rows || []);
    const options = { simulations: input.track.simulations, yieldEvery: false };
    const track = { clubId: input.track.clubId, matchIds: input.track.matchIds };
    const result = await live.simulate(model, { ...options, track });
    const plain = await live.simulate(model, options);
    output.track = {
      entries: result.track,
      overall: result.clubs.get(input.track.clubId),
      simulations: result.simulations,
      plain: plain.track,
    };
  }
  process.stdout.write(JSON.stringify(output));
})();
"""

pytestmark = pytest.mark.skipif(NODE is None, reason="Node indisponível")


def _node(payload: dict[str, Any]) -> dict[str, Any]:
    assert NODE is not None
    completed = subprocess.run(
        [
            NODE,
            "-e",
            HARNESS,
            str(ASSETS / "simulator-logic.js"),
            str(ASSETS / "simulator.js"),
            str(ASSETS / "live-round.js"),
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    result: dict[str, Any] = json.loads(completed.stdout)
    return result


def _random_outcome(generator: random.Random) -> dict[str, str | None]:
    pool: list[str | None] = [None, *CLUBS[:6], CLUBS[-1], CLUBS[-3]]
    outcome = {key: generator.choice(pool) for key in OUTCOME_KEYS}
    if outcome["cup_champion"] is None or outcome["cup_runner_up"] == outcome["cup_champion"]:
        outcome["cup_runner_up"] = None
    return outcome


@cache
def _allocation_cases() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    generator = random.Random(2026)
    cases = []
    for _ in range(400):
        order = CLUBS.copy()
        generator.shuffle(order)
        cases.append({"order": order, "outcome": _random_outcome(generator)})
    return cases, _node({"allocations": cases})["allocations"]


def _python_allocation(case: dict[str, Any]) -> dict[str, Any]:
    slots = allocate_slots(case["order"], load_season_rules(2026), ExternalOutcome(**case["outcome"]))
    return {
        "libertadores": {club: phase.value for club, phase in slots.libertadores.items()},
        "sudamericana": slots.sudamericana,
    }


def test_rules_match_2026_season_file() -> None:
    rules = load_season_rules(2026)
    expected = {
        "leagueSlots": [phase.value for phase in rules.league_slots],
        "cupChampionPhase": rules.cup_champion_phase.value,
        "cupRunnerUpPhase": rules.cup_runner_up_phase.value,
        "continentalTitlePhase": rules.continental_title_phase.value,
        "cupRedirectPolicy": rules.cup_redirect_policy.value,
        "sudamericanaCount": rules.sudamericana_count,
        "relegationCount": rules.relegation_count,
    }
    assert _node({"rules": True})["rules"] == expected


def test_libertadores_matches_python() -> None:
    cases, allocations = _allocation_cases()
    mismatches = [
        index
        for index, case in enumerate(cases)
        if allocations[index]["libertadores"] != _python_allocation(case)["libertadores"]
    ]
    assert mismatches == []


def test_sudamericana_matches_python() -> None:
    cases, allocations = _allocation_cases()
    mismatches = [
        index
        for index, case in enumerate(cases)
        if allocations[index]["sudamericana"] != _python_allocation(case)["sudamericana"]
    ]
    assert mismatches == []


def _rates_match() -> dict[str, Any]:
    return {"match_id": "2099-a-b", "home_id": "a", "away_id": "b", "xg_home": 1.4, "xg_away": 1.1}


def test_live_distribution_never_goes_below_current_score() -> None:
    row = {"status": "live", "minute": 70, "home_goals": 2, "away_goals": 1}
    cells = _node({"distribution": {"match": _rates_match(), "row": row}})["distribution"]["cells"]
    assert min(home for home, _ in cells) == 2 and min(away for _, away in cells) == 1


def test_late_lead_is_very_likely_to_hold() -> None:
    row = {"status": "live", "minute": 89, "home_goals": 1, "away_goals": 0}
    odds = _node({"distribution": {"match": _rates_match(), "row": row}})["distribution"]["odds"]
    assert odds["H"] > 0.9


def _score_matrix() -> list[list[float]]:
    home = [0.3, 0.35, 0.2, 0.1, 0.05]
    away = [0.4, 0.35, 0.15, 0.07, 0.03]
    return [[left * right for right in away] for left in home]


def _synthetic_snapshot() -> dict[str, Any]:
    generator = random.Random(7)
    matches = []
    for round_index, pairs in enumerate(round_robin_rounds(CLUBS), start=1):
        for home, away in pairs:
            finished = round_index < 38
            matches.append(
                {
                    "match_id": f"2099-{home}-{away}",
                    "round": round_index,
                    "home_id": home,
                    "away_id": away,
                    "status": "finished" if finished else "scheduled",
                    "home_goals": generator.randint(0, 3) if finished else None,
                    "away_goals": generator.randint(0, 2) if finished else None,
                    "xg_home": 1.4,
                    "xg_away": 1.1,
                    "score_probabilities": None if finished else _score_matrix(),
                }
            )
    return {
        "season": 2099,
        "teams": [{"club_id": club, "name": club, "short_name": club[-3:]} for club in CLUBS],
        "matches": matches,
        "scenarios": [{"scenario_id": "none|none|none|none"}],
    }


def _last_round_rows(snapshot: dict[str, Any], status: str) -> list[dict[str, Any]]:
    last_round = [match for match in snapshot["matches"] if match["round"] == 38]
    return [
        {
            "season": 2099,
            "round": 38,
            "match_id": match["match_id"],
            "status": status,
            "home_goals": 1,
            "away_goals": 0,
            "minute": 60,
        }
        for match in last_round
    ]


@cache
def _settled_run() -> dict[str, Any]:
    snapshot = _synthetic_snapshot()
    return _node({"snapshot": snapshot, "rows": _last_round_rows(snapshot, "finished"), "simulations": 200})


@cache
def _live_run() -> dict[str, Any]:
    snapshot = _synthetic_snapshot()
    rows = _last_round_rows(snapshot, "live")
    rows.append(
        {
            "season": 2099,
            "round": 38,
            "match_id": "2099-desconhecido-x",
            "status": "live",
            "home_goals": 0,
            "away_goals": 0,
            "minute": 5,
        }
    )
    return _node({"snapshot": snapshot, "rows": rows, "simulations": 2000})


def test_settled_round_gives_title_to_table_leader() -> None:
    run = _settled_run()
    leader = next(club for club, position, _, _ in run["table"] if position == 1)
    assert run["result"][leader]["title"] == 1


def test_settled_round_has_exactly_four_certain_relegations() -> None:
    run = _settled_run()
    assert sorted(value["relegation"] for value in run["result"].values()).count(1) == 4


def test_live_round_detected() -> None:
    assert (_live_run()["model"]["round"], _live_run()["model"]["live"]) == (38, 10)


def test_unknown_match_is_ignored() -> None:
    assert _live_run()["model"]["ignored"] == 1


def test_title_probabilities_sum_to_one() -> None:
    assert sum(value["title"] for value in _live_run()["result"].values()) == pytest.approx(1)


def test_seeded_simulation_is_repeatable() -> None:
    assert _live_run()["repeatable"] is True


def test_partial_scores_enter_the_table() -> None:
    played = {club: points for club, _, points, _ in _live_run()["table"]}
    before = {club: points for club, _, points, _ in _settled_run()["table"]}
    assert played == before


def test_official_result_beats_live_row() -> None:
    snapshot = _synthetic_snapshot()
    finished = next(match for match in snapshot["matches"] if match["round"] == 37)
    rows = _last_round_rows(snapshot, "finished")
    rows.append(
        {
            "season": 2099,
            "round": 37,
            "match_id": finished["match_id"],
            "status": "finished",
            "home_goals": 9,
            "away_goals": 9,
        }
    )
    assert _node({"snapshot": snapshot, "rows": rows, "simulations": 10})["table"] == _settled_run()["table"]


TRACKED_CLUB = CLUBS[0]


@cache
def _tracked_run() -> dict[str, Any]:
    snapshot = _synthetic_snapshot()
    last_round = [match["match_id"] for match in snapshot["matches"] if match["round"] == 38]
    finished = next(match["match_id"] for match in snapshot["matches"] if match["round"] == 37)
    payload = {"snapshot": snapshot, "clubId": TRACKED_CLUB, "matchIds": [*last_round, finished], "simulations": 3000}
    result: dict[str, Any] = _node({"track": payload})["track"]
    return result


def test_tracked_outcomes_cover_every_simulation() -> None:
    run = _tracked_run()
    totals = {sum(outcome["n"] for outcome in entry["outcomes"].values()) for entry in run["entries"]}
    assert totals == {run["simulations"]}


def test_conditional_probabilities_add_back_to_overall() -> None:
    run = _tracked_run()
    entry = run["entries"][0]
    combined = (
        sum(outcome["n"] * (outcome["relegation"] or 0) for outcome in entry["outcomes"].values()) / run["simulations"]
    )
    assert combined == pytest.approx(run["overall"]["relegation"])


def test_finished_match_is_not_tracked() -> None:
    assert len(_tracked_run()["entries"]) == 10


def test_simulation_without_track_returns_empty_list() -> None:
    assert _tracked_run()["plain"] == []


def _clock(minute: int, updated: str, now: str) -> int:
    row = {"status": "live", "minute": minute, "updated_at": updated}
    result: int = _node({"clock": [{"row": row, "now": now}]})["clock"][0]
    return result


def test_clock_advances_between_updates() -> None:
    assert _clock(60, "2099-11-27T23:00:00Z", "2099-11-27T23:07:30Z") == 67


def test_clock_stops_after_first_half() -> None:
    assert _clock(44, "2099-11-27T23:00:00Z", "2099-11-27T23:15:00Z") == 48


def test_clock_never_drifts_more_than_twenty_minutes() -> None:
    assert _clock(50, "2099-11-27T23:00:00Z", "2099-11-28T01:00:00Z") == 70


def test_clock_ignores_future_timestamp() -> None:
    assert _clock(30, "2099-11-27T23:10:00Z", "2099-11-27T23:00:00Z") == 30
