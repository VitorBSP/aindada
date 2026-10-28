"""Download da v18 no workflow: só arquivos fixados e com SHA-256 igual (dados sintéticos, sem rede)."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "infrastructure" / "scripts" / "fetch_adaoduque_v18.py"
SYNTHETIC_CSV = b"synthetic,not real data\n1,2\n"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fetch_adaoduque_v18", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_extracts_only_pinned_files() -> None:
    script = _load_script()
    payload = _zip({"pinned.csv": SYNTHETIC_CSV, "extra.csv": SYNTHETIC_CSV})
    contents = script.extract_pinned(payload, {"pinned.csv": hashlib.sha256(SYNTHETIC_CSV).hexdigest()})
    assert set(contents) == {"pinned.csv"}


def test_divergent_hash_fails() -> None:
    script = _load_script()
    payload = _zip({"pinned.csv": SYNTHETIC_CSV})
    with pytest.raises(SystemExit, match="SHA-256 divergente"):
        script.extract_pinned(payload, {"pinned.csv": "0" * 64})


def test_missing_pinned_file_fails() -> None:
    script = _load_script()
    payload = _zip({"other.csv": SYNTHETIC_CSV})
    with pytest.raises(SystemExit, match="ausentes"):
        script.extract_pinned(payload, {"pinned.csv": hashlib.sha256(SYNTHETIC_CSV).hexdigest()})


def test_repository_pins_cover_the_two_source_files() -> None:
    script = _load_script()
    pins = script.load_pinned_files(SCRIPT.parents[2] / "data" / "reference" / "source_pins.json")
    assert set(pins) == {"campeonato-brasileiro-full.csv", "campeonato-brasileiro-cartoes.csv"}
