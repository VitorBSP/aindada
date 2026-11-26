"""simulator-cloud.js no Node: filtro de apelidos, mesma lista da sugestão SQL e SDK com versão e SRI fixos.

Apelidos de teste inventados. Sem Node no ambiente, os testes que rodam JS são pulados.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from functools import cache
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLOUD = ROOT / "apps" / "web" / "assets" / "simulator-cloud.js"
CONFIG = ROOT / "apps" / "web" / "assets" / "simulator-config.js"
SUGGESTION = ROOT / "infrastructure" / "supabase" / "sugestoes" / "apelidos_bloqueados.sql"
NODE = shutil.which("node")

HARNESS = """
const fs = require("fs");
const vm = require("vm");
const [cloudPath] = process.argv.slice(1);
const nicknames = JSON.parse(fs.readFileSync(0, "utf8"));
const context = { console, JSON, Map, Set, Promise, String, RegExp };
context.window = context;
context.AINDA_DA_SIMULATOR = { supabaseUrl: "https://example.invalid", supabaseAnonKey: "chave-publica-de-teste" };
vm.createContext(context);
vm.runInContext(fs.readFileSync(cloudPath, "utf8"), context);
const cloud = context.SimulatorCloud;
process.stdout.write(JSON.stringify({
  problems: Object.fromEntries(nicknames.map((nickname) => [nickname, cloud.nicknameProblem(nickname)])),
  blocked: cloud.BLOCKED_NICKNAMES,
  captcha: cloud.captchaEnabled,
}));
"""

BLOCKED = ["C4R4LH0 fc", "Pútaaaa", "cu de mae", "Admin", "Oficial AIndaDa", "filho.da.puta", "VIADO", "porrraaa"]
ALLOWED = ["Ana Tricolor", "Computador", "Cuca 10", "Rolando", "Picanha", "Bichano", "Fogão 1904", "Iporá"]


@cache
def _run() -> dict[str, Any]:
    assert NODE is not None
    completed = subprocess.run(
        [NODE, "-e", HARNESS, str(CLOUD)],
        input=json.dumps(BLOCKED + ALLOWED),
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    result: dict[str, Any] = json.loads(completed.stdout)
    return result


def _sql_terms() -> dict[str, list[str]]:
    text = SUGGESTION.read_text(encoding="utf-8")
    terms: dict[str, list[str]] = {}
    for kind, values in re.findall(r"select term, '(\w+)' from unnest\(array\[(.*?)\]\)", text, re.S):
        terms[kind] = re.findall(r"'([a-z]+)'", values)
    return terms


needs_node = pytest.mark.skipif(NODE is None, reason="Node indisponível")


@needs_node
@pytest.mark.parametrize("nickname", BLOCKED)
def test_offensive_nickname_is_refused(nickname: str) -> None:
    assert "ofensivo" in _run()["problems"][nickname]


@needs_node
@pytest.mark.parametrize("nickname", ALLOWED)
def test_ordinary_nickname_passes(nickname: str) -> None:
    assert _run()["problems"][nickname] == ""


@needs_node
def test_browser_and_sql_block_the_same_terms() -> None:
    assert _run()["blocked"] == _sql_terms()


@needs_node
def test_captcha_is_off_without_site_key() -> None:
    assert _run()["captcha"] is False


def test_sdk_is_pinned_with_sri() -> None:
    source = CLOUD.read_text(encoding="utf-8")
    url = re.search(r'LIBRARY_URL = "([^"]+)"', source)
    integrity = re.search(r'LIBRARY_INTEGRITY = "(sha384-[A-Za-z0-9+/]{64})"', source)
    assert url and integrity and re.search(r"@\d+\.\d+\.\d+/", url.group(1))


def test_production_config_keeps_captcha_off() -> None:
    assert 'turnstileSiteKey: ""' in CONFIG.read_text(encoding="utf-8")
