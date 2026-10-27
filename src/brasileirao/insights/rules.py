"""Regras determinísticas do 08A (quatro primeiras regras do catálogo; versão em config)."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from brasileirao.config import INSIGHT_RULES_VERSION
from brasileirao.insights.contracts import (
    Category,
    Evidence,
    InsightCandidate,
    ReferencePeriod,
    Relevance,
    SnapshotRef,
    Subject,
    Uncertainty,
)
from brasileirao.insights.criteria import InsightCriteria
from brasileirao.storage.schema import MatchImpactInfo, RoundViewInfo

METRIC_LABELS = {"title": "título", "top4": "G4", "relegation": "rebaixamento"}
CATEGORY_RELEVANCE = {"title": 1.0, "relegation": 0.9, "top4": 0.7}
MATCH_RELEVANCE = 0.7


@dataclass(frozen=True)
class ClubValues:
    name: str
    title: float
    top4: float
    relegation: float

    def metric(self, name: str) -> float:
        return float(getattr(self, name))


@dataclass(frozen=True)
class SnapshotView:
    ref: SnapshotRef
    clubs: dict[str, ClubValues]


@dataclass(frozen=True)
class RoundContext:
    """Visão da rodada que termina na data do snapshot atual e a visão anterior a ela."""

    view: RoundViewInfo
    previous_view: RoundViewInfo
    n_simulations: int


@dataclass(frozen=True)
class RuleInput:
    current: SnapshotView
    previous: SnapshotView | None
    criteria: InsightCriteria
    round_context: RoundContext | None = None
    recent_published: list[tuple[str, str]] = field(default_factory=list)


def format_pct(value: float) -> str:
    if value <= 0:
        return "0%"
    if value < 0.001:
        return "<0,1%"
    if value < 0.01 or 0.99 < value < 0.999:
        return f"{value * 100:.1f}%".replace(".", ",")
    if 0.999 <= value < 1:
        return ">99,9%"
    return f"{round(value * 100)}%"


def format_pp(value_pp: float) -> str:
    return f"{abs(value_pp):.1f}".replace(".", ",")


def format_day(value: date) -> str:
    return value.strftime("%d/%m")


def insight_id(rule_id: str, snapshot_id: str, subject_ids: list[str], metric: str) -> str:
    """Determinístico; inclui a versão das regras para que texto novo nunca herde revisão antiga."""
    key = "|".join([INSIGHT_RULES_VERSION, rule_id, snapshot_id, ",".join(sorted(subject_ids)), metric])
    return "ins_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def snapshot_noise_pp(current: float, current_n: int, previous: float, previous_n: int) -> float:
    """Erro-padrão (em p.p.) da diferença entre duas estimativas de Monte Carlo independentes."""
    variance = current * (1 - current) / current_n + previous * (1 - previous) / previous_n
    return 100 * math.sqrt(max(variance, 0.0))


def novelty(rule_id: str, subject_id: str, recent: list[tuple[str, str]]) -> float:
    if (rule_id, subject_id) in recent:
        return 0.0
    if any(previous_rule == rule_id for previous_rule, _ in recent):
        return 0.5
    return 1.0


def _relevance(base: float, delta_pp: float, rule_id: str, subject_id: str, rule_input: RuleInput) -> Relevance:
    criteria = rule_input.criteria
    materiality = min(1.0, abs(delta_pp) / criteria.materiality_full_pp)
    novelty_value = novelty(rule_id, subject_id, rule_input.recent_published)
    return Relevance(relevance=base, novelty=novelty_value, materiality=materiality, diversity=1.0, score=0.0)


def _decomposition(rule_input: RuleInput, club_id: str, metric: str) -> tuple[list[Evidence], str | None]:
    """Efeito de resultados × força, só quando a revisão por rodada cobre o mesmo intervalo."""
    context = rule_input.round_context
    previous = rule_input.previous
    if context is None or previous is None:
        return [], None
    same_interval = (
        context.view.reference_date == rule_input.current.ref.reference_date
        and context.previous_view.reference_date == previous.ref.reference_date
    )
    results = context.view.results_effect.get(club_id, {}).get(metric)
    strength = context.view.strength_effect.get(club_id, {}).get(metric)
    if not same_interval or results is None or strength is None:
        return [], None
    round_number = context.view.round_number
    evidence = [
        Evidence(
            source="rounds",
            path=f"rounds[round_number={round_number}].{kind}[{club_id}].{metric}",
            metric=f"effect_{kind}_{metric}",
            current=value,
        )
        for kind, value in (("results_effect", results), ("strength_effect", strength))
    ]
    sentence = (
        f"Da variação, {format_pp(results * 100)} p.p. vêm dos resultados da rodada e "
        f"{format_pp(strength * 100)} p.p. da reavaliação da força dos clubes."
    )
    return evidence, sentence


def _snapshot_mover(rule_input: RuleInput, metric: str, direction: int) -> tuple[str, float, float, float] | None:
    """Clube com a maior variação na direção pedida que passa no teste de ruído e de materialidade."""
    previous = rule_input.previous
    if previous is None:
        return None
    criteria = rule_input.criteria
    best: tuple[str, float, float, float] | None = None
    for club_id, values in rule_input.current.clubs.items():
        before = previous.clubs.get(club_id)
        if before is None:
            continue
        current_value, previous_value = values.metric(metric), before.metric(metric)
        delta_pp = (current_value - previous_value) * 100
        if delta_pp * direction <= 0:
            continue
        noise_pp = snapshot_noise_pp(
            current_value, rule_input.current.ref.n_simulations, previous_value, previous.ref.n_simulations
        )
        threshold = max(criteria.materiality_pp(metric), criteria.z * noise_pp)
        if abs(delta_pp) < threshold:
            continue
        if best is None or abs(delta_pp) > abs(best[1] - best[2]) * 100:
            best = (club_id, current_value, previous_value, threshold)
    return best


def _variation_candidate(
    rule_input: RuleInput,
    rule_id: str,
    category: Category,
    metric: str,
    direction: int,
    headline: Callable[[str], str],
    verb: str,
) -> list[InsightCandidate]:
    mover = _snapshot_mover(rule_input, metric, direction)
    previous = rule_input.previous
    if mover is None or previous is None:
        return []
    club_id, current_value, previous_value, threshold = mover
    current = rule_input.current
    name = current.clubs[club_id].name
    delta_pp = (current_value - previous_value) * 100
    relative = (
        (current_value - previous_value) / previous_value
        if previous_value >= rule_input.criteria.relative_min_base
        else None
    )
    evidence = [
        Evidence(
            source="probability_history",
            path=f"teams[club_id={club_id}].{metric}",
            metric=metric,
            current=current_value,
            previous=previous_value,
            previous_snapshot_id=previous.ref.snapshot_id,
            delta_pp=delta_pp,
            relative_change=relative,
            noise_threshold_pp=threshold,
        )
    ]
    decomposition_evidence, decomposition_sentence = _decomposition(rule_input, club_id, metric)
    evidence.extend(decomposition_evidence)
    body = (
        f"A chance de {METRIC_LABELS[metric]} {verb} de {format_pct(previous_value)} para "
        f"{format_pct(current_value)} entre {format_day(previous.ref.reference_date)} e "
        f"{format_day(current.ref.reference_date)}: {format_pp(delta_pp)} pontos percentuais."
    )
    if decomposition_sentence:
        body = f"{body} {decomposition_sentence}"
    notes = [f"Limiar usado: {format_pp(threshold)} p.p. (materialidade ou {rule_input.criteria.z:g} erros-padrão)."]
    if decomposition_sentence is None:
        notes.append("Sem decomposição por rodada para este intervalo; nenhuma causa é atribuída.")
    return [
        InsightCandidate(
            insight_id=insight_id(rule_id, current.ref.snapshot_id, [club_id], metric),
            insight_version=1,
            rule_id=rule_id,
            category=category,
            subjects=[Subject(kind="club", id=club_id, label=name)],
            headline=headline(name),
            body=body,
            evidence=evidence,
            reference_period=ReferencePeriod(from_=previous.ref.reference_date, to=current.ref.reference_date),
            relevance=_relevance(CATEGORY_RELEVANCE[metric], delta_pp, rule_id, club_id, rule_input),
            suggested_placement=["home", "club"],
            suggested_visual="before_after_bar",
            uncertainty=Uncertainty(
                passes_noise_test=True,
                causal_claim="decomposition_supported" if decomposition_sentence else "none",
                notes=notes,
            ),
        )
    ]


def title_riser(rule_input: RuleInput) -> list[InsightCandidate]:
    return _variation_candidate(
        rule_input, "TITLE_RISER", "title", "title", 1, lambda name: f"{name} ganha força na briga pelo título", "subiu"
    )


def title_faller(rule_input: RuleInput) -> list[InsightCandidate]:
    return _variation_candidate(
        rule_input,
        "TITLE_FALLER",
        "title",
        "title",
        -1,
        lambda name: f"{name} perde terreno na briga pelo título",
        "caiu",
    )


def relegation_riser(rule_input: RuleInput) -> list[InsightCandidate]:
    return _variation_candidate(
        rule_input,
        "RELEG_RISER",
        "relegation",
        "relegation",
        1,
        lambda name: f"Risco de queda cresce para {name}",
        "subiu",
    )


def _impact_noise_pp(match: MatchImpactInfo, probability: float, n_simulations: int) -> float:
    count = max(match.pre_match[match.outcome] * n_simulations, 1.0)
    variance = probability * (1 - probability) * max(1 / count - 1 / n_simulations, 0.0)
    return 100 * math.sqrt(variance)


def _outcome_text(match: MatchImpactInfo, names: dict[str, str]) -> str:
    if match.outcome == "home":
        return f"A vitória de {names.get(match.home_id, match.home_id)}"
    if match.outcome == "away":
        return f"A vitória de {names.get(match.away_id, match.away_id)}"
    return "O empate"


def match_moved_most(rule_input: RuleInput) -> list[InsightCandidate]:
    context = rule_input.round_context
    current = rule_input.current
    if context is None or context.view.summary is None or context.view.summary.decisive_match_id is None:
        return []
    if context.view.reference_date != current.ref.reference_date:
        return []
    match = next(
        (item for item in context.view.matches if item.match_id == context.view.summary.decisive_match_id), None
    )
    if match is None:
        return []
    criteria = rule_input.criteria
    best: tuple[str, str, float, float] | None = None
    for club_id, values in match.impacts.items():
        for metric in ("title", "top4", "relegation"):
            impact = values.get(metric)
            baseline = context.previous_view.teams.get(club_id, {}).get(metric)
            if impact is None or baseline is None:
                continue
            threshold = max(
                criteria.materiality_pp(metric), criteria.z * _impact_noise_pp(match, baseline, context.n_simulations)
            )
            if abs(impact) * 100 < threshold:
                continue
            if best is None or abs(impact) > abs(best[2]):
                best = (club_id, metric, impact, threshold)
    if best is None:
        return []
    club_id, metric, impact, threshold = best
    names = {club: values.name for club, values in current.clubs.items()}
    home, away = names.get(match.home_id, match.home_id), names.get(match.away_id, match.away_id)
    pre_match = match.pre_match[match.outcome]
    direction = "acima" if impact > 0 else "abaixo"
    winner = {"home": match.home_id, "away": match.away_id}.get(match.outcome)
    affected = "Com ela, o clube" if club_id == winner else f"Para {names.get(club_id, club_id)}, a"
    subject = "teve a chance" if club_id == winner else "chance"
    body = (
        f"{_outcome_text(match, names)} tinha {format_pct(pre_match)} de chance antes do jogo. {affected} "
        f"{subject} de {METRIC_LABELS[metric]} {format_pp(impact * 100)} pontos percentuais {direction} "
        "do esperado antes da partida."
    )
    path = f"rounds[round_number={context.view.round_number}].matches[match_id={match.match_id}]"
    evidence = [
        Evidence(
            source="rounds",
            path=f"{path}.impacts[{club_id}].{metric}",
            metric=f"impact_{metric}",
            current=impact,
            noise_threshold_pp=threshold,
        ),
        Evidence(
            source="rounds", path=f"{path}.pre_match.{match.outcome}", metric="pre_match_probability", current=pre_match
        ),
        Evidence(source="rounds", path=f"{path}.home_goals", metric="home_goals", current=match.home_goals),
        Evidence(source="rounds", path=f"{path}.away_goals", metric="away_goals", current=match.away_goals),
    ]
    rule_id = "MATCH_MOVED_MOST"
    score_line = f"{home} {match.home_goals} × {match.away_goals} {away}"
    headline = f"{score_line}: o jogo que mais mexeu nas chances"
    if len(headline) > 80:
        headline = score_line
        body = f"Foi o jogo que mais mexeu nas chances. {body}"
    return [
        InsightCandidate(
            insight_id=insight_id(rule_id, current.ref.snapshot_id, [match.match_id, club_id], metric),
            insight_version=1,
            rule_id=rule_id,
            category="match",
            subjects=[
                Subject(kind="match", id=match.match_id, label=f"{home} x {away}"),
                Subject(kind="club", id=club_id, label=names.get(club_id, club_id)),
            ],
            headline=headline,
            body=body,
            evidence=evidence,
            reference_period=ReferencePeriod(
                from_=context.previous_view.reference_date, to=context.view.reference_date
            ),
            relevance=_relevance(MATCH_RELEVANCE, impact * 100, rule_id, match.match_id, rule_input),
            suggested_placement=["home", "round", "matches"],
            suggested_visual="match_line",
            uncertainty=Uncertainty(
                passes_noise_test=True,
                causal_claim="decomposition_supported",
                notes=[
                    "Efeito medido nas simulações feitas antes do jogo, condicionando ao resultado real.",
                    "Outros jogos da rodada e a reavaliação de força também mexeram nas chances.",
                    f"Limiar usado: {format_pp(threshold)} p.p.",
                ],
            ),
        )
    ]


RULES: dict[str, Callable[[RuleInput], list[InsightCandidate]]] = {
    "TITLE_RISER": title_riser,
    "TITLE_FALLER": title_faller,
    "RELEG_RISER": relegation_riser,
    "MATCH_MOVED_MOST": match_moved_most,
}
