"""Monte Carlo do Mundial de LoL 2026 a partir do estado na Wikipédia (ADR-0013).

Fase suíça: quem tem 3 vitórias se classifica, 3 derrotas sai. A rodada 5 (2–2) é em melhor de 3; confronto
ainda não definido na página é sorteado entre os times com 2–2. Sorteio das quartas (regra da página): os dois
times 3–0 ficam em lados opostos e enfrentam times 3–2; os demais são sorteados. Quartas 1 e 2 formam a semi 1,
quartas 3 e 4 a semi 2. Mata-mata em melhor de 5. Série já jogada entra com o resultado real; confronto já
definido na página é respeitado. Ratings fixos na data de referência.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from brasileirao.esports.model import map_probability, series_probability
from brasileirao.esports.sources import Series

SWISS = "Swiss stage"
QUARTERFINALS = "Knockout stage / Quarterfinals"
SEMIFINALS = "Knockout stage / Semifinals"
FINAL = "Knockout stage / Final"
STAGES = ("qualify", "semifinal", "final", "champion")


@dataclass(frozen=True)
class SwissRecord:
    wins: int
    losses: int

    @property
    def status(self) -> str:
        return "qualified" if self.wins >= 3 else "eliminated" if self.losses >= 3 else "alive"


def required_wins(section: str, wins: int, losses: int) -> int:
    """Fase suíça: melhor de 3 quando a série decide vaga ou eliminação, senão melhor de 1; mata-mata: melhor de 5."""
    if section.startswith(SWISS):
        return 2 if wins == 2 or losses == 2 else 1
    return 3


def _round_number(item: Series) -> int:
    digits = item.section.rsplit("Round ", 1)[-1]
    return int(digits) if digits.isdigit() else 0


def complete_only(series: Sequence[Series]) -> list[Series]:
    """A Wikipédia é editada ao vivo: série com placar parcial (ninguém chegou às vitórias necessárias) volta a
    ser agendada, sem placar. Vale para o evento em andamento; o formato vem da regra da fase."""
    wins: Counter[str] = Counter()
    losses: Counter[str] = Counter()
    finished: dict[int, Series] = {}
    swiss = sorted(
        (index for index, item in enumerate(series) if item.section.startswith(SWISS)),
        key=lambda index: (_round_number(series[index]), series[index].match_date),
    )
    others = [index for index, item in enumerate(series) if not item.section.startswith(SWISS)]
    for index in [*swiss, *others]:
        item = series[index]
        if not item.played:
            finished[index] = item
            continue
        assert item.score1 is not None and item.score2 is not None
        needed = required_wins(item.section, wins[item.team1], losses[item.team1])
        if max(item.score1, item.score2) < needed:
            finished[index] = replace(item, score1=None, score2=None)
            continue
        finished[index] = item
        if item.section.startswith(SWISS):
            winner = _winner(item)
            loser = item.team2 if winner == item.team1 else item.team1
            wins[winner] += 1
            losses[loser] += 1
    return [finished[index] for index in range(len(series))]


def swiss_records(series: Sequence[Series]) -> dict[str, SwissRecord]:
    wins: Counter[str] = Counter()
    losses: Counter[str] = Counter()
    teams: set[str] = set()
    for item in series:
        if not item.section.startswith(SWISS) or not item.defined:
            continue
        teams.update((item.team1, item.team2))
        if item.played:
            assert item.score1 is not None and item.score2 is not None
            winner, loser = (item.team1, item.team2) if item.score1 > item.score2 else (item.team2, item.team1)
            wins[winner] += 1
            losses[loser] += 1
    return {team: SwissRecord(wins[team], losses[team]) for team in teams}


def _winner(item: Series) -> str:
    assert item.score1 is not None and item.score2 is not None
    return item.team1 if item.score1 > item.score2 else item.team2


@dataclass(frozen=True)
class WorldsSimulation:
    stage_probabilities: dict[str, dict[str, float]]
    n_simulations: int


class WorldsSimulator:
    def __init__(self, series: Sequence[Series], rating: Callable[[str], float]) -> None:
        self.series = series
        self.rating = rating
        self.records = swiss_records(series)
        self._cache: dict[tuple[str, str, int], float] = {}

    def win_probability(self, first: str, second: str, best_of: int) -> float:
        key = (first, second, best_of)
        if key not in self._cache:
            self._cache[key] = series_probability(map_probability(self.rating(first), self.rating(second)), best_of)
        return self._cache[key]

    def _play(self, first: str, second: str, best_of: int, generator: random.Random) -> str:
        return first if generator.random() < self.win_probability(first, second, best_of) else second

    def _section(self, name: str) -> list[Series]:
        return [item for item in self.series if item.section == name]

    def _known_or_play(self, items: Sequence[Series], first: str, second: str, generator: random.Random) -> str:
        """Resultado real quando a série entre os dois já foi jogada na fase, em qualquer posição da página."""
        for item in items:
            if item.played and {item.team1, item.team2} == {first, second}:
                return _winner(item)
        return self._play(first, second, 5, generator)

    @staticmethod
    def _semifinal_pairs(winners: list[str], items: Sequence[Series]) -> list[tuple[str, str]]:
        """Semi já definida na página manda no pareamento; sem ela, quartas 1 e 2 formam a semi 1."""
        for item in items:
            if item.defined and {item.team1, item.team2} <= set(winners):
                rest = [team for team in winners if team not in (item.team1, item.team2)]
                return [(item.team1, item.team2), (rest[0], rest[1])]
        return [(winners[0], winners[1]), (winners[2], winners[3])]

    def _swiss(self, generator: random.Random) -> dict[str, SwissRecord]:
        """Completa a fase suíça rodada a rodada. Série definida e não jogada: melhor de 1 ou de 3, como a página
        lista; confronto ainda não definido: sorteio entre times com o mesmo saldo (melhor de 3 quando decide)."""
        wins = {team: record.wins for team, record in self.records.items()}
        losses = {team: record.losses for team, record in self.records.items()}
        for round_number in range(1, 6):
            scheduled: set[str] = set()
            for item in self._section(f"{SWISS} / Round {round_number}"):
                if not item.defined:
                    continue
                scheduled.update((item.team1, item.team2))
                if item.played:
                    continue
                best_of = 2 * required_wins(item.section, wins[item.team1], losses[item.team1]) - 1
                winner = self._play(item.team1, item.team2, best_of, generator)
                loser = item.team2 if winner == item.team1 else item.team1
                wins[winner] += 1
                losses[loser] += 1
            waiting = [
                team
                for team in sorted(wins)
                if team not in scheduled
                and wins[team] < 3
                and losses[team] < 3
                and wins[team] + losses[team] == round_number - 1
            ]
            groups: dict[tuple[int, int], list[str]] = {}
            for team in waiting:
                groups.setdefault((wins[team], losses[team]), []).append(team)
            for (group_wins, group_losses), teams in groups.items():
                if len(teams) % 2:
                    raise ValueError(f"fase suíça: grupo {group_wins}-{group_losses} ímpar na rodada {round_number}")
                generator.shuffle(teams)
                best_of = 3 if group_wins == 2 or group_losses == 2 else 1
                for index in range(0, len(teams) - 1, 2):
                    winner = self._play(teams[index], teams[index + 1], best_of, generator)
                    loser = teams[index + 1] if winner == teams[index] else teams[index]
                    wins[winner] += 1
                    losses[loser] += 1
        return {team: SwissRecord(wins[team], losses[team]) for team in wins}

    def _quarterfinal_pairs(self, records: dict[str, SwissRecord], generator: random.Random) -> list[tuple[str, str]]:
        defined = [(item.team1, item.team2) for item in self._section(QUARTERFINALS) if item.defined]
        if len(defined) == 4:
            return defined
        if defined:
            drawn = {team for pair in defined for team in pair}
            rest = [team for team, record in records.items() if record.wins == 3 and team not in drawn]
            generator.shuffle(rest)
            return [*defined, *zip(rest[::2], rest[1::2], strict=True)]
        three_zero = sorted(team for team, record in records.items() if (record.wins, record.losses) == (3, 0))
        three_one = sorted(team for team, record in records.items() if (record.wins, record.losses) == (3, 1))
        three_two = sorted(team for team, record in records.items() if (record.wins, record.losses) == (3, 2))
        generator.shuffle(three_zero)
        pool_three_two = list(three_two)
        generator.shuffle(pool_three_two)
        first, second = (three_zero[0], pool_three_two[0]), (three_zero[1], pool_three_two[1])
        rest = three_one + pool_three_two[2:]
        generator.shuffle(rest)
        return [first, (rest[0], rest[1]), second, (rest[2], rest[3])]

    def run(self, n_simulations: int, seed: int) -> WorldsSimulation:
        generator = random.Random(seed)
        counts: dict[str, Counter[str]] = {stage: Counter() for stage in STAGES}
        quarter_items = self._section(QUARTERFINALS)
        semi_items = self._section(SEMIFINALS)
        final_items = self._section(FINAL)
        for _ in range(n_simulations):
            records = self._swiss(generator)
            qualified = [team for team, record in records.items() if record.wins == 3]
            if len(qualified) != 8:
                raise ValueError(f"fase suíça terminou com {len(qualified)} classificados")
            counts["qualify"].update(qualified)
            pairs = self._quarterfinal_pairs(records, generator)
            quarter_winners = [self._known_or_play(quarter_items, *pair, generator) for pair in pairs]
            counts["semifinal"].update(quarter_winners)
            finalists = [
                self._known_or_play(semi_items, *pair, generator)
                for pair in self._semifinal_pairs(quarter_winners, semi_items)
            ]
            counts["final"].update(finalists)
            champion = self._known_or_play(final_items, finalists[0], finalists[1], generator)
            counts["champion"][champion] += 1
        teams = sorted(self.records)
        return WorldsSimulation(
            stage_probabilities={
                team: {stage: counts[stage][team] / n_simulations for stage in STAGES} for team in teams
            },
            n_simulations=n_simulations,
        )
