from __future__ import annotations

from dataclasses import replace

from brasileirao.competition_rules.scenarios import enumerate_external_scenarios
from brasileirao.competition_rules.season_rules import SeasonRules


def test_2026_has_32_external_scenarios(rules_2026: SeasonRules) -> None:
    assert len(enumerate_external_scenarios(rules_2026)) == 32


def test_cup_champion_and_runner_up_come_from_different_semifinals(rules_2026: SeasonRules) -> None:
    pairs = {frozenset(pair) for pair in rules_2026.external.cup_semifinals}
    finals = {
        frozenset((s.outcome.cup_champion, s.outcome.cup_runner_up)) for s in enumerate_external_scenarios(rules_2026)
    }
    assert not finals & pairs


def test_foreign_champion_maps_to_none(rules_2026: SeasonRules) -> None:
    champions = {s.outcome.libertadores_champion for s in enumerate_external_scenarios(rules_2026)}
    assert champions == {"palmeiras", None}


def test_known_champions_collapse_scenarios(rules_2026: SeasonRules) -> None:
    external = replace(
        rules_2026.external,
        libertadores_champion="palmeiras",
        sudamericana_champion="foreign:Boca Juniors",
        cup_champion="vasco",
        cup_runner_up="gremio",
    )
    assert len(enumerate_external_scenarios(replace(rules_2026, external=external))) == 1
