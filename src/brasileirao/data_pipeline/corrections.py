"""Correções manuais de resultados, com proveniência, aplicadas sobre a fonte na camada silver.

Cada correção registra o que a fonte mostrava (`source_*`) e o valor conferido em outra fonte
confiável (`status`, `home_goals`, `away_goals`), com URL e data da conferência. Ela só é aplicada
enquanto a fonte continuar mostrando exatamente o valor registrado. Quando a fonte passa a concordar,
a correção vira redundante; quando a fonte muda para um terceiro valor, a correção não é aplicada e
o conflito é reportado para revisão humana. Correções usam o `match_id` estável entre fontes
(`<temporada>-<mandante>-<visitante>`), e a coluna `source` da linha corrigida guarda a fonte-base:
`<fonte>+manual_correction@<evidência>:<data>` (regra G2 do ADR-0008).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, ConfigDict, model_validator

from brasileirao.contracts import MatchStatus

CORRECTION_SOURCE_PREFIX = "manual_correction"


class ManualCorrection(BaseModel):
    model_config = ConfigDict(frozen=True)

    match_id: str
    home_id: str
    away_id: str
    source_status: MatchStatus
    source_home_goals: int | None = None
    source_away_goals: int | None = None
    status: MatchStatus
    home_goals: int | None = None
    away_goals: int | None = None
    evidence_name: str
    evidence_url: str
    checked_at: date
    note: str = ""

    @model_validator(mode="after")
    def _check_consistency(self) -> ManualCorrection:
        for status, home_goals, away_goals in (
            (self.source_status, self.source_home_goals, self.source_away_goals),
            (self.status, self.home_goals, self.away_goals),
        ):
            has_score = home_goals is not None and away_goals is not None
            if status == MatchStatus.FINISHED and not has_score:
                raise ValueError(f"{self.match_id}: partida encerrada sem placar")
            if status != MatchStatus.FINISHED and (home_goals is not None or away_goals is not None):
                raise ValueError(f"{self.match_id}: partida não encerrada com placar")
        if not self.evidence_url.startswith("https://"):
            raise ValueError(f"{self.match_id}: evidência precisa de URL https")
        if self.source_result == self.corrected_result:
            raise ValueError(f"{self.match_id}: correção igual ao valor da fonte")
        return self

    @property
    def source_result(self) -> tuple[str, int | None, int | None]:
        return (self.source_status.value, self.source_home_goals, self.source_away_goals)

    @property
    def corrected_result(self) -> tuple[str, int | None, int | None]:
        return (self.status.value, self.home_goals, self.away_goals)

    def source_label(self, base_source: str) -> str:
        """Fonte-base da linha seguida da correção (regra G2 do ADR-0008)."""
        base_name = base_source.split("+", 1)[0].split("@", 1)[0]
        return f"{base_name}+{CORRECTION_SOURCE_PREFIX}@{self.evidence_name}:{self.checked_at.isoformat()}"


class CorrectionAction(StrEnum):
    APPLIED = "applied"
    SOURCE_AGREES = "source_agrees"
    CONFLICT = "conflict"
    MATCH_NOT_FOUND = "match_not_found"


@dataclass(frozen=True)
class CorrectionOutcome:
    correction: ManualCorrection
    action: CorrectionAction
    found: tuple[str, int | None, int | None] | None = None


def _optional_int(value: object) -> int | None:
    """Gols opcionais vindos de CSV (texto vazio) ou do DataFrame (`pd.NA`)."""
    text = "" if value is None or value is pd.NA else str(value).strip()
    return None if text in ("", "nan", "<NA>") else int(float(text))


def load_corrections(path: Path) -> list[ManualCorrection]:
    if not path.exists():
        return []
    rows = pd.read_csv(path, dtype=str, keep_default_na=False)
    return [
        ManualCorrection(
            match_id=row["match_id"],
            home_id=row["home_id"],
            away_id=row["away_id"],
            source_status=MatchStatus(row["source_status"]),
            source_home_goals=_optional_int(row["source_home_goals"]),
            source_away_goals=_optional_int(row["source_away_goals"]),
            status=MatchStatus(row["status"]),
            home_goals=_optional_int(row["home_goals"]),
            away_goals=_optional_int(row["away_goals"]),
            evidence_name=row["evidence_name"],
            evidence_url=row["evidence_url"],
            checked_at=date.fromisoformat(row["checked_at"]),
            note=row.get("note", ""),
        )
        for _, row in rows.iterrows()
    ]


def _result_of(row: pd.Series) -> tuple[str, int | None, int | None]:
    return (str(row["status"]), _optional_int(row["home_goals"]), _optional_int(row["away_goals"]))


def apply_corrections(
    matches_data: pd.DataFrame, corrections: Sequence[ManualCorrection]
) -> tuple[pd.DataFrame, list[CorrectionOutcome]]:
    """Aplica as correções válidas e devolve o que aconteceu com cada uma."""
    corrected = matches_data.copy()
    outcomes: list[CorrectionOutcome] = []
    for correction in corrections:
        positions = corrected.index[corrected["match_id"] == correction.match_id]
        if len(positions) != 1:
            outcomes.append(CorrectionOutcome(correction, CorrectionAction.MATCH_NOT_FOUND))
            continue
        position = positions[0]
        row = corrected.loc[position]
        found = _result_of(row)
        same_clubs = (str(row["home_id"]), str(row["away_id"])) == (correction.home_id, correction.away_id)
        if not same_clubs:
            outcomes.append(CorrectionOutcome(correction, CorrectionAction.CONFLICT, found))
        elif found == correction.corrected_result:
            outcomes.append(CorrectionOutcome(correction, CorrectionAction.SOURCE_AGREES, found))
        elif found != correction.source_result:
            outcomes.append(CorrectionOutcome(correction, CorrectionAction.CONFLICT, found))
        else:
            corrected.loc[position, "status"] = correction.status.value
            corrected.loc[position, "home_goals"] = (
                correction.home_goals if correction.home_goals is not None else pd.NA
            )
            corrected.loc[position, "away_goals"] = (
                correction.away_goals if correction.away_goals is not None else pd.NA
            )
            corrected.loc[position, "source"] = correction.source_label(str(row["source"]))
            outcomes.append(CorrectionOutcome(correction, CorrectionAction.APPLIED, found))
    return corrected, outcomes
