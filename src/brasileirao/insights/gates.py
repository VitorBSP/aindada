"""Portões automáticos (docs/storytelling/INSIGHTS_VALIDATION.md). Falhou um, o candidato é rejeitado."""

from __future__ import annotations

import re

from pydantic import ValidationError

from brasileirao.insights.contracts import Evidence, InsightCandidate, SnapshotRef
from brasileirao.insights.criteria import InsightCriteria
from brasileirao.insights.rules import format_pct, format_pp

NUMBER_TOKEN = re.compile(r"(?<![\d/,])[<>]?\d+(?:,\d+)?%?(?![\d/])")
ARITHMETIC_TOLERANCE = 1e-6
CONTINENTAL_CATEGORIES = {"libertadores", "sudamericana"}


def allowed_number_tokens(evidence: list[Evidence]) -> set[str]:
    tokens: set[str] = set()
    for item in evidence:
        if item.metric in {"home_goals", "away_goals"}:
            tokens.add(str(int(item.current)))
            continue
        if item.metric.startswith(("effect_", "impact_")):
            tokens.add(format_pp(item.current * 100))
            continue
        tokens.add(format_pct(item.current))
        if item.previous is not None:
            tokens.add(format_pct(item.previous))
        if item.delta_pp is not None:
            tokens.add(format_pp(item.delta_pp))
        if item.range is not None:
            tokens.update({format_pct(item.range.min), format_pct(item.range.max)})
    return tokens


def check_candidate(candidate: InsightCandidate, snapshot_ref: SnapshotRef, criteria: InsightCriteria) -> list[str]:
    failures: list[str] = []
    try:
        InsightCandidate.model_validate(candidate.model_dump(by_alias=True))
    except ValidationError as error:
        failures.append(f"schema: {error.error_count()} erro(s)")

    allowed = allowed_number_tokens(candidate.evidence)
    for text in (candidate.headline, candidate.body):
        for token in NUMBER_TOKEN.findall(text):
            if token not in allowed:
                failures.append(f"rastreabilidade: número '{token}' sem evidência")

    period = candidate.reference_period
    if period.to > snapshot_ref.reference_date or period.from_ > period.to:
        failures.append("temporalidade: período fora da data de referência do snapshot")

    if not candidate.uncertainty.passes_noise_test:
        failures.append("ruído: candidato não passou no teste de ruído")
    for item in candidate.evidence:
        threshold = item.noise_threshold_pp
        if threshold is None:
            continue
        if item.delta_pp is not None and abs(item.delta_pp) < threshold:
            failures.append(f"ruído: {item.metric} varia {item.delta_pp:.2f} p.p., abaixo do limiar")
        if item.metric.startswith("impact_") and abs(item.current) * 100 < threshold:
            failures.append(f"ruído: {item.metric} abaixo do limiar")

    for item in candidate.evidence:
        if item.previous is None:
            continue
        if (
            item.delta_pp is not None
            and abs(item.delta_pp - (item.current - item.previous) * 100) > ARITHMETIC_TOLERANCE
        ):
            failures.append(f"aritmética: delta_pp de {item.metric} não confere")
        if item.previous < criteria.relative_min_base and item.relative_change is not None:
            failures.append(f"aritmética: variação relativa de {item.metric} com base abaixo do mínimo")
        if item.relative_change is not None and item.previous > 0:
            expected = (item.current - item.previous) / item.previous
            if abs(item.relative_change - expected) > ARITHMETIC_TOLERANCE:
                failures.append(f"aritmética: variação relativa de {item.metric} não confere")

    if candidate.category in CONTINENTAL_CATEGORIES and not any(item.range for item in candidate.evidence):
        failures.append("faixas: vaga continental sem faixa entre cenários")
    return failures
