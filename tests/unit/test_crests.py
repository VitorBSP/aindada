"""Escudos das outras competições (D-043): só funções puras, sem rede."""

from __future__ import annotations

import hashlib
import json

import pytest

from brasileirao.config import PATHS
from brasileirao.crests import (
    APPS,
    BADGE,
    FREE_LICENSES,
    badge_colors,
    contrast,
    load_sources,
    logo_file,
    provenance_path,
)


def test_badge_uses_ink_text_on_light_color() -> None:
    assert badge_colors(["#F2C300"])["fg"] == "#17191C"


def test_badge_uses_white_text_on_dark_color() -> None:
    assert badge_colors(["#002366"])["fg"] == "#FFFFFF"


def test_generic_wikidata_red_becomes_institutional_red() -> None:
    assert badge_colors(["#FF0000"])["bg"] == "#C8102E"


def test_badge_without_official_color_is_neutral() -> None:
    assert badge_colors([]) == BADGE


@pytest.mark.parametrize("background", ["#C8102E", "#1F3F8F", "#1E7B3A", "#F2C300", "#6CABDD", "#E2E1DB", "#FFFFFF"])
def test_badge_text_contrast_is_at_least_4_5(background: str) -> None:
    colors = badge_colors([background])
    assert contrast(colors["bg"], colors["fg"]) >= 4.5


def test_only_public_domain_and_cc0_are_free() -> None:
    assert frozenset({"Public domain", "CC0"}) == FREE_LICENSES


def test_logo_prefers_the_preferred_rank() -> None:
    claims = {
        "P154": [
            {"rank": "normal", "mainsnak": {"datavalue": {"value": "antigo.svg"}}},
            {"rank": "preferred", "mainsnak": {"datavalue": {"value": "atual.svg"}}},
            {"rank": "normal", "mainsnak": {"datavalue": {"value": "outro.svg"}}},
        ]
    }
    assert logo_file(claims) == "atual.svg"


@pytest.mark.parametrize("competition", sorted({row["competition"] for row in load_sources()}))
def test_every_crest_file_is_free_and_matches_its_sha256(competition: str) -> None:
    provenance = json.loads(provenance_path(competition).read_text(encoding="utf-8"))
    problems = []
    for team_id, record in provenance.items():
        if not record.get("file"):
            continue
        content = (PATHS.root / "apps" / APPS[competition] / "assets" / "crests" / record["file"]).read_bytes()
        if record["license"] not in FREE_LICENSES or hashlib.sha256(content).hexdigest() != record["sha256"]:
            problems.append(team_id)
    assert problems == []


@pytest.mark.parametrize("app", sorted(set(APPS.values())))
def test_every_png_in_the_app_has_provenance(app: str) -> None:
    files = {
        record["file"]
        for competition, target in APPS.items()
        if target == app
        for record in json.loads(provenance_path(competition).read_text(encoding="utf-8")).values()
        if record.get("file")
    }
    on_disk = {path.name for path in (PATHS.root / "apps" / app / "assets" / "crests").glob("*.png")}
    assert on_disk <= files
