"""Adaptador do dataset "Campeonato Brasileiro de Futebol" de Adão Duque, Kaggle versão 18 (2003–2025).

Fonte de publicação do histórico (ADR-0008). O adaptador não baixa nada: lê os arquivos que o dono do
produto baixou do Kaggle para `data/raw/adaoduque/v18/` e confere o SHA-256 de cada um contra os
hashes fixados em `data/reference/source_pins.json`. O espelho do GitHub serve só para comparar
hashes, nunca como fonte.

Formato (Legenda do dataset): `ID`, `rodata`, `data` (dd/mm/aaaa), `hora`, `mandante`, `visitante`,
`mandante_Placar`, `visitante_Placar`, entre outras colunas. A data é tratada como data de Brasília,
sem conversão. Não há coluna de temporada: a temporada é o ano da data, exceto a de 2020, disputada
até fevereiro de 2021.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from brasileirao.contracts import AllowedUse, LicenseStatus, MatchStatus
from brasileirao.data_pipeline.sources import RawCard, RawMatch, SourceSnapshot

MATCHES_FILE = "campeonato-brasileiro-full.csv"
CARDS_FILE = "campeonato-brasileiro-cartoes.csv"
SOURCE_FILES = {"matches": MATCHES_FILE, "cards": CARDS_FILE}
CROSS_YEAR_SEASONS = {2020: (date(2020, 8, 1), date(2021, 2, 28))}


class AdaoDuqueFilesError(FileNotFoundError):
    """Arquivos da versão fixada ausentes ou com hash diferente do registrado."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def season_of(match_date: date) -> int:
    for season, (first_day, last_day) in CROSS_YEAR_SEASONS.items():
        if first_day <= match_date <= last_day:
            return season
    return match_date.year


def _column(row: dict[str, str], *names: str) -> str:
    lowered = {key.strip().lower(): value for key, value in row.items() if key is not None}
    for name in names:
        if name.lower() in lowered:
            return (lowered[name.lower()] or "").strip()
    raise KeyError(f"coluna ausente: {names}")


def _goals(text: str) -> int | None:
    return None if text in ("", "-") else int(float(text))


@dataclass(frozen=True)
class PinnedFiles:
    version: str
    origin: str
    files: dict[str, str]


def load_pins(pins_path: Path, source_name: str) -> PinnedFiles:
    if not pins_path.exists():
        raise AdaoDuqueFilesError(f"arquivo de hashes fixados ausente: {pins_path}")
    entry = json.loads(pins_path.read_text(encoding="utf-8")).get(source_name) or {}
    return PinnedFiles(
        version=str(entry.get("version", "")),
        origin=str(entry.get("origin", "")),
        files={str(name): str(digest) for name, digest in (entry.get("files") or {}).items()},
    )


