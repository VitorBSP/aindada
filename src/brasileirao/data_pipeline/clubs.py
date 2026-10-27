"""Registro canônico de clubes e resolução de aliases das fontes."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from brasileirao.config import PATHS
from brasileirao.contracts import Club


class UnknownClubError(KeyError):
    def __init__(self, unknown_names: Iterable[str]) -> None:
        self.unknown_names = sorted(set(unknown_names))
        super().__init__(f"clubes sem mapeamento canônico: {self.unknown_names}")


@dataclass(frozen=True)
class ClubRegistry:
    clubs: dict[str, Club]
    alias_index: dict[str, str]

    def resolve(self, source_name: str) -> str:
        normalized_name = source_name.strip()
        if normalized_name in self.alias_index:
            return self.alias_index[normalized_name]
        raise UnknownClubError([normalized_name])

    def resolve_many(self, source_names: Iterable[str]) -> dict[str, str]:
        unique_names = {name.strip() for name in source_names}
        unknown_names = [name for name in unique_names if name not in self.alias_index]
        if unknown_names:
            raise UnknownClubError(unknown_names)
        return {name: self.alias_index[name] for name in unique_names}

    def display_name(self, club_id: str) -> str:
        return self.clubs[club_id].display_name


def load_club_registry(path: Path | None = None) -> ClubRegistry:
    registry_path = path or PATHS.clubs_reference
    clubs: dict[str, Club] = {}
    alias_index: dict[str, str] = {}
    with registry_path.open(encoding="utf-8") as registry_file:
        for row in csv.DictReader(registry_file):
            aliases = tuple(alias.strip() for alias in row["aliases"].split("|") if alias.strip())
            club = Club(
                club_id=row["club_id"],
                display_name=row["display_name"],
                short_name=row["short_name"],
                state=row["state"],
                aliases=aliases,
            )
            clubs[club.club_id] = club
            for alias in (*aliases, club.display_name, club.club_id):
                existing_id = alias_index.get(alias)
                if existing_id is not None and existing_id != club.club_id:
                    raise ValueError(f"alias '{alias}' ambíguo: {existing_id} e {club.club_id}")
                alias_index[alias] = club.club_id
    return ClubRegistry(clubs=clubs, alias_index=alias_index)
