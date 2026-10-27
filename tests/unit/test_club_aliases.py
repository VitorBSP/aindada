"""Aliases de clubes das fontes de publicação (ADR-0008, passo 4)."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

from brasileirao.data_pipeline.clubs import ClubRegistry, load_club_registry
from brasileirao.data_pipeline.football_data_org import FootballDataOrgSource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

FOOTBALL_DATA_ORG_NAMES = {
    "AC Goianiense": "atletico-go",
    "Botafogo FR": "botafogo",
    "CA Mineiro": "atletico-mg",
    "CA Paranaense": "athletico-pr",
    "Ceará SC": "ceara",
    "Chapecoense AF": "chapecoense",
    "Clube do Remo": "remo",
    "Coritiba FBC": "coritiba",
    "CR Flamengo": "flamengo",
    "CR Vasco da Gama": "vasco",
    "Criciúma EC": "criciuma",
    "Cruzeiro EC": "cruzeiro",
    "Cuiabá EC": "cuiaba",
    "EC Bahia": "bahia",
    "EC Juventude": "juventude",
    "EC Vitória": "vitoria",
    "Fluminense FC": "fluminense",
    "Fortaleza EC": "fortaleza",
    "Grêmio FBPA": "gremio",
    "Mirassol FC": "mirassol",
    "RB Bragantino": "bragantino",
    "Santos FC": "santos",
    "São Paulo FC": "sao-paulo",
    "SC Corinthians Paulista": "corinthians",
    "SC Internacional": "internacional",
    "SC Recife": "sport",
    "SE Palmeiras": "palmeiras",
}

# Nomes do formato Adão Duque observados em 2003–2023 (cópia local do formato) e "Mirassol", esperado em
# 2025; os nomes de 2024–2025 da v18 só serão confirmados depois do download (pendência do dono).
ADAODUQUE_NAMES = (
    "America-MG", "America-RN", "Athletico-PR", "Atletico-GO", "Atletico-MG", "Avai", "Bahia", "Barueri",
    "Botafogo-RJ", "Bragantino", "Brasiliense", "CSA", "Ceara", "Chapecoense", "Corinthians", "Coritiba",
    "Criciuma", "Cruzeiro", "Cuiaba", "Figueirense", "Flamengo", "Fluminense", "Fortaleza", "Goias", "Gremio",
    "Gremio Prudente", "Guarani", "Internacional", "Ipatinga", "Joinville", "Juventude", "Mirassol", "Nautico",
    "Palmeiras", "Parana", "Paysandu", "Ponte Preta", "Portuguesa", "Santa Cruz", "Santo Andre", "Santos",
    "Sao Caetano", "Sao Paulo", "Sport", "Vasco", "Vitoria",
)  # fmt: skip


def test_section_8_4_lists_27_names() -> None:
    assert len(FOOTBALL_DATA_ORG_NAMES) == 27


@pytest.mark.parametrize(("source_name", "club_id"), sorted(FOOTBALL_DATA_ORG_NAMES.items()))
def test_football_data_org_name_resolves(real_registry: ClubRegistry, source_name: str, club_id: str) -> None:
    assert real_registry.resolve(source_name) == club_id


@pytest.mark.parametrize("source_name", ADAODUQUE_NAMES)
def test_adaoduque_name_resolves(real_registry: ClubRegistry, source_name: str) -> None:
    assert source_name in real_registry.alias_index


def test_every_name_in_football_data_fixture_resolves(real_registry: ClubRegistry) -> None:
    payload = json.loads((FIXTURES / "football_data_org_names_synthetic.json").read_text(encoding="utf-8"))
    matches = FootballDataOrgSource.parse_matches(payload, 2032)
    names = {name for match in matches for name in (match.home_name, match.away_name)}
    assert set(real_registry.resolve_many(names).values()) == set(FOOTBALL_DATA_ORG_NAMES.values())


def test_every_alias_points_to_an_existing_club(real_registry: ClubRegistry) -> None:
    assert set(real_registry.alias_index.values()) <= set(real_registry.clubs)


def _folded(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character)).strip()


def test_no_alias_points_to_two_clubs_ignoring_case_and_accents(real_registry: ClubRegistry) -> None:
    owners: dict[str, set[str]] = {}
    for alias, club_id in real_registry.alias_index.items():
        owners.setdefault(_folded(alias), set()).add(club_id)
    assert {alias: ids for alias, ids in owners.items() if len(ids) > 1} == {}


def test_registry_rejects_alias_of_two_clubs(tmp_path: Path) -> None:
    clubs_path = tmp_path / "clubs.csv"
    clubs_path.write_text(
        "club_id,display_name,short_name,state,aliases\n"
        "sintetico-01,Sintético 01,S01,XX,Mesmo Nome\n"
        "sintetico-02,Sintético 02,S02,XX,Mesmo Nome\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ambíguo"):
        load_club_registry(clubs_path)
