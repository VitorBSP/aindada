"""Critérios configuráveis do 08A (docs/storytelling/contracts/insight-criteria.toml)."""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

from brasileirao.config import PATHS


@dataclass(frozen=True)
class InsightCriteria:
    z: float
    relative_min_base: float
    title_pp: float
    top4_pp: float
    relegation_pp: float
    materiality_full_pp: float
    novelty_window: int
    max_home_highlights: int
    w_relevance: float
    w_novelty: float
    w_materiality: float
    w_diversity: float
    criteria_hash: str

    def materiality_pp(self, metric: str) -> float:
        return {"title": self.title_pp, "top4": self.top4_pp, "relegation": self.relegation_pp}[metric]


def load_criteria(path: Path | None = None) -> InsightCriteria:
    source = path or PATHS.insight_criteria
    raw_bytes = source.read_bytes()
    values = tomllib.loads(raw_bytes.decode("utf-8"))
    noise, materiality = values["noise"], values["materiality"]
    editorial, scoring = values["editorial"], values["scoring"]
    return InsightCriteria(
        z=float(noise["z"]),
        relative_min_base=float(noise["relative_min_base"]),
        title_pp=float(materiality["title_pp"]),
        top4_pp=float(materiality["top4_pp"]),
        relegation_pp=float(materiality["relegation_pp"]),
        materiality_full_pp=float(materiality["materiality_full_pp"]),
        novelty_window=int(editorial["novelty_window"]),
        max_home_highlights=int(editorial["max_home_highlights"]),
        w_relevance=float(scoring["w_relevance"]),
        w_novelty=float(scoring["w_novelty"]),
        w_materiality=float(scoring["w_materiality"]),
        w_diversity=float(scoring["w_diversity"]),
        criteria_hash=hashlib.sha256(raw_bytes).hexdigest(),
    )
