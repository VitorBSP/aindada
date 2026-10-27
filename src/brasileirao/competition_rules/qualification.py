"""Alocação de vagas continentais e rebaixamento (Art. 6º, 7º e 8º)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from brasileirao.competition_rules.season_rules import (
    PHASE_RANK,
    CupRedirectPolicy,
    Phase,
    SeasonRules,
)


@dataclass(frozen=True)
class ExternalOutcome:
    """Campeões externos. `None` = clube estrangeiro ou fora da Série A."""

    libertadores_champion: str | None = None
    sudamericana_champion: str | None = None
    cup_champion: str | None = None
    cup_runner_up: str | None = None


@dataclass
class QualificationResult:
    libertadores: dict[str, Phase] = field(default_factory=dict)
    routes: dict[str, str] = field(default_factory=dict)
    sudamericana: list[str] = field(default_factory=list)
    relegated: list[str] = field(default_factory=list)


def _sorted_slots(slots: Sequence[Phase]) -> list[Phase]:
    return sorted(slots, key=lambda phase: PHASE_RANK[phase])


def _league_allocation(final_order: Sequence[str], slots: Sequence[Phase], excluded: set[str]) -> dict[str, Phase]:
    remaining_slots = list(slots)
    allocation: dict[str, Phase] = {}
    for club_id in final_order:
        if not remaining_slots:
            break
        if club_id in excluded:
            continue
        allocation[club_id] = remaining_slots.pop(0)
    return allocation


def allocate_slots(final_order: Sequence[str], rules: SeasonRules, outcome: ExternalOutcome) -> QualificationResult:
    """Aplica o Art. 6º (com §§ 2º–5º), o Art. 7º e o Art. 8º a uma classificação final."""
    in_league = set(final_order)
    result = QualificationResult()
    continental: dict[str, Phase] = {}
    for champion in (outcome.libertadores_champion, outcome.sudamericana_champion):
        if champion is not None and champion in in_league:
            continental[champion] = rules.continental_title_phase
            result.routes[champion] = "título continental"

    league_slots = list(rules.league_slots)
    extra_slots: list[Phase] = []
    cup_holders: dict[str, Phase] = {}

    champion = outcome.cup_champion if outcome.cup_champion in in_league else None
    runner_up = outcome.cup_runner_up if outcome.cup_runner_up in in_league else None
    runner_up_phase = rules.cup_runner_up_phase

    if outcome.cup_champion is not None:
        tentative = _league_allocation(final_order, league_slots, set(continental))
        broad_redirect = rules.cup_redirect_policy == CupRedirectPolicy.ANY_OTHER_QUALIFICATION
        champion_league_phase = tentative.get(champion) if champion else None
        if champion is not None and champion in continental:
            if broad_redirect:
                runner_up_phase = rules.cup_champion_phase
                extra_slots.append(rules.cup_runner_up_phase)
            else:
                extra_slots.append(rules.cup_champion_phase)
        elif (
            champion is not None
            and champion_league_phase is not None
            and (PHASE_RANK[champion_league_phase] <= PHASE_RANK[rules.cup_champion_phase])
        ):
            runner_up_phase = rules.cup_champion_phase
            extra_slots.append(rules.cup_runner_up_phase)
            result.routes[champion] = "Brasileirão (campeão da Copa do Brasil, § 4º/§ 5º)"
        elif champion is not None:
            cup_holders[champion] = rules.cup_champion_phase
            result.routes[champion] = "campeão da Copa do Brasil"

    if runner_up is not None:
        if runner_up in continental:
            extra_slots.append(runner_up_phase)
        else:
            tentative = _league_allocation(final_order, league_slots, set(continental) | set(cup_holders))
            runner_up_league_phase = tentative.get(runner_up)
            if runner_up_league_phase is None or (PHASE_RANK[runner_up_phase] < PHASE_RANK[runner_up_league_phase]):
                cup_holders[runner_up] = runner_up_phase
                result.routes[runner_up] = "vice da Copa do Brasil"
            else:
                extra_slots.append(runner_up_phase)

    excluded = set(continental) | set(cup_holders)
    league_allocation = _league_allocation(final_order, _sorted_slots(league_slots + extra_slots), excluded)
    for club_id in league_allocation:
        result.routes.setdefault(club_id, "Brasileirão")
    result.libertadores = {**league_allocation, **continental, **cup_holders}

    for club_id in final_order:
        if len(result.sudamericana) == rules.sudamericana_count:
            break
        if club_id not in result.libertadores:
            result.sudamericana.append(club_id)
    result.relegated = list(final_order[-rules.relegation_count :])
    return result