class AdaoDuqueSource:
    source_name = "adaoduque_kaggle"
    origin = "https://www.kaggle.com/datasets/adaoduque/campeonato-brasileiro-de-futebol"
    version = "kaggle-v18"
    raw_dir_name = "v18"
    license_status = LicenseStatus.LICENSED_WITH_ATTRIBUTION
    allowed_uses = (
        AllowedUse.RESEARCH_LOCAL,
        AllowedUse.PROTOTYPE_LOCAL,
        AllowedUse.PUBLIC_DISPLAY_DERIVED,
        AllowedUse.REDISTRIBUTION,
    )
    license_name = "GPL-2.0 (declarada no Kaggle, versão 18; 'only' ou 'or later' não especificado)"
    terms_url = "https://www.kaggle.com/datasets/adaoduque/campeonato-brasileiro-de-futebol"
    terms_checked_at = date(2026, 10, 27)
    attribution = (
        'Dados históricos (2003–2025): "Campeonato Brasileiro de Futebol", de Adão Duque, Kaggle, versão 18, '
        "sob a licença GPL-2.0"
    )
    license_notes = (
        "GPL-2 declarada no Kaggle (v18). Coleta do autor 'de páginas do Google' (proveniência de segunda mão, "
        "risco aceito no ADR-0008). Redistribuição exigiria o texto da GPL-2, o aviso de origem e a mesma licença, "
        "e um ADR próprio: o projeto não redistribui. Texto de atribuição provisório até a aprovação do C2 "
        "(Agente 08 e dono do produto)."
    )

    def __init__(self, input_dir: Path, pins_path: Path) -> None:
        self.input_dir = input_dir
        self.pins_path = pins_path

    def verify_files(self) -> dict[str, Path]:
        """Confere presença e SHA-256 dos arquivos contra os hashes fixados; falha com mensagem clara."""
        missing = [name for name in SOURCE_FILES.values() if not (self.input_dir / name).is_file()]
        if missing:
            raise AdaoDuqueFilesError(
                f"arquivos da versão 18 do Adão Duque ausentes em {self.input_dir}: {missing}. Baixe-os do Kaggle "
                f"({self.origin}, versão 18) para essa pasta; pendência do dono do produto (ADR-0008)"
            )
        pins = load_pins(self.pins_path, self.source_name)
        if pins.version != self.version or not all(pins.files.get(name) for name in SOURCE_FILES.values()):
            raise AdaoDuqueFilesError(
                f"hashes da {self.version} não fixados em {self.pins_path}. Depois de conferir o download contra o "
                "espelho do GitHub, registre-os com `brasileirao pin-adaoduque` e versione o arquivo"
            )
        mismatched = [name for name in SOURCE_FILES.values() if _sha256(self.input_dir / name) != pins.files[name]]
        if mismatched:
            raise AdaoDuqueFilesError(
                f"SHA-256 diferente do fixado para {mismatched} em {self.input_dir}: o arquivo não é a {self.version}"
            )
        return {logical: self.input_dir / name for logical, name in SOURCE_FILES.items()}

    def snapshot(self) -> SourceSnapshot:
        files = self.verify_files()
        downloaded_at = max(path.stat().st_mtime for path in files.values())
        return SourceSnapshot(
            source_name=self.source_name,
            origin=self.origin,
            version=self.version,
            retrieved_at=datetime.fromtimestamp(downloaded_at, tz=UTC).replace(microsecond=0),
            files=files,
            license_status=self.license_status,
            license_notes=self.license_notes,
            allowed_uses=self.allowed_uses,
            license_name=self.license_name,
            terms_url=self.terms_url,
            terms_checked_at=self.terms_checked_at,
            attribution=self.attribution,
            raw_dir_name=self.raw_dir_name,
        )

    def pin_current_files(self) -> dict[str, str]:
        """Grava os SHA-256 dos arquivos presentes como a versão fixada (passo humano, depois da conferência)."""
        missing = [name for name in SOURCE_FILES.values() if not (self.input_dir / name).is_file()]
        if missing:
            raise AdaoDuqueFilesError(f"arquivos ausentes em {self.input_dir}: {missing}")
        hashes = {name: _sha256(self.input_dir / name) for name in SOURCE_FILES.values()}
        document = json.loads(self.pins_path.read_text(encoding="utf-8")) if self.pins_path.exists() else {}
        document[self.source_name] = {"version": self.version, "origin": self.origin, "files": hashes}
        self.pins_path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return hashes

    @staticmethod
    def parse_matches(matches_path: Path) -> list[RawMatch]:
        parsed_matches: list[RawMatch] = []
        with matches_path.open(encoding="utf-8-sig", newline="") as matches_file:
            for row in csv.DictReader(matches_file):
                match_date = datetime.strptime(_column(row, "data"), "%d/%m/%Y").date()
                round_text = _column(row, "rodata", "rodada")
                home_goals = _goals(_column(row, "mandante_Placar"))
                away_goals = _goals(_column(row, "visitante_Placar"))
                has_score = home_goals is not None and away_goals is not None
                parsed_matches.append(
                    RawMatch(
                        source_match_id=_column(row, "ID"),
                        season=season_of(match_date),
                        round=int(round_text) if round_text else None,
                        match_date=match_date,
                        home_name=_column(row, "mandante"),
                        away_name=_column(row, "visitante"),
                        home_goals=home_goals if has_score else None,
                        away_goals=away_goals if has_score else None,
                        status=MatchStatus.FINISHED if has_score else MatchStatus.SCHEDULED,
                    )
                )
        return parsed_matches

    @staticmethod
    def parse_cards(cards_path: Path, matches: list[RawMatch]) -> list[RawCard]:
        season_by_match = {match.source_match_id: match.season for match in matches}
        cards: list[RawCard] = []
        with cards_path.open(encoding="utf-8-sig", newline="") as cards_file:
            for row in csv.DictReader(cards_file):
                match_id = _column(row, "partida_id")
                club_name = _column(row, "clube")
                if match_id not in season_by_match or not club_name:
                    continue
                cards.append(
                    RawCard(
                        source_match_id=match_id,
                        season=season_by_match[match_id],
                        club_name=club_name,
                        card_color=_column(row, "cartao"),
                    )
                )
        return cards
