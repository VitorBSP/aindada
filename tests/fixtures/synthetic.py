"""Dados SINTÉTICOS para testes. Nunca representam resultados reais."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SYNTHETIC_CLUBS_CSV = Path(__file__).with_name("clubs_synthetic.csv")
SYNTHETIC_SOURCE = "synthetic-fixture"


def round_robin_rounds(club_ids: list[str]) -> list[list[tuple[str, str]]]:
    """Tabela de turno e returno pelo método do círculo."""
    clubs = list(club_ids)
    n_clubs = len(clubs)
    first_half: list[list[tuple[str, str]]] = []
    for round_number in range(n_clubs - 1):
        pairs = []
        for slot in range(n_clubs // 2):
            home, away = clubs[slot], clubs[n_clubs - 1 - slot]
            pairs.append((home, away) if round_number % 2 == 0 else (away, home))
        first_half.append(pairs)
        clubs = [clubs[0], clubs[-1], *clubs[1:-1]]
    second_half = [[(away, home) for home, away in pairs] for pairs in first_half]
    return first_half + second_half


def synthetic_season(
    season: int,
    club_ids: list[str],
    start: date,
    finished_rounds: int,
    seed: int,
    strengths: dict[str, float] | None = None,
) -> pd.DataFrame:
    generator = np.random.default_rng(seed)
    club_strength = strengths or {club: 0.0 for club in club_ids}
    rows = []
    for round_index, pairs in enumerate(round_robin_rounds(club_ids)):
        match_date = start + timedelta(days=7 * round_index)
        for pair_index, (home, away) in enumerate(pairs):
            finished = round_index < finished_rounds
            home_goals = away_goals = None
            if finished:
                gap = club_strength[home] - club_strength[away]
                home_goals = int(generator.poisson(np.exp(0.35 + 0.3 * gap)))
                away_goals = int(generator.poisson(np.exp(0.05 - 0.3 * gap)))
            rows.append(
                {
                    "match_id": f"syn-{season}-{round_index + 1:02d}-{pair_index:02d}",
                    "season": season,
                    "round": round_index + 1,
                    "match_date": pd.Timestamp(match_date),
                    "home_id": home,
                    "away_id": away,
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                    "status": "finished" if finished else "scheduled",
                    "source": SYNTHETIC_SOURCE,
                    "source_match_id": f"{season}-{round_index}-{pair_index}",
                }
            )
    frame = pd.DataFrame(rows)
    for column in ("round", "home_goals", "away_goals"):
        frame[column] = frame[column].astype("Int64")
    return frame


def synthetic_history(n_clubs: int = 20, current_finished_rounds: int = 30) -> pd.DataFrame:
    """Três temporadas sintéticas: duas completas e a atual parcialmente disputada."""
    all_clubs = [f"sintetico-{index:02d}" for index in range(1, 23)]
    strengths = {club: (index - 11) / 6 for index, club in enumerate(all_clubs)}
    seasons = [
        synthetic_season(2030, all_clubs[:n_clubs], date(2030, 4, 1), 38, 1, strengths),
        synthetic_season(2031, all_clubs[2 : n_clubs + 2], date(2031, 4, 1), 38, 2, strengths),
        synthetic_season(2032, all_clubs[2 : n_clubs + 2], date(2032, 4, 1), current_finished_rounds, 3, strengths),
    ]
    return pd.concat(seasons, ignore_index=True)
