"""Correções manuais com proveniência (Agente 01). Partidas e placares SINTÉTICOS."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from brasileirao.contracts import MatchStatus
from brasileirao.data_pipeline.corrections import (
    CorrectionAction,
    ManualCorrection,
    apply_corrections,
    load_corrections,
)

EVIDENCE = "https://example.org/synthetic-match"


def _matches(status: str = "finished", home_goals: int | None = 0, away_goals: int | None = 0) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "match_id": ["syn-1", "syn-2"],
            "home_id": ["sintetico-01", "sintetico-03"],
            "away_id": ["sintetico-02", "sintetico-04"],
            "home_goals": [home_goals, 2],
            "away_goals": [away_goals, 1],
            "status": [status, "finished"],
            "source": ["synthetic@1", "synthetic@1"],
        }
    )
    for column in ("home_goals", "away_goals"):
        frame[column] = frame[column].astype("Int64")
    return frame


def _correction(**changes: object) -> ManualCorrection:
    fields: dict[str, object] = {
        "match_id": "syn-1",
        "home_id": "sintetico-01",
        "away_id": "sintetico-02",
        "source_status": MatchStatus.FINISHED,
        "source_home_goals": 0,
        "source_away_goals": 0,
        "status": MatchStatus.FINISHED,
        "home_goals": 0,
        "away_goals": 1,
        "evidence_name": "synthetic",
        "evidence_url": EVIDENCE,
        "checked_at": date(2032, 10, 27),
    }
    fields.update(changes)
    return ManualCorrection.model_validate(fields)


def test_correction_applies_when_source_shows_recorded_value() -> None:
    corrected, outcomes = apply_corrections(_matches(), [_correction()])
    assert (outcomes[0].action, int(corrected.loc[0, "away_goals"])) == (CorrectionAction.APPLIED, 1)


def test_applied_correction_marks_provenance_in_source_column() -> None:
    corrected, _ = apply_corrections(_matches(), [_correction()])
    assert corrected.loc[0, "source"] == "synthetic+manual_correction@synthetic:2032-10-27"


def test_correction_is_redundant_when_source_already_agrees() -> None:
    _, outcomes = apply_corrections(_matches(home_goals=0, away_goals=1), [_correction()])
    assert outcomes[0].action == CorrectionAction.SOURCE_AGREES


def test_correction_is_not_applied_when_source_changed_to_another_value() -> None:
    corrected, outcomes = apply_corrections(_matches(home_goals=2, away_goals=2), [_correction()])
    assert (outcomes[0].action, int(corrected.loc[0, "home_goals"])) == (CorrectionAction.CONFLICT, 2)


def test_correction_with_wrong_clubs_is_a_conflict() -> None:
    _, outcomes = apply_corrections(_matches(), [_correction(home_id="sintetico-09")])
    assert outcomes[0].action == CorrectionAction.CONFLICT


def test_unknown_match_is_reported() -> None:
    _, outcomes = apply_corrections(_matches(), [_correction(match_id="syn-99")])
    assert outcomes[0].action == CorrectionAction.MATCH_NOT_FOUND


def test_correction_can_finish_a_scheduled_match() -> None:
    scheduled = _correction(source_status=MatchStatus.SCHEDULED, source_home_goals=None, source_away_goals=None)
    corrected, _ = apply_corrections(_matches(status="scheduled", home_goals=None, away_goals=None), [scheduled])
    assert corrected.loc[0, "status"] == "finished"


def test_other_matches_are_untouched() -> None:
    corrected, _ = apply_corrections(_matches(), [_correction()])
    assert corrected.loc[1, "source"] == "synthetic@1"


def test_finished_correction_requires_score() -> None:
    with pytest.raises(ValidationError):
        _correction(home_goals=None, away_goals=None)


def test_correction_requires_https_evidence() -> None:
    with pytest.raises(ValidationError):
        _correction(evidence_url="ge.globo")


def test_correction_must_change_something() -> None:
    with pytest.raises(ValidationError):
        _correction(away_goals=0)


def test_missing_corrections_file_means_no_corrections(tmp_path: Path) -> None:
    assert load_corrections(tmp_path / "manual_corrections.csv") == []


def test_corrections_file_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "manual_corrections.csv"
    path.write_text(
        "match_id,home_id,away_id,source_status,source_home_goals,source_away_goals,status,home_goals,away_goals,"
        "evidence_name,evidence_url,checked_at,note\n"
        f"syn-1,sintetico-01,sintetico-02,scheduled,,,finished,3,2,synthetic,{EVIDENCE},2032-10-27,sintético\n",
        encoding="utf-8",
    )
    assert load_corrections(path)[0].corrected_result == ("finished", 3, 2)


def test_project_corrections_file_is_valid() -> None:
    path = Path(__file__).resolve().parents[2] / "data" / "reference" / "manual_corrections.csv"
    if not path.exists():
        pytest.skip("manual_corrections.csv é local e ignorado pelo git (decisão B1); nada a conferir")
    assert all(correction.evidence_url.startswith("https://") for correction in load_corrections(path))


def test_example_corrections_file_is_synthetic_and_valid() -> None:
    path = Path(__file__).resolve().parents[2] / "data" / "reference" / "manual_corrections.example.csv"
    corrections = load_corrections(path)
    assert corrections and all(correction.note.startswith("synthetic") for correction in corrections)


def test_correction_label_drops_base_source_version() -> None:
    assert _correction().source_label("football_data_org@v4-20321027") == (
        "football_data_org+manual_correction@synthetic:2032-10-27"
    )
