"""Cenários condicionais para torneios externos ainda não decididos.

Nenhuma probabilidade é atribuída aos cenários: todos são enumerados e as saídas são
reportadas por cenário e como faixa (mínimo–máximo).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import product

from brasileirao.competition_rules.qualification import ExternalOutcome
from brasileirao.competition_rules.season_rules import FOREIGN_PREFIX, SeasonRules, is_foreign


@dataclass(frozen=True)
class ExternalScenario:
    scenario_id: str
    outcome: ExternalOutcome
    labels: dict[str, str]


def _as_club(reference: str) -> str | None:
    if not reference or is_foreign(reference):
        return None
    return reference


def _label(reference: str, name_of: Callable[[str], str]) -> str:
    if is_foreign(reference):
        return reference.removeprefix(FOREIGN_PREFIX)
    return name_of(reference)


def _options(champion: str, finalists: tuple[str, ...]) -> list[str]:
    if champion:
        return [champion]
    return list(finalists) or [""]


def _cup_options(rules: SeasonRules) -> list[tuple[str, str]]:
    external = rules.external
    if external.cup_champion:
        return [(external.cup_champion, external.cup_runner_up)]
    if len(external.cup_semifinals) == 2:
        first_pair, second_pair = external.cup_semifinals
        return [
            (champion, runner_up)
            for champion_pair, runner_up_pair in ((first_pair, second_pair), (second_pair, first_pair))
            for champion in champion_pair
            for runner_up in runner_up_pair
        ]
    return [("", "")]


def enumerate_external_scenarios(rules: SeasonRules, name_of: Callable[[str], str] = str) -> list[ExternalScenario]:
    external = rules.external
    scenarios: list[ExternalScenario] = []
    for libertadores, sudamericana, (cup_champion, cup_runner_up) in product(
        _options(external.libertadores_champion, external.libertadores_finalists),
        _options(external.sudamericana_champion, external.sudamericana_finalists),
        _cup_options(rules),
    ):
        outcome = ExternalOutcome(
            libertadores_champion=_as_club(libertadores),
            sudamericana_champion=_as_club(sudamericana),
            cup_champion=_as_club(cup_champion) if cup_champion else None,
            cup_runner_up=_as_club(cup_runner_up) if cup_runner_up else None,
        )
        labels = {
            "libertadores_champion": _label(libertadores, name_of) if libertadores else "?",
            "sudamericana_champion": _label(sudamericana, name_of) if sudamericana else "?",
            "cup_champion": _label(cup_champion, name_of) if cup_champion else "?",
            "cup_runner_up": _label(cup_runner_up, name_of) if cup_runner_up else "?",
        }
        scenario_id = "|".join(
            reference or "none" for reference in (libertadores, sudamericana, cup_champion, cup_runner_up)
        )
        scenarios.append(ExternalScenario(scenario_id=scenario_id, outcome=outcome, labels=labels))
    return scenarios
