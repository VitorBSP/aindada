"""Composição da Champions League (ADR-0012, Decisão 1).

- 2021/22–2025/26: openfootball, 7 ligas nacionais e Champions, Liga Europa e Conference (commits e
  SHA-256 fixados); ratings e treino.
- Temporada corrente: football-data.org, Champions (`CL`) e as 7 ligas (`PL`, `PD`, `BL1`, `SA`, `FL1`,
  `DED`, `PPL`); ratings e simulação.

Placar de 90 minutos para o modelo; prorrogação e pênaltis guardados à parte. Jogo cancelado ou com resultado
dado pela organização (W.O.) fica fora: não foi disputado.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from brasileirao.contracts import BRASILIA_TIMEZONE, MatchStatus, SourceManifest
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.europe.sources import parse_cup
from brasileirao.leagues.sources import (
    FOOTBALL_DATA_SOURCE,
    OPENFOOTBALL_SOURCE,
    openfootball_manifest,
    parse_football_data,
    parse_openfootball,
    read_manifest,
    verify_files,
    write_manifest,
)
from brasileirao.serie_b.sources import sha256_bytes

CUP_CODES = frozenset({"CL", "EL", "CONF"})
FINAL_STAGE = re.compile(r"(?:^|,\s*)Final$")
MATCH_COLUMNS = [
    "match_id",
    "season",
    "competition",
    "stage",
    "round",
    "match_date",
    "kickoff_utc",
    "home_id",
    "away_id",
    "home_goals",
    "away_goals",
    "extra_time_home",
    "extra_time_away",
    "penalties_home",
    "penalties_away",
    "neutral",
    "status",
    "source",
]


class CompositionError(ValueError):
    pass


@dataclass(frozen=True)
class EuropePins:
    current_season: int
    football_data: dict[str, str | None]
    timezones: dict[str, str]
    files: tuple[dict[str, Any], ...]


def load_europe_pins(path: Path) -> EuropePins:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return EuropePins(
        current_season=int(payload["current_season"]),
        football_data={str(code): country for code, country in payload["football_data"].items()},
        timezones={str(code): str(zone) for code, zone in payload["timezones"].items()},
        files=tuple(payload["openfootball"]),
    )


def local_name(entry: dict[str, Any]) -> str:
    return f"{entry['repo']}_{entry['path'].replace('/', '_')}"


def fetch_openfootball_files(raw_dir: Path, pins: EuropePins, get: Any) -> Path:
    """`get(url) -> bytes`. Grava cada arquivo fixado e o manifesto; SHA-256 diferente do fixado falha."""
    target_dir = raw_dir / OPENFOOTBALL_SOURCE / "europe"
    target_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for entry in pins.files:
        content: bytes = get(
            f"https://raw.githubusercontent.com/openfootball/{entry['repo']}/{entry['commit']}/{entry['path']}"
        )
        digest = sha256_bytes(content)
        if digest != entry["sha256"]:
            raise CompositionError(f"{entry['repo']}/{entry['path']}: SHA-256 {digest} difere do fixado")
        (target_dir / local_name(entry)).write_bytes(content)
        files[local_name(entry)] = digest
    manifest = openfootball_manifest("europe-multi", "pins", files, datetime.now(tz=UTC))
    write_manifest(
        target_dir, manifest.model_copy(update={"version": "europe-pins", "origin": "https://github.com/openfootball"})
    )
    return target_dir


def _record(**values: object) -> dict[str, object]:
    base: dict[str, object] = {column: None for column in MATCH_COLUMNS}
    base.update(values)
    return base


def history_records(raw_dir: Path, pins: EuropePins, registry: ClubRegistry) -> tuple[list[dict[str, object]], str]:
    source_dir = raw_dir / OPENFOOTBALL_SOURCE / "europe"
    manifest = read_manifest(source_dir)
    verify_files(source_dir, manifest)
    for entry in pins.files:
        if manifest.files.get(local_name(entry)) != entry["sha256"]:
            raise CompositionError(f"{local_name(entry)}: SHA-256 do manifesto difere do fixado")
    tag = f"{OPENFOOTBALL_SOURCE}@{manifest.version}"
    records: list[dict[str, object]] = []
    for entry in pins.files:
        text = (source_dir / local_name(entry)).read_text(encoding="utf-8")
        season = int(entry["season"])
        if entry["kind"] == "domestic":
            rows = parse_openfootball(text, season)
            names = registry.resolve_many({row.home_name for row in rows} | {row.away_name for row in rows})
            for row in rows:
                if row.home_goals is None or row.away_goals is None:
                    raise CompositionError(f"{entry['tag']} {season}: jogo sem placar no histórico")
                records.append(
                    _record(
                        match_id=f"{entry['tag']}-{season}-{names[row.home_name]}-{names[row.away_name]}",
                        season=season,
                        competition=entry["tag"],
                        stage="league",
                        round=row.round,
                        match_date=row.match_date,
                        home_id=names[row.home_name],
                        away_id=names[row.away_name],
                        home_goals=row.home_goals,
                        away_goals=row.away_goals,
                        neutral=False,
                        status=MatchStatus.FINISHED.value,
                        source=tag,
                    )
                )
            continue
        cup_rows = parse_cup(text, str(entry["tag"]), season)
        names = registry.resolve_many({cup.home_name for cup in cup_rows} | {cup.away_name for cup in cup_rows})
        for cup in cup_rows:
            if cup.home_goals is None or cup.away_goals is None:
                raise CompositionError(f"{entry['tag']} {season}: jogo sem placar no histórico")
            home, away = names[cup.home_name], names[cup.away_name]
            records.append(
                _record(
                    match_id=f"{entry['tag']}-{season}-{home}-{away}-{cup.match_date.isoformat()}",
                    season=season,
                    competition=entry["tag"],
                    stage=cup.stage,
                    match_date=cup.match_date,
                    home_id=home,
                    away_id=away,
                    home_goals=cup.home_goals,
                    away_goals=cup.away_goals,
                    extra_time_home=cup.extra_time[0] if cup.extra_time else None,
                    extra_time_away=cup.extra_time[1] if cup.extra_time else None,
                    penalties_home=cup.penalties[0] if cup.penalties else None,
                    penalties_away=cup.penalties[1] if cup.penalties else None,
                    neutral=bool(FINAL_STAGE.search(cup.stage)),
                    status=MatchStatus.FINISHED.value,
                    source=tag,
                )
            )
    return records, tag


def current_records(
    payload: dict[str, Any], code: str, season: int, timezone: str, registry: ClubRegistry, tag: str
) -> tuple[list[dict[str, object]], int]:
    """Jogos com resultado dado pela organização saem (devolve quantos); os demais seguem as regras das ligas."""
    played = [match for match in payload["matches"] if match["status"] != "AWARDED"]
    skipped = len(payload["matches"]) - len(played)
    parsed = parse_football_data({"matches": played}, season, timezone)
    records = []
    for raw, row in zip(played, parsed, strict=True):
        home = registry.resolve(f"fd:{raw['homeTeam']['id']}")
        away = registry.resolve(f"fd:{raw['awayTeam']['id']}")
        stage = str(raw.get("stage") or "REGULAR_SEASON")
        records.append(
            _record(
                match_id=f"{code}-{season}-{raw['id']}",
                season=season,
                competition=code if code in CUP_CODES else str(raw.get("_country", code)),
                stage=stage,
                round=row.round,
                match_date=row.match_date,
                kickoff_utc=row.kickoff_utc.isoformat() if row.kickoff_utc else None,
                home_id=home,
                away_id=away,
                home_goals=row.home_goals,
                away_goals=row.away_goals,
                neutral=stage == "FINAL",
                status=row.status.value,
                source=tag,
            )
        )
    return records, skipped


@dataclass(frozen=True)
class Composition:
    matches: pd.DataFrame
    sources: dict[str, Any]
    reference_date: date


def _latest(parent: Path, prefix: str) -> Path:
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


def compose(raw_dir: Path, pins: EuropePins, registry: ClubRegistry) -> Composition:
    records, history_tag = history_records(raw_dir, pins, registry)
    sources = [_source_info(history_tag, read_manifest(raw_dir / OPENFOOTBALL_SOURCE / "europe"))]
    awarded = 0
    reference_date: date | None = None
    for code, country in pins.football_data.items():
        api_dir = _latest(raw_dir / FOOTBALL_DATA_SOURCE, f"v4-{code}-")
        manifest = read_manifest(api_dir)
        verify_files(api_dir, manifest)
        tag = f"{FOOTBALL_DATA_SOURCE}@{manifest.version}"
        payload = json.loads((api_dir / f"{code}_{pins.current_season}.json").read_text(encoding="utf-8"))
        for match in payload["matches"]:
            match["_country"] = country or code
        timezone = pins.timezones["CL" if country is None else country]
        rows, skipped = current_records(payload, code, pins.current_season, timezone, registry, tag)
        awarded += skipped
        records.extend(rows)
        sources.append(_source_info(tag, manifest))
        if code == "CL":
            finished = [row["match_date"] for row in rows if row["status"] == MatchStatus.FINISHED.value]
            if not finished:
                raise CompositionError("Champions League sem jogo encerrado na temporada corrente")
            reference_date = max(value for value in finished if isinstance(value, date))
            collected_on = manifest.retrieved_at.astimezone(BRASILIA_TIMEZONE).date()
            if reference_date > collected_on:
                raise CompositionError(f"jogo encerrado em {reference_date}, depois da coleta ({collected_on})")
    if reference_date is None:
        raise CompositionError("Champions League ausente das fontes fixadas")
    matches = pd.DataFrame.from_records(records, columns=MATCH_COLUMNS)
    duplicated = matches["match_id"].duplicated()
    if duplicated.any():
        raise CompositionError(f"match_id repetido: {matches.loc[duplicated, 'match_id'].head(3).tolist()}")
    return Composition(
        matches.sort_values(["match_date", "match_id"]).reset_index(drop=True),
        {
            "competition": "champions-league",
            "reference_date": reference_date.isoformat(),
            "awarded_skipped": awarded,
            "sources": sources,
        },
        reference_date,
    )


def write_silver(composition: Composition, silver_dir: Path) -> None:
    silver_dir.mkdir(parents=True, exist_ok=True)
    composition.matches.to_csv(silver_dir / "matches.csv", index=False)
    (silver_dir / "sources.json").write_text(
        json.dumps(composition.sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def read_silver(silver_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    matches_data = pd.read_csv(silver_dir / "matches.csv", parse_dates=["match_date"])
    for column in (
        "round",
        "home_goals",
        "away_goals",
        "extra_time_home",
        "extra_time_away",
        "penalties_home",
        "penalties_away",
    ):
        matches_data[column] = matches_data[column].astype("Int64")
    sources = json.loads((silver_dir / "sources.json").read_text(encoding="utf-8"))
    return matches_data, sources
