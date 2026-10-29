"""Resumo do método por competição (D-040): o arquivo publicado acompanha as configurações versionadas."""

from __future__ import annotations

import json

from brasileirao.methods import OUTPUT, render_json


def test_methods_json_matches_versioned_configs() -> None:
    assert OUTPUT.read_text(encoding="utf-8") == render_json(), "rode: python -m brasileirao.methods"


def test_methods_cover_every_competition() -> None:

    ids = [competition["id"] for competition in json.loads(render_json())["competitions"]]
    assert ids == ["serie-a", "serie-b", "premier-league", "la-liga", "champions-league"]
