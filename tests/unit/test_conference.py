"""Conferência local entre fontes (ADR-0008, passo 7). Dados SINTÉTICOS."""

from __future__ import annotations

import pandas as pd

from brasileirao.data_pipeline.conference import CONFERENCE_PAIRS, ConferencePair, compare_sources, counts_table

PAIR = ConferencePair(
    candidate="synthetic_a", reference="synthetic_b", seasons=(2032,), date_tolerance_days=1, note="synthetic"
)


def _frame(rows: list[tuple[str, str, int | None, int | None, str, int]]) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "match_id": match_id,
                "season": 2032,
                "round": round_number,
                "match_date": pd.Timestamp(day),
                "home_id": "sintetico-01",
                "away_id": "sintetico-02",
                "home_goals": home_goals,
                "away_goals": away_goals,
                "status": status,
            }
            for match_id, day, home_goals, away_goals, status, round_number in rows
        ]
    )
    for column in ("round", "home_goals", "away_goals"):
        frame[column] = frame[column].astype("Int64")
    return frame


CANDIDATE = _frame(
    [
        ("m1", "2032-05-01", 1, 0, "finished", 1),
        ("m2", "2032-05-02", 2, 2, "finished", 1),
        ("m3", "2032-05-05", None, None, "scheduled", 2),
        ("m4", "2032-05-09", 0, 0, "finished", 3),
    ]
)
REFERENCE = _frame(
    [
        ("m1", "2032-05-01", 1, 0, "finished", 1),
        ("m2", "2032-05-03", 2, 1, "finished", 1),
        ("m3", "2032-05-01", None, None, "scheduled", 2),
        ("m5", "2032-05-09", 0, 0, "finished", 3),
    ]
)


def _season() -> dict[str, int]:
    return compare_sources(CANDIDATE, REFERENCE, PAIR).seasons[0].model_dump()


def test_matched_pairs_are_counted() -> None:
    assert _season()["matched"] == 3


def test_missing_matches_are_counted_on_each_side() -> None:
    season = _season()
    assert (season["only_candidate"], season["only_reference"]) == (1, 1)


def test_one_day_gap_is_within_tolerance() -> None:
    assert _season()["date_within_tolerance"] == 1


def test_larger_date_gap_is_flagged() -> None:
    assert _season()["date_other"] == 1


def test_score_divergence_is_counted() -> None:
    assert _season()["score_diff"] == 1


def test_divergences_are_listed_for_changes_log() -> None:
    changes = {entry["change"] for entry in compare_sources(CANDIDATE, REFERENCE, PAIR).divergences}
    assert changes == {"conference_divergence", "conference_missing_match"}


def test_counts_table_has_no_scores() -> None:
    table = counts_table([compare_sources(CANDIDATE, REFERENCE, PAIR)])
    assert all(isinstance(value, (int, str)) for row in table for value in row.values())


def test_football_data_vs_adaoduque_requires_exact_dates() -> None:
    pair = next(pair for pair in CONFERENCE_PAIRS if pair.candidate == "football_data_org")
    assert (pair.seasons, pair.date_tolerance_days) == ((2024, 2025), 0)
