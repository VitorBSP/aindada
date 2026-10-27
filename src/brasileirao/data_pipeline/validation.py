"""Validações de integridade das partidas (camada silver/gold)."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from brasileirao.contracts import MatchStatus
from brasileirao.frame_values import as_int


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class QualityIssue(BaseModel):
    severity: Severity
    code: str
    season: int | None
    detail: str


class SeasonCoverage(BaseModel):
    season: int
    n_clubs: int
    n_matches: int
    n_finished: int
    n_scheduled: int
    expected_matches: int
    first_date: date
    last_date: date


class QualityReport(BaseModel):
    reference_date: date
    seasons: list[SeasonCoverage]
    issues: list[QualityIssue]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == Severity.ERROR for issue in self.issues)


def _season_issues(season: int, season_matches: pd.DataFrame, reference_date: date) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    clubs = set(season_matches["home_id"]) | set(season_matches["away_id"])
    n_clubs = len(clubs)
    expected = n_clubs * (n_clubs - 1)
    if len(season_matches) != expected:
        issues.append(
            QualityIssue(
                severity=Severity.ERROR,
                code="match_count",
                season=season,
                detail=f"{len(season_matches)} partidas; esperado {expected}",
            )
        )
    duplicated_pairs = season_matches.duplicated(["home_id", "away_id"]).sum()
    if duplicated_pairs:
        issues.append(
            QualityIssue(
                severity=Severity.ERROR,
                code="duplicate_pair",
                season=season,
                detail=f"{duplicated_pairs} pares mandante/visitante repetidos",
            )
        )
    home_counts = season_matches.groupby("home_id").size()
    if home_counts.nunique() > 1:
        issues.append(
            QualityIssue(
                severity=Severity.ERROR,
                code="unbalanced_home",
                season=season,
                detail=f"mandos desiguais: {home_counts.to_dict()}",
            )
        )
    finished = season_matches[season_matches["status"] == MatchStatus.FINISHED.value]
    if (finished["home_goals"].isna() | finished["away_goals"].isna()).any():
        issues.append(
            QualityIssue(
                severity=Severity.ERROR,
                code="finished_without_score",
                season=season,
                detail="partida encerrada sem placar",
            )
        )
    if ((finished["home_goals"] < 0) | (finished["away_goals"] < 0)).any():
        issues.append(
            QualityIssue(severity=Severity.ERROR, code="negative_score", season=season, detail="placar negativo")
        )
    unscored = season_matches[season_matches["status"] != MatchStatus.FINISHED.value]
    overdue = unscored[unscored["match_date"].dt.date < reference_date]
    if len(overdue):
        overdue_list = ", ".join(
            f"{row.home_id} x {row.away_id} ({row.match_date.date()})" for row in overdue.itertuples()
        )
        issues.append(
            QualityIssue(
                severity=Severity.WARNING,
                code="past_date_without_result",
                season=season,
                detail=f"{len(overdue)} partidas com data anterior a {reference_date} sem placar na "
                f"fonte (adiadas ou ainda não ingeridas); tratadas como não disputadas: "
                f"{overdue_list}",
            )
        )
    return issues


def load_known_exceptions(path: Path) -> dict[tuple[int, str], str]:
    if not path.exists():
        return {}
    exceptions_data = pd.read_csv(path)
    return {(as_int(row.season), str(row.code)): str(row.note) for row in exceptions_data.itertuples(index=False)}


def _apply_known_exceptions(
    issues: list[QualityIssue], known_exceptions: dict[tuple[int, str], str]
) -> list[QualityIssue]:
    reviewed_issues: list[QualityIssue] = []
    for issue in issues:
        note = known_exceptions.get((issue.season or 0, issue.code))
        if note is None:
            reviewed_issues.append(issue)
        else:
            reviewed_issues.append(
                issue.model_copy(
                    update={
                        "severity": Severity.INFO,
                        "detail": f"{issue.detail} | exceção conhecida: {note}",
                    }
                )
            )
    return reviewed_issues


def run_quality_checks(
    matches_data: pd.DataFrame,
    reference_date: date,
    known_exceptions: dict[tuple[int, str], str] | None = None,
) -> QualityReport:
    issues: list[QualityIssue] = []
    coverage: list[SeasonCoverage] = []
    duplicated_ids = matches_data["match_id"].duplicated().sum()
    if duplicated_ids:
        issues.append(
            QualityIssue(
                severity=Severity.ERROR,
                code="duplicate_match_id",
                season=None,
                detail=f"{duplicated_ids} IDs repetidos",
            )
        )
    if (matches_data["home_id"] == matches_data["away_id"]).any():
        issues.append(
            QualityIssue(severity=Severity.ERROR, code="self_match", season=None, detail="clube enfrentando a si mesmo")
        )
    for season, season_matches in matches_data.groupby("season"):
        season_number = int(str(season))
        clubs = set(season_matches["home_id"]) | set(season_matches["away_id"])
        statuses = season_matches["status"]
        coverage.append(
            SeasonCoverage(
                season=season_number,
                n_clubs=len(clubs),
                n_matches=len(season_matches),
                n_finished=int((statuses == MatchStatus.FINISHED.value).sum()),
                n_scheduled=int((statuses != MatchStatus.FINISHED.value).sum()),
                expected_matches=len(clubs) * (len(clubs) - 1),
                first_date=season_matches["match_date"].min().date(),
                last_date=season_matches["match_date"].max().date(),
            )
        )
        issues.extend(_season_issues(season_number, season_matches, reference_date))
    reviewed_issues = _apply_known_exceptions(issues, known_exceptions or {})
    return QualityReport(reference_date=reference_date, seasons=coverage, issues=reviewed_issues)
