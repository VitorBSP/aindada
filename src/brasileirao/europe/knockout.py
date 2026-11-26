"""Mata-mata real da Champions League (ADR-0012, Art. 19; desempate dos confrontos conferido no ADR).

Lê os confrontos que a fonte já trouxe (ida e volta, final em jogo único), confere cada um contra o regulamento
e diz quais chaves do Art. 19 ainda batem com eles. O que não se encaixa no formato conhecido trava a previsão
(`KnockoutFormatError`): publicar probabilidades de um mata-mata que o modelo não entende seria inventar.

Placar dos 90 minutos nas colunas de gols; prorrogação (total dos 120 minutos) e pênaltis à parte. Só conta jogo
encerrado até a data de referência; jogo sem placar é jogo por disputar, nunca 0 x 0.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise, product

import pandas as pd

from brasileirao.contracts import MatchStatus
from brasileirao.frame_values import as_timestamp, optional_int

LEAGUE_STAGE = "LEAGUE_STAGE"
KNOCKOUT_STAGES = ("PLAYOFFS", "LAST_16", "QUARTER_FINALS", "SEMI_FINALS", "FINAL")
STAGE_ALIASES = {
    "PLAYOFFS": "PLAYOFFS",
    "PLAY_OFFS": "PLAYOFFS",
    "KNOCKOUT_ROUND_PLAY_OFFS": "PLAYOFFS",
    "LAST_16": "LAST_16",
    "ROUND_OF_16": "LAST_16",
    "QUARTER_FINALS": "QUARTER_FINALS",
    "SEMI_FINALS": "SEMI_FINALS",
    "FINAL": "FINAL",
}
STAGE_LABELS = {
    "PLAYOFFS": "Playoff",
    "LAST_16": "Oitavas",
    "QUARTER_FINALS": "Quartas",
    "SEMI_FINALS": "Semifinal",
    "FINAL": "Final",
}
TIES_PER_STAGE = {"PLAYOFFS": 8, "LAST_16": 8, "QUARTER_FINALS": 4, "SEMI_FINALS": 2, "FINAL": 1}
# Fase a que o vencedor do confronto chega (chaves de ChampionsSimulation.stage_counts).
NEXT_STAGE = {
    "PLAYOFFS": "round_of_16",
    "LAST_16": "quarter_finals",
    "QUARTER_FINALS": "semi_finals",
    "SEMI_FINALS": "final",
    "FINAL": "winner",
}

# Art. 19, posições 1-based. Playoff: cabeças x não cabeças em cada seção.
PLAYOFF_SECTIONS = (((9, 10), (23, 24)), ((11, 12), (21, 22)), ((13, 14), (19, 20)), ((15, 16), (17, 18)))
# Oitavas: seção A = 1º/2º contra os vencedores da seção 3 do playoff; B = 3º/4º x 2; C = 5º/6º x 1; D = 7º/8º x 0.
ROUND_OF_16_SECTIONS = (((1, 2), 3), ((3, 4), 2), ((5, 6), 1), ((7, 8), 0))
# Configuração da chave = 12 sorteios binários: par do playoff em cada seção (4), par das oitavas em cada seção (4)
# e lado da chave de cada seção das oitavas (4). Onde a UEFA sorteia, todas valem o mesmo.
CONFIG_BITS = 12


class KnockoutFormatError(RuntimeError):
    """Mata-mata fora do formato que o modelo conhece: a previsão para em vez de publicar números falsos."""


@dataclass(frozen=True)
class Leg:
    match_id: str
    match_date: date
    kickoff_utc: str | None
    home_id: str
    away_id: str
    home_goals: int | None
    away_goals: int | None
    extra_time: tuple[int, int] | None
    penalties: tuple[int, int] | None
    finished: bool


@dataclass(frozen=True)
class RealTie:
    """`clubs` = (mandante da ida, mandante da volta); na final, (mandante e visitante de papel)."""

    stage: str
    clubs: tuple[str, str]
    legs: tuple[Leg, ...]
    winner: str | None
    aggregate: tuple[int, int] | None

    @property
    def first_leg(self) -> Leg | None:
        return self.legs[0] if self.legs and self.legs[0].finished else None


def normalize_stage(stage: str) -> str:
    if stage == LEAGUE_STAGE:
        return stage
    if stage not in STAGE_ALIASES:
        raise KnockoutFormatError(f"fase {stage!r} da Champions fora do formato conhecido")
    return STAGE_ALIASES[stage]


def _optional_pair(home: object, away: object) -> tuple[int, int] | None:
    home_value, away_value = optional_int(home), optional_int(away)
    if home_value is None and away_value is None:
        return None
    if home_value is None or away_value is None:
        raise KnockoutFormatError("prorrogação ou pênaltis com só um dos lados")
    return home_value, away_value


def _leg(match: pd.Series, reference: pd.Timestamp) -> Leg:
    home_goals, away_goals = optional_int(match["home_goals"]), optional_int(match["away_goals"])
    finished = (
        match["status"] == MatchStatus.FINISHED.value
        and as_timestamp(match["match_date"]) <= reference
        and home_goals is not None
        and away_goals is not None
    )
    kickoff = match.get("kickoff_utc")
    return Leg(
        match_id=str(match["match_id"]),
        match_date=as_timestamp(match["match_date"]).date(),
        kickoff_utc=kickoff if isinstance(kickoff, str) else None,
        home_id=str(match["home_id"]),
        away_id=str(match["away_id"]),
        home_goals=home_goals if finished else None,
        away_goals=away_goals if finished else None,
        extra_time=_optional_pair(match.get("extra_time_home"), match.get("extra_time_away")) if finished else None,
        penalties=_optional_pair(match.get("penalties_home"), match.get("penalties_away")) if finished else None,
        finished=finished,
    )


def _decide(scores: tuple[int, int], extra_time: tuple[int, int] | None, penalties: tuple[int, int] | None,
            label: str) -> int:  # fmt: skip
    """Índice (0 ou 1) de quem passa. `scores` = gols de 90 minutos; `extra_time` = o que a prorrogação somou."""
    if scores[0] != scores[1]:
        if extra_time is not None or penalties is not None:
            raise KnockoutFormatError(f"{label}: prorrogação ou pênaltis sem empate no tempo normal")
        return 0 if scores[0] > scores[1] else 1
    if extra_time is None:
        raise KnockoutFormatError(f"{label}: empate no tempo normal sem prorrogação registrada")
    after = (scores[0] + extra_time[0], scores[1] + extra_time[1])
    if after[0] != after[1]:
        if penalties is not None:
            raise KnockoutFormatError(f"{label}: pênaltis depois de prorrogação sem empate")
        return 0 if after[0] > after[1] else 1
    if penalties is None or penalties[0] == penalties[1]:
        raise KnockoutFormatError(f"{label}: empate na prorrogação sem pênaltis decididos")
    return 0 if penalties[0] > penalties[1] else 1


def _extra_goals(leg: Leg) -> tuple[int, int] | None:
    if leg.extra_time is None or leg.home_goals is None or leg.away_goals is None:
        return None
    gained = (leg.extra_time[0] - leg.home_goals, leg.extra_time[1] - leg.away_goals)
    if min(gained) < 0:
        raise KnockoutFormatError(f"jogo {leg.match_id}: placar da prorrogação menor que o dos 90 minutos")
    return gained


def _tie(stage: str, legs: list[Leg]) -> RealTie:
    legs = sorted(legs, key=lambda leg: (leg.match_date, leg.match_id))
    first = legs[0]
    clubs = (first.home_id, first.away_id)
    label = f"{STAGE_LABELS[stage]} {clubs[0]} x {clubs[1]}"
    if stage == "FINAL":
        if len(legs) != 1:
            raise KnockoutFormatError(f"{label}: final com {len(legs)} jogos")
        if not first.finished or first.home_goals is None or first.away_goals is None:
            return RealTie(stage, clubs, tuple(legs), None, None)
        extra = _extra_goals(first)
        winner = clubs[_decide((first.home_goals, first.away_goals), extra, first.penalties, label)]
        total = first.extra_time or (first.home_goals, first.away_goals)
        return RealTie(stage, clubs, tuple(legs), winner, total)
    if len(legs) > 2:
        raise KnockoutFormatError(f"{label}: {len(legs)} jogos num confronto de ida e volta")
    if len(legs) == 2 and (legs[1].home_id, legs[1].away_id) != (clubs[1], clubs[0]):
        raise KnockoutFormatError(f"{label}: a volta não inverte o mando da ida")
    if first.extra_time is not None or first.penalties is not None:
        raise KnockoutFormatError(f"{label}: prorrogação ou pênaltis no jogo de ida")
    if len(legs) == 2 and legs[1].finished and not first.finished:
        raise KnockoutFormatError(f"{label}: volta encerrada com a ida por disputar")
    if not first.finished or first.home_goals is None or first.away_goals is None:
        return RealTie(stage, clubs, tuple(legs), None, None)
    aggregate = (first.home_goals, first.away_goals)
    if len(legs) == 1 or not legs[1].finished:
        return RealTie(stage, clubs, tuple(legs), None, aggregate)
    second = legs[1]
    if second.home_goals is None or second.away_goals is None:
        raise KnockoutFormatError(f"{label}: volta encerrada sem placar")
    regular = (first.home_goals + second.away_goals, first.away_goals + second.home_goals)
    extra = _extra_goals(second)
    extra_for_clubs = None if extra is None else (extra[1], extra[0])
    penalties = None if second.penalties is None else (second.penalties[1], second.penalties[0])
    winner = clubs[_decide(regular, extra_for_clubs, penalties, label)]
    total = regular if extra_for_clubs is None else (regular[0] + extra_for_clubs[0], regular[1] + extra_for_clubs[1])
    return RealTie(stage, clubs, tuple(legs), winner, total)


def read_knockout(champions: pd.DataFrame, reference: pd.Timestamp) -> dict[str, list[RealTie]]:
    """Confrontos reais por fase. Fase desconhecida, jogo repetido ou chave inconsistente: `KnockoutFormatError`."""
    rows = champions[champions["stage"] != LEAGUE_STAGE]
    grouped: dict[tuple[str, frozenset[str]], list[Leg]] = {}
    for _, match in rows.iterrows():
        stage = normalize_stage(str(match["stage"]))
        key = (stage, frozenset((str(match["home_id"]), str(match["away_id"]))))
        if len(key[1]) != 2:
            raise KnockoutFormatError(f"jogo {match['match_id']} de um clube contra ele mesmo")
        grouped.setdefault(key, []).append(_leg(match, reference))
    ties: dict[str, list[RealTie]] = {stage: [] for stage in KNOCKOUT_STAGES}
    for (stage, _), legs in sorted(grouped.items(), key=lambda item: (item[0][0], sorted(item[0][1]))):
        ties[stage].append(_tie(stage, legs))
    for stage, stage_ties in ties.items():
        if len(stage_ties) > TIES_PER_STAGE[stage]:
            raise KnockoutFormatError(
                f"{len(stage_ties)} confrontos em {STAGE_LABELS[stage]}; o máximo é {TIES_PER_STAGE[stage]}"
            )
        clubs = [club for tie in stage_ties for club in tie.clubs]
        if len(clubs) != len(set(clubs)):
            raise KnockoutFormatError(f"clube em dois confrontos de {STAGE_LABELS[stage]}")
    return ties


def check_progression(ties: Mapping[str, Sequence[RealTie]], position: Mapping[str, int]) -> None:
    """Quem está numa fase chegou lá pela fase anterior: venceu o confronto real dela (ou é do top 8 nas oitavas)."""
    for previous, stage in pairwise(KNOCKOUT_STAGES):
        winners = {tie.winner for tie in ties[previous] if tie.winner is not None}
        earlier = {club for tie in ties[previous] for club in tie.clubs}
        for tie in ties[stage]:
            for club in tie.clubs:
                if stage == "LAST_16" and position[club] <= 8:
                    if club in earlier:
                        raise KnockoutFormatError(f"{club} do top 8 também aparece no playoff")
                    continue
                if club not in winners:
                    raise KnockoutFormatError(
                        f"{club} em {STAGE_LABELS[stage]} sem ter vencido {STAGE_LABELS[previous]}"
                    )
    for tie in ties["PLAYOFFS"]:
        for club in tie.clubs:
            if not 9 <= position[club] <= 24:
                raise KnockoutFormatError(f"{club} no playoff em {position[club]}º na fase de liga")


# ---------------------------------------------------------------- Chave (Art. 19)

Node = tuple[str, int] | tuple[str, str, "Node", "Node"]


def bracket(config: Sequence[int]) -> Node:
    """Árvore da chave em posições da fase de liga, para uma configuração dos 12 sorteios."""
    playoff_swap, round_swap, half = config[0:4], config[4:8], config[8:12]
    playoff = [
        [
            ("tie", "PLAYOFFS", ("leaf", seeds[slot]), ("leaf", unseeded[slot ^ playoff_swap[section]]))
            for slot in (0, 1)
        ]
        for section, (seeds, unseeded) in enumerate(PLAYOFF_SECTIONS)
    ]
    halves: list[list[Node]] = [[], []]
    for section, (seeds, playoff_section) in enumerate(ROUND_OF_16_SECTIONS):
        ties: list[Node] = [
            ("tie", "LAST_16", ("leaf", seeds[slot]), playoff[playoff_section][slot ^ round_swap[section]])
            for slot in (0, 1)
        ]
        for side in (0, 1):
            halves[side].append(ties[side ^ half[section]])
    semis: list[Node] = []
    for section_a, section_b, section_c, section_d in halves:
        semis.append(
            ("tie", "SEMI_FINALS", ("tie", "QUARTER_FINALS", section_a, section_d),
             ("tie", "QUARTER_FINALS", section_b, section_c))
        )  # fmt: skip
    return ("tie", "FINAL", semis[0], semis[1])


def _leaves(node: Node) -> frozenset[int]:
    if node[0] == "leaf":
        return frozenset({int(node[1])})
    return _leaves(node[2]) | _leaves(node[3])  # type: ignore[misc]


def _nodes(node: Node) -> Iterable[tuple[str, frozenset[int], frozenset[int]]]:
    if node[0] == "leaf":
        return
    _, stage, left, right = node  # type: ignore[misc]
    yield str(stage), _leaves(left), _leaves(right)
    yield from _nodes(left)
    yield from _nodes(right)


def consistent_configs(ties: Mapping[str, Sequence[RealTie]], position: Mapping[str, int]) -> list[tuple[int, ...]]:
    """Configurações da chave em que todo confronto real cai num nó da sua fase, um clube de cada lado."""
    real = [
        (tie.stage, position[tie.clubs[0]], position[tie.clubs[1]]) for stage in KNOCKOUT_STAGES for tie in ties[stage]
    ]
    valid = []
    for config in product((0, 1), repeat=CONFIG_BITS):
        nodes = list(_nodes(bracket(config)))
        if all(
            any(
                stage == node_stage and ((first in left and second in right) or (first in right and second in left))
                for node_stage, left, right in nodes
            )
            for stage, first, second in real
        ):
            valid.append(config)
    if not valid:
        raise KnockoutFormatError("os confrontos reais não cabem em nenhuma chave do Art. 19")
    return valid


def league_complete(champions: pd.DataFrame, reference: pd.Timestamp) -> bool:
    league = champions[champions["stage"] == LEAGUE_STAGE]
    done = (league["status"] == MatchStatus.FINISHED.value) & (league["match_date"] <= reference)
    return bool(len(league)) and bool(done.all())
