"""Art. 6º, 7º e 8º do Regulamento da Série A 2026."""

from __future__ import annotations

from dataclasses import replace

from brasileirao.competition_rules.qualification import ExternalOutcome, allocate_slots
from brasileirao.competition_rules.season_rules import CupRedirectPolicy, Phase, SeasonRules


def test_no_external_titles_gives_g4_groups_and_fifth_prelim(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome())
    expected = {"c01": Phase.GROUPS, "c02": Phase.GROUPS, "c03": Phase.GROUPS, "c04": Phase.GROUPS, "c05": Phase.PRELIM}
    assert result.libertadores == expected


def test_sudamericana_takes_next_six_clubs(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome())
    assert result.sudamericana == ["c06", "c07", "c08", "c09", "c10", "c11"]


def test_bottom_four_are_relegated(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome())
    assert result.relegated == ["c17", "c18", "c19", "c20"]


def test_libertadores_champion_in_g4_passes_league_slot_down(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome(libertadores_champion="c02"))
    assert result.libertadores["c05"] == Phase.GROUPS and result.libertadores["c06"] == Phase.PRELIM


def test_continental_champion_outside_league_slots_adds_club(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome(sudamericana_champion="c12"))
    assert len(result.libertadores) == 6


def test_cup_champion_outside_top5_takes_groups(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome(cup_champion="c14", cup_runner_up="c15"))
    assert result.libertadores["c14"] == Phase.GROUPS


def test_cup_runner_up_outside_top5_takes_prelim(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome(cup_champion="c14", cup_runner_up="c15"))
    assert result.libertadores["c15"] == Phase.PRELIM


def test_cup_champion_in_g4_redirects_groups_slot_to_runner_up(
    rules_2026: SeasonRules, twenty_clubs: list[str]
) -> None:
    """§ 4º e § 5º: vagas equivalentes; o vice herda a vaga direta da Copa."""
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome(cup_champion="c01", cup_runner_up="c15"))
    assert result.libertadores["c15"] == Phase.GROUPS


def test_cup_champion_in_g4_returns_prelim_to_league(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    """§ 5º: a vaga de pré-Libertadores do vice volta ao melhor colocado não classificado."""
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome(cup_champion="c01", cup_runner_up="c15"))
    assert result.libertadores["c06"] == Phase.PRELIM


def test_cup_champion_fifth_upgrades_and_frees_prelim(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    """§ 3º: o 5º campeão da Copa fica com a fase de grupos; a vaga preliminar desce."""
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome(cup_champion="c05", cup_runner_up="c15"))
    assert (result.libertadores["c05"], result.libertadores["c06"]) == (Phase.GROUPS, Phase.PRELIM)


def test_cup_runner_up_in_top5_keeps_league_slot(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome(cup_champion="c14", cup_runner_up="c03"))
    assert result.libertadores["c06"] == Phase.PRELIM


def test_total_libertadores_slots_with_disjoint_qualifiers(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    outcome = ExternalOutcome(
        libertadores_champion="c10", sudamericana_champion="c11", cup_champion="c12", cup_runner_up="c13"
    )
    assert len(allocate_slots(twenty_clubs, rules_2026, outcome).libertadores) == 9


def test_continental_champion_who_wins_cup_uses_literal_policy(
    rules_2026: SeasonRules, twenty_clubs: list[str]
) -> None:
    """Leitura textual: § 2º manda a vaga da Copa ao melhor colocado não classificado."""
    outcome = ExternalOutcome(libertadores_champion="c12", cup_champion="c12", cup_runner_up="c15")
    result = allocate_slots(twenty_clubs, rules_2026, outcome)
    assert result.libertadores["c05"] == Phase.GROUPS


def test_continental_champion_who_wins_cup_broad_policy_upgrades_runner_up(
    rules_2026: SeasonRules, twenty_clubs: list[str]
) -> None:
    broad_rules = replace(rules_2026, cup_redirect_policy=CupRedirectPolicy.ANY_OTHER_QUALIFICATION)
    outcome = ExternalOutcome(libertadores_champion="c12", cup_champion="c12", cup_runner_up="c15")
    assert allocate_slots(twenty_clubs, broad_rules, outcome).libertadores["c15"] == Phase.GROUPS


def test_relegated_cup_champion_still_qualifies(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome(cup_champion="c19", cup_runner_up="c15"))
    assert "c19" in result.libertadores and "c19" in result.relegated


def test_foreign_or_missing_club_does_not_consume_league_slot(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome(libertadores_champion=None))
    assert len(result.libertadores) == 5


def test_runner_up_outside_league_keeps_its_slot(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    """Vice da Copa da Série B: não gera vaga extra na tabela (achado do Agente 06)."""
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome(cup_champion="c08", cup_runner_up="serie-b"))
    assert len(result.libertadores) == 6


def test_redirect_to_runner_up_outside_league_returns_only_prelim(
    rules_2026: SeasonRules, twenty_clubs: list[str]
) -> None:
    result = allocate_slots(twenty_clubs, rules_2026, ExternalOutcome(cup_champion="c03", cup_runner_up="serie-b"))
    assert len(result.libertadores) == 6


def test_freed_groups_slot_upgrades_best_placed_club(rules_2026: SeasonRules, twenty_clubs: list[str]) -> None:
    """Interpretação adotada: vagas liberadas e da tabela formam um só conjunto, ordenado por fase."""
    outcome = ExternalOutcome(libertadores_champion="c01", cup_champion="c01", cup_runner_up="c06")
    result = allocate_slots(twenty_clubs, rules_2026, outcome)
    assert (result.libertadores["c06"], result.libertadores["c07"]) == (Phase.GROUPS, Phase.PRELIM)
