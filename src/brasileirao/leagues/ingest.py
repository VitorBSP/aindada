"""Composição por temporada das ligas europeias (ADR-0011, Decisão 1).

| Temporadas | Fonte | Papel |
|---|---|---|
| primeira fixada até a anterior à corrente | openfootball (commit e SHA-256 fixados) | publicação |
| corrente | football-data.org | publicação |
| as anteriores que o plano gratuito libera | football-data.org | só conferência local (`--conference`) |

Sem fallback: temporada sem fonte, placar faltando no histórico ou divergência na conferência fazem a
ingestão falhar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from brasileirao.contracts import BRASILIA_TIMEZONE, MatchStatus, SourceManifest
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.leagues.sources import (
    FOOTBALL_DATA_SOURCE,
    OPENFOOTBALL_SOURCE,
    ApiMatch,
    FixtureRow,
    parse_football_data,
    parse_openfootball,
    read_manifest,
    season_folder,
    verify_files,
)

MATCH_COLUMNS = [
    "match_id",
    "season",
    "round",
    "match_date",
    "kickoff_utc",
    "home_id",
    "away_id",
    "home_goals",
    "away_goals",
    "status",
    "source",
    "source_match_id",
]


class CompositionError(ValueError):
    pass


@dataclass(frozen=True)
class LeaguePins:
    code: str
    football_data_code: str
    clubs_file: str
    current_season: int
    openfootball_repo: str
    openfootball_path: str
    openfootball_commit: str
    history_seasons: tuple[int, ...]
    openfootball_sha256: dict[str, str]
    conference_seasons: tuple[int, ...]


def load_league_pins(path: Path, code: str) -> LeaguePins:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if code not in payload:
        raise CompositionError(f"liga {code!r} sem fontes fixadas em {path.name}")
    league = payload[code]
    openfootball = league["openfootball"]
    return LeaguePins(
        code=code,
        football_data_code=str(league["football_data_code"]),
        clubs_file=str(league["clubs_file"]),
        current_season=int(league["current_season"]),
        openfootball_repo=str(openfootball["repo"]),
        openfootball_path=str(openfootball["path"]),
        openfootball_commit=str(openfootball["commit"]),
        history_seasons=tuple(range(int(openfootball["first_season"]), int(league["current_season"]))),
        openfootball_sha256={str(name): str(digest) for name, digest in openfootball["sha256"].items()},
        conference_seasons=tuple(int(season) for season in league["conference_seasons"]),
    )


def openfootball_file(season: int, path: str) -> str:
    return f"{season_folder(season)}/{path}".replace("/", "_")


def match_id(season: int, home_id: str, away_id: str) -> str:
    return f"{season}-{home_id}-{away_id}"


def history_records(rows: list[FixtureRow], registry: ClubRegistry, source: str) -> list[dict[str, object]]:
    names = registry.resolve_many({row.home_name for row in rows} | {row.away_name for row in rows})
    records = []
    for row in rows:
        if row.home_goals is None or row.away_goals is None:
            raise CompositionError(f"{row.season}: histórico sem placar em {row.home_name} x {row.away_name}")
        home, away = names[row.home_name], names[row.away_name]
        records.append(
            {
                "match_id": match_id(row.season, home, away),
                "season": row.season,
                "round": row.round,
                "match_date": row.match_date,
                "kickoff_utc": None,
                "home_id": home,
                "away_id": away,
                "home_goals": row.home_goals,
                "away_goals": row.away_goals,
                "status": MatchStatus.FINISHED.value,
                "source": source,
                "source_match_id": None,
            }
        )
    return records


def current_records(rows: list[ApiMatch], registry: ClubRegistry, source: str) -> list[dict[str, object]]:
    names = registry.resolve_many({row.home_name for row in rows} | {row.away_name for row in rows})
    return [
        {
            "match_id": match_id(row.season, names[row.home_name], names[row.away_name]),
            "season": row.season,
            "round": row.round,
            "match_date": row.match_date,
            "kickoff_utc": row.kickoff_utc.isoformat() if row.kickoff_utc else None,
            "home_id": names[row.home_name],
            "away_id": names[row.away_name],
            "home_goals": row.home_goals,
            "away_goals": row.away_goals,
            "status": row.status.value,
            "source": source,
            "source_match_id": row.source_match_id,
        }
        for row in rows
    ]


@dataclass(frozen=True)
class Conference:
    season: int
    matched: int
    only_one_source: int
    date_mismatches: int
    score_mismatches: int


def conference(history: list[dict[str, object]], api_rows: list[dict[str, object]], season: int) -> Conference:
    """Mesmo jogo (temporada, mandante, visitante) nas duas fontes: data e placar têm de bater."""
    left = {str(row["match_id"]): row for row in history if row["season"] == season}
    right = {str(row["match_id"]): row for row in api_rows if row["status"] == MatchStatus.FINISHED.value}
    common = set(left) & set(right)
    return Conference(
        season=season,
        matched=len(common),
        only_one_source=len(set(left) ^ set(right)),
        date_mismatches=sum(left[key]["match_date"] != right[key]["match_date"] for key in common),
        score_mismatches=sum(
            (left[key]["home_goals"], left[key]["away_goals"]) != (right[key]["home_goals"], right[key]["away_goals"])
            for key in common
        ),
    )


@dataclass(frozen=True)
class Composition:
    matches: pd.DataFrame
    sources: dict[str, Any]
    reference_date: date


def _latest_dir(parent: Path, prefix: str) -> Path:
    candidates = sorted(
        (path for path in parent.glob(f"{prefix}*") if (path / "manifest.json").exists()),
        key=lambda path: read_manifest(path).retrieved_at,
    )
    if not candidates:
        raise CompositionError(f"nenhuma ingestão em {parent} com prefixo {prefix!r}")
    return candidates[-1]


def _source_info(tag: str, manifest: SourceManifest) -> dict[str, Any]:
    return {
        "tag": tag,
        "source_name": manifest.source_name,
        "origin": manifest.origin,
        "version": manifest.version,
        "retrieved_at": manifest.retrieved_at.isoformat(),
        "license_status": manifest.license_status.value,
        "license_name": manifest.license_name,
        "allowed_uses": [use.value for use in manifest.allowed_uses],
        "attribution": manifest.attribution,
    }


def compose(raw_dir: Path, pins: LeaguePins, registry: ClubRegistry, timezone: str) -> Composition:
    openfootball_dir = raw_dir / OPENFOOTBALL_SOURCE / f"{pins.openfootball_repo}-{pins.openfootball_commit[:12]}"
    if not (openfootball_dir / "manifest.json").exists():
        raise CompositionError(f"openfootball {pins.openfootball_repo} não ingerido em {openfootball_dir}")
    openfootball = read_manifest(openfootball_dir)
    verify_files(openfootball_dir, openfootball)
    for file_name, digest in pins.openfootball_sha256.items():
        if openfootball.files.get(file_name) != digest:
            raise CompositionError(f"{file_name}: SHA-256 do manifesto difere do fixado")
    openfootball_tag = f"{OPENFOOTBALL_SOURCE}@{openfootball.version}"
    records: list[dict[str, object]] = []
    for season in pins.history_seasons:
        text = (openfootball_dir / openfootball_file(season, pins.openfootball_path)).read_text(encoding="utf-8")
        records.extend(history_records(parse_openfootball(text, season), registry, openfootball_tag))

    api_dir = _latest_dir(raw_dir / FOOTBALL_DATA_SOURCE, f"v4-{pins.football_data_code}-")
    api_manifest = read_manifest(api_dir)
    verify_files(api_dir, api_manifest)
    api_tag = f"{FOOTBALL_DATA_SOURCE}@{api_manifest.version}"
    current_file = f"{pins.football_data_code}_{pins.current_season}.json"
    if current_file not in api_manifest.files:
        raise CompositionError(f"{current_file} ausente na última ingestão do football-data.org")
    payload = json.loads((api_dir / current_file).read_text(encoding="utf-8"))
    current = current_records(parse_football_data(payload, pins.current_season, timezone), registry, api_tag)
    records.extend(current)

    conferences: list[Conference] = []
    for season in pins.conference_seasons:
        file_name = f"{pins.football_data_code}_{season}.json"
        if file_name not in api_manifest.files:
            continue
        api_payload = json.loads((api_dir / file_name).read_text(encoding="utf-8"))
        result = conference(
            records, current_records(parse_football_data(api_payload, season, timezone), registry, api_tag), season
        )
        if result.only_one_source or result.date_mismatches or result.score_mismatches:
            raise CompositionError(f"conferência {season}: {result}")
        conferences.append(result)

    finished_current = [
        row["match_date"]
        for row in current
        if row["status"] == MatchStatus.FINISHED.value and isinstance(row["match_date"], date)
    ]
    if not finished_current:
        raise CompositionError(f"{pins.current_season}: nenhum jogo encerrado na temporada corrente")
    reference_date = max(value for value in finished_current if isinstance(value, date))
    collected_on = api_manifest.retrieved_at.astimezone(BRASILIA_TIMEZONE).date()
    if reference_date > collected_on:
        raise CompositionError(f"jogo encerrado em {reference_date}, depois da coleta ({collected_on})")
    matches = pd.DataFrame.from_records(records, columns=MATCH_COLUMNS)
    duplicated = matches["match_id"].duplicated()
    if duplicated.any():
        raise CompositionError(f"match_id repetido: {matches.loc[duplicated, 'match_id'].head(3).tolist()}")
    for manifest in (openfootball, api_manifest):
        if not manifest.allows_public_display:
            raise CompositionError(f"{manifest.source_name} sem public_display_derived")
    sources = {
        "competition": pins.code,
        "reference_date": reference_date.isoformat(),
        "seasons": {
            **{str(season): openfootball_tag for season in pins.history_seasons},
            str(pins.current_season): api_tag,
        },
        "sources": [_source_info(openfootball_tag, openfootball), _source_info(api_tag, api_manifest)],
        "conference": [result.__dict__ for result in conferences],
    }
    return Composition(
        matches.sort_values(["season", "match_date", "match_id"]).reset_index(drop=True), sources, reference_date
    )


def write_silver(composition: Composition, silver_dir: Path) -> None:
    silver_dir.mkdir(parents=True, exist_ok=True)
    composition.matches.to_csv(silver_dir / "matches.csv", index=False)
    (silver_dir / "sources.json").write_text(
        json.dumps(composition.sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def read_silver(silver_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    matches_data = pd.read_csv(silver_dir / "matches.csv", parse_dates=["match_date"])
    for column in ("round", "home_goals", "away_goals"):
        matches_data[column] = matches_data[column].astype("Int64")
    sources = json.loads((silver_dir / "sources.json").read_text(encoding="utf-8"))
    return matches_data, sources
