"""Conferência local entre fontes (ADR-0008, passo 7). Nunca altera dados nem entra no gold.

Compara duas fontes já normalizadas (`match_id` estável) e conta, por temporada, pares casados,
diferenças de data, status, placar e rodada. Os detalhes (com placares) ficam em `data/silver/`,
que não é versionado; no catálogo entram só as contagens (decisão B1). Divergência não é corrigida
automaticamente: vai para o relatório e para o `changes.jsonl`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd
from pydantic import BaseModel

from brasileirao.contracts import MatchStatus


@dataclass(frozen=True)
class ConferencePair:
    candidate: str
    reference: str
    seasons: tuple[int, ...]
    date_tolerance_days: int
    note: str


CONFERENCE_PAIRS = (
    ConferencePair(
        candidate="football_data_org",
        reference="adaoduque_kaggle",
        seasons=(2024, 2025),
        date_tolerance_days=0,
        note="verifica a premissa de data de Brasília do Adão Duque; esperado zero divergência de data",
    ),
    ConferencePair(
        candidate="adaoduque_kaggle",
        reference="brasileirao_dataset",
        seasons=tuple(range(2003, 2024)),
        date_tolerance_days=1,
        note="brasileirao-dataset só traz a data, às vezes no dia UTC; tolerância de ±1 dia",
    ),
    ConferencePair(
        candidate="football_data_org",
        reference="brasileirao_dataset",
        seasons=(2026,),
        date_tolerance_days=1,
        note="conferência local de 2026 (pendência 5 do ADR-0008); divergência em jogo encerrado exige "
        "evidência pontual; tolerância de ±1 dia",
    ),
)


class SeasonConference(BaseModel):
    season: int
    candidate_matches: int
    reference_matches: int
    matched: int
    only_candidate: int
    only_reference: int
    same_date: int
    date_within_tolerance: int
    date_other: int
    status_diff: int
    finished_both: int
    score_diff: int
    round_diff: int


class ConferenceReport(BaseModel):
    candidate: str
    reference: str
    date_tolerance_days: int
    note: str
    seasons: list[SeasonConference]
    divergences: list[dict[str, str]]

    def totals(self) -> dict[str, int]:
        fields = [name for name in SeasonConference.model_fields if name != "season"]
        return {name: sum(int(getattr(season, name)) for season in self.seasons) for name in fields}


def _text(value: object) -> str:
    return "" if value is None or value is pd.NA or (isinstance(value, float) and pd.isna(value)) else str(value)


def compare_sources(
    candidate_matches: pd.DataFrame, reference_matches: pd.DataFrame, pair: ConferencePair
) -> ConferenceReport:
    """Compara por `match_id` estável. As tabelas seguem as colunas da camada silver."""
    seasons: list[SeasonConference] = []
    divergences: list[dict[str, str]] = []
    for season in pair.seasons:
        candidate = candidate_matches[candidate_matches["season"] == season].set_index("match_id")
        reference = reference_matches[reference_matches["season"] == season].set_index("match_id")
        if candidate.empty and reference.empty:
            continue
        common = candidate.index.intersection(reference.index)
        joined = candidate.loc[common].add_suffix("_c").join(reference.loc[common].add_suffix("_r"))
        day_gap = (joined["match_date_c"] - joined["match_date_r"]).dt.days.abs()
        status_diff = joined["status_c"] != joined["status_r"]
        both_finished = (joined["status_c"] == MatchStatus.FINISHED.value) & (
            joined["status_r"] == MatchStatus.FINISHED.value
        )
        score_diff = both_finished & (
            (joined["home_goals_c"] != joined["home_goals_r"]) | (joined["away_goals_c"] != joined["away_goals_r"])
        )
        round_diff = joined["round_c"].astype("Int64").ne(joined["round_r"].astype("Int64")).fillna(True)
        seasons.append(
            SeasonConference(
                season=season,
                candidate_matches=len(candidate),
                reference_matches=len(reference),
                matched=len(common),
                only_candidate=len(candidate.index.difference(reference.index)),
                only_reference=len(reference.index.difference(candidate.index)),
                same_date=int((day_gap == 0).sum()),
                date_within_tolerance=int(((day_gap > 0) & (day_gap <= pair.date_tolerance_days)).sum()),
                date_other=int((day_gap > pair.date_tolerance_days).sum()),
                status_diff=int(status_diff.sum()),
                finished_both=int(both_finished.sum()),
                score_diff=int(score_diff.fillna(False).sum()),
                round_diff=int(round_diff.sum()),
            )
        )
        flagged = joined[(day_gap > pair.date_tolerance_days) | status_diff | score_diff.fillna(False) | round_diff]
        for match_id, row in flagged.iterrows():
            divergences.append(
                {
                    "match_id": str(match_id),
                    "change": "conference_divergence",
                    "candidate": pair.candidate,
                    "reference": pair.reference,
                    "candidate_value": f"{row['match_date_c'].date()} {row['status_c']} "
                    f"{_text(row['home_goals_c'])}-{_text(row['away_goals_c'])} r{_text(row['round_c'])}",
                    "reference_value": f"{row['match_date_r'].date()} {row['status_r']} "
                    f"{_text(row['home_goals_r'])}-{_text(row['away_goals_r'])} r{_text(row['round_r'])}",
                }
            )
        for match_id in candidate.index.symmetric_difference(reference.index):
            divergences.append(
                {
                    "match_id": str(match_id),
                    "change": "conference_missing_match",
                    "candidate": pair.candidate,
                    "reference": pair.reference,
                    "present_in": pair.candidate if match_id in candidate.index else pair.reference,
                }
            )
    return ConferenceReport(
        candidate=pair.candidate,
        reference=pair.reference,
        date_tolerance_days=pair.date_tolerance_days,
        note=pair.note,
        seasons=seasons,
        divergences=divergences,
    )


def counts_table(reports: Sequence[ConferenceReport]) -> list[dict[str, object]]:
    """Só contagens, sem placares: o que pode ir para documentos versionados."""
    return [{"candidate": report.candidate, "reference": report.reference, **report.totals()} for report in reports]
