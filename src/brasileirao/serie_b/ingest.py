"""Composição da Série B por temporada (ADR-0010, Decisão 1).

| Temporadas | Resultado | Data e rodada |
|---|---|---|
| 2018–2024 | openfootball | openfootball |
| 2025 | Wikipédia (matriz) | calendário do openfootball (`openfootball_schedule`) |
| temporada corrente | Wikipédia (matriz) | ordem imputada (`imputed`); jogos sem placar sem data (`unknown`) |

Sem fallback: temporada sem fonte faz a ingestão falhar.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from brasileirao.contracts import BRASILIA_TIMEZONE, MatchStatus
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.serie_b.sources import (
    OPENFOOTBALL_SOURCE,
    WIKIPEDIA_SOURCE,
    FixtureRow,
    ResultsMatrix,
    SourceFormatError,
    StandingsTable,
    parse_openfootball,
    parse_portuguese_day,
    parse_wikipedia_matrix,
    parse_wikipedia_standings,
    read_manifest,
    verify_files,
)

MATCH_COLUMNS = [
    "match_id",
    "season",
    "round",
    "match_date",
    "home_id",
    "away_id",
    "home_goals",
    "away_goals",
    "status",
    "source",
    "date_source",
    "awarded",
]
SEASON_START_PATTERN = re.compile(r"^\s*\|\s*início\s*=\s*(.+?)\s*$", re.MULTILINE)


class CompositionError(ValueError):
    pass


@dataclass(frozen=True)
class SerieBPins:
    openfootball_commit: str
    openfootball_seasons: tuple[int, ...]
    openfootball_sha256: dict[str, str]
    wikipedia_closed_seasons: dict[int, int]
    current_season: int


def load_pins(path: Path) -> SerieBPins:
    payload = json.loads(path.read_text(encoding="utf-8"))
    openfootball, wikipedia = payload["openfootball"], payload["wikipedia_pt"]
    return SerieBPins(
        openfootball_commit=str(openfootball["commit"]),
        openfootball_seasons=tuple(int(season) for season in openfootball["seasons"]),
        openfootball_sha256={str(name): str(digest) for name, digest in openfootball["sha256"].items()},
        wikipedia_closed_seasons={int(season): int(revid) for season, revid in wikipedia["closed_seasons"].items()},
        current_season=int(wikipedia["current_season"]),
    )


def match_id(season: int, home_id: str, away_id: str) -> str:
    return f"{season}-{home_id}-{away_id}"


def _record(
    season: int,
    round_number: int | None,
    match_date: date,
    home_id: str,
    away_id: str,
    home_goals: int | None,
    away_goals: int | None,
    source: str,
    date_source: str,
    awarded: bool = False,
) -> dict[str, object]:
    finished = home_goals is not None and away_goals is not None
    return {
        "match_id": match_id(season, home_id, away_id),
        "season": season,
        "round": round_number,
        "match_date": match_date,
        "home_id": home_id,
        "away_id": away_id,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "status": MatchStatus.FINISHED.value if finished else MatchStatus.SCHEDULED.value,
        "source": source,
        "date_source": date_source,
        "awarded": awarded,
    }


def openfootball_season(rows: list[FixtureRow], registry: ClubRegistry, source: str) -> list[dict[str, object]]:
    names = registry.resolve_many({row.home_name for row in rows} | {row.away_name for row in rows})
    records = []
    for row in rows:
        if row.home_goals is None:
            raise CompositionError(f"{row.season}: openfootball sem placar em {row.home_name} x {row.away_name}")
        records.append(
            _record(
                row.season,
                row.round,
                row.match_date,
                names[row.home_name],
                names[row.away_name],
                row.home_goals,
                row.away_goals,
                source,
                "openfootball",
                row.awarded,
            )
        )
    return records


@dataclass(frozen=True)
class ScheduleConference:
    season: int
    compared: int
    score_mismatches: int


def wikipedia_with_schedule(
    matrix: ResultsMatrix, schedule: list[FixtureRow], registry: ClubRegistry, source: str
) -> tuple[list[dict[str, object]], ScheduleConference]:
    """Temporada encerrada: placar da matriz, data e rodada do calendário do openfootball."""
    matrix_names = registry.resolve_many({r.home_name for r in matrix.results} | {r.away_name for r in matrix.results})
    schedule_names = registry.resolve_many({r.home_name for r in schedule} | {r.away_name for r in schedule})
    by_pair = {(schedule_names[row.home_name], schedule_names[row.away_name]): row for row in schedule}
    records, compared, mismatches = [], 0, 0
    for result in matrix.results:
        pair = (matrix_names[result.home_name], matrix_names[result.away_name])
        fixture = by_pair.get(pair)
        if fixture is None:
            raise CompositionError(f"{matrix.season}: {pair} na matriz e fora do calendário do openfootball")
        if result.home_goals is None:
            raise CompositionError(f"{matrix.season}: temporada encerrada com jogo sem placar: {pair}")
        if fixture.home_goals is not None:
            compared += 1
            mismatches += (fixture.home_goals, fixture.away_goals) != (result.home_goals, result.away_goals)
        records.append(
            _record(
                matrix.season,
                fixture.round,
                fixture.match_date,
                *pair,
                result.home_goals,
                result.away_goals,
                source,
                "openfootball_schedule",
            )
        )
    if len(by_pair) != len(records):
        raise CompositionError(f"{matrix.season}: calendário com {len(by_pair)} jogos e matriz com {len(records)}")
    return records, ScheduleConference(matrix.season, compared, mismatches)


def _stable_key(identifier: str) -> str:
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()


def imputed_rounds(pairs: list[tuple[str, str]]) -> list[int]:
    """Distribui jogos em rodadas em que cada clube joga no máximo uma vez, em ordem estável e sem viés
    alfabético. A ordem real é desconhecida; o resultado serve só para os ratings não verem todos os
    jogos de uma vez."""
    order = sorted(range(len(pairs)), key=lambda index: _stable_key("|".join(pairs[index])))
    busy: list[set[str]] = []
    assigned = [0] * len(pairs)
    for index in order:
        home, away = pairs[index]
        slot = next((number for number, clubs in enumerate(busy) if home not in clubs and away not in clubs), None)
        if slot is None:
            busy.append(set())
            slot = len(busy) - 1
        busy[slot].update((home, away))
        assigned[index] = slot + 1
    return assigned


def current_season_from_matrix(
    matrix: ResultsMatrix, season_start: date, registry: ClubRegistry, source: str
) -> list[dict[str, object]]:
    cutoff = matrix.cutoff_date()
    if cutoff is None:
        raise CompositionError(
            f"{matrix.season}: matriz marcada como completa; use o calendário de temporada encerrada"
        )
    if cutoff < season_start:
        raise CompositionError(f"{matrix.season}: data de atualização {cutoff} anterior ao início {season_start}")
    names = registry.resolve_many({r.home_name for r in matrix.results} | {r.away_name for r in matrix.results})
    played = [result for result in matrix.results if result.home_goals is not None]
    pending = [result for result in matrix.results if result.home_goals is None]
    pairs = [(names[result.home_name], names[result.away_name]) for result in played]
    slots = imputed_rounds(pairs)
    n_slots = max(slots, default=1)
    span_days = (cutoff - season_start).days
    records = []
    for result, pair, slot in zip(played, pairs, slots, strict=True):
        offset = round(span_days * (slot - 1) / max(n_slots - 1, 1))
        records.append(
            _record(
                matrix.season,
                None,
                season_start + timedelta(days=offset),
                *pair,
                result.home_goals,
                result.away_goals,
                source,
                "imputed",
            )
        )
    for result in pending:
        pair = (names[result.home_name], names[result.away_name])
        records.append(_record(matrix.season, None, cutoff + timedelta(days=1), *pair, None, None, source, "unknown"))
    return records


def check_against_standings(
    records: list[dict[str, object]], standings: StandingsTable, matrix: ResultsMatrix, registry: ClubRegistry
) -> None:
    """A matriz e a predefinição de classificação são editadas à parte: precisam contar a mesma temporada.

    Pega placar vandalizado ou atrasado num dos dois e perda de pontos (não modelada: a ingestão falha).
    """
    if standings.updated.strip() != matrix.updated.strip():
        raise CompositionError(
            f"{matrix.season}: matriz atualizada em {matrix.updated!r} e classificação em {standings.updated!r}"
        )
    names = registry.resolve_many(standings.stats)
    adjusted = sorted(names[name] for name, points in standings.point_adjustments.items() if points)
    if adjusted:
        raise CompositionError(f"{matrix.season}: ajuste de pontos (STJD) não modelado: {adjusted}")
    computed: dict[str, list[int]] = {club: [0, 0, 0, 0, 0] for club in names.values()}
    for record in records:
        if record["status"] != MatchStatus.FINISHED.value:
            continue
        home, away = str(record["home_id"]), str(record["away_id"])
        home_goals, away_goals = int(str(record["home_goals"])), int(str(record["away_goals"]))
        for club, scored, conceded in ((home, home_goals, away_goals), (away, away_goals, home_goals)):
            stats = computed.setdefault(club, [0, 0, 0, 0, 0])
            stats[0 if scored > conceded else 1 if scored == conceded else 2] += 1
            stats[3] += scored
            stats[4] += conceded
    divergent = sorted(club for name, club in names.items() if tuple(computed[club]) != standings.stats[name])
    if divergent or set(computed) != set(names.values()):
        raise CompositionError(f"{matrix.season}: matriz e classificação divergem para {divergent}")


def season_start_from_wikitext(wikitext: str, season: int) -> date:
    found = SEASON_START_PATTERN.search(wikitext)
    start = parse_portuguese_day(found.group(1), season) if found else None
    if start is None:
        raise SourceFormatError(f"{season}: campo 'início' ausente na página")
    return start


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


def compose(raw_dir: Path, pins: SerieBPins, registry: ClubRegistry) -> Composition:
    openfootball_dir = raw_dir / OPENFOOTBALL_SOURCE / pins.openfootball_commit[:12]
    if not (openfootball_dir / "manifest.json").exists():
        raise CompositionError(f"openfootball {pins.openfootball_commit[:12]} não ingerido em {openfootball_dir}")
    openfootball = read_manifest(openfootball_dir)
    verify_files(openfootball_dir, openfootball)
    openfootball_tag = f"{OPENFOOTBALL_SOURCE}@{openfootball.version}"
    records: list[dict[str, object]] = []
    seasons_info: dict[str, object] = {}
    conferences: list[ScheduleConference] = []
    manifests = {openfootball_tag: openfootball}
    for season in pins.openfootball_seasons:
        if season in pins.wikipedia_closed_seasons:
            continue
        rows = parse_openfootball((openfootball_dir / f"{season}_br2.txt").read_text(encoding="utf-8"), season)
        records.extend(openfootball_season(rows, registry, openfootball_tag))
        seasons_info[str(season)] = {"results": openfootball_tag, "dates": openfootball_tag}
    for season, revision_id in sorted(pins.wikipedia_closed_seasons.items()):
        wiki_dir = raw_dir / WIKIPEDIA_SOURCE / f"{season}-r{revision_id}"
        if not (wiki_dir / "manifest.json").exists():
            raise CompositionError(f"Wikipédia {season} revisão {revision_id} não ingerida")
        wiki = read_manifest(wiki_dir)
        verify_files(wiki_dir, wiki)
        wiki_tag = f"{WIKIPEDIA_SOURCE}@{wiki.version}"
        manifests[wiki_tag] = wiki
        matrix = parse_wikipedia_matrix((wiki_dir / "page.wikitext").read_text(encoding="utf-8"), season)
        schedule = parse_openfootball((openfootball_dir / f"{season}_br2.txt").read_text(encoding="utf-8"), season)
        season_records, conference = wikipedia_with_schedule(matrix, schedule, registry, wiki_tag)
        if conference.score_mismatches:
            raise CompositionError(
                f"{season}: {conference.score_mismatches} placares divergem entre openfootball e Wikipédia"
            )
        records.extend(season_records)
        conferences.append(conference)
        seasons_info[str(season)] = {"results": wiki_tag, "dates": f"{openfootball_tag} (calendário)"}
    current = pins.current_season
    current_dir = _latest_dir(raw_dir / WIKIPEDIA_SOURCE, f"{current}-r")
    current_manifest = read_manifest(current_dir)
    verify_files(current_dir, current_manifest)
    current_tag = f"{WIKIPEDIA_SOURCE}@{current_manifest.version}"
    manifests[current_tag] = current_manifest
    wikitext = (current_dir / "page.wikitext").read_text(encoding="utf-8")
    matrix = parse_wikipedia_matrix(wikitext, current)
    current_records = current_season_from_matrix(
        matrix, season_start_from_wikitext(wikitext, current), registry, current_tag
    )
    if "standings.wikitext" not in current_manifest.files:
        raise CompositionError(f"{current}: ingestão sem a predefinição de classificação para conferência")
    standings = parse_wikipedia_standings((current_dir / "standings.wikitext").read_text(encoding="utf-8"), current)
    check_against_standings(current_records, standings, matrix, registry)
    records.extend(current_records)
    seasons_info[str(current)] = {"results": current_tag, "dates": "imputed"}
    reference_date = matrix.cutoff_date()
    if reference_date is None:
        raise CompositionError("temporada corrente sem data de atualização")
    collected_on = current_manifest.retrieved_at.astimezone(BRASILIA_TIMEZONE).date()
    if reference_date > collected_on:
        raise CompositionError(f"data de atualização {reference_date} posterior à coleta ({collected_on})")
    matches = pd.DataFrame.from_records(records, columns=MATCH_COLUMNS)
    duplicated = matches["match_id"].duplicated()
    if duplicated.any():
        raise CompositionError(f"match_id repetido: {matches.loc[duplicated, 'match_id'].head(3).tolist()}")
    for manifest in manifests.values():
        if not manifest.allows_public_display:
            raise CompositionError(f"{manifest.source_name} sem public_display_derived")
    sources = {
        "reference_date": reference_date.isoformat(),
        "seasons": seasons_info,
        "sources": [
            {
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
            for tag, manifest in manifests.items()
        ],
        "schedule_conference": [conference.__dict__ for conference in conferences],
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
