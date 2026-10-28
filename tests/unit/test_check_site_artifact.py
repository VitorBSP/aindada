"""Checagens do artefato do Pages (`check_site_artifact.py`) sobre um export sintético, sem rede."""

from __future__ import annotations

import importlib.util
import io
import json
import urllib.error
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "infrastructure" / "scripts" / "check_site_artifact.py"
SEASON = 2026
SEED = 2026
LIVE_URL = "https://synthetic.github.io/site/data/api/seasons/2026/predictions.json"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_site_artifact", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = _load_script()


def _documents() -> dict[str, Any]:
    """Export mínimo e sintético (não é dado real), com os campos que o script lê."""
    return {
        "seasons.json": [{"season": SEASON, "latest_reference_date": "2026-10-20", "synthetic": True}],
        f"seasons/{SEASON}/predictions.json": {
            "synthetic": True,
            "reference_date": "2026-10-20",
            "seed": SEED,
            "model": {"model_version": "synthetic-model-1"},
            "data": {"version": "synthetic-data-1"},
        },
        f"seasons/{SEASON}/probability-history.json": [
            {"reference_date": "2026-10-13", "n_simulations": 100},
            {"reference_date": "2026-10-20", "n_simulations": 100},
        ],
        f"seasons/{SEASON}/rounds.json": {
            "synthetic": True,
            "model_version": "synthetic-model-1",
            "data_version": "synthetic-data-1",
            "data_until": "2026-10-20",
            "seed": SEED,
            "rounds": [{"round": 1}],
        },
        "models/metrics.json": {"synthetic": True, "model_version": "synthetic-model-1"},
    }


def _write_site(site_dir: Path, documents: dict[str, Any]) -> Path:
    for relative_path, document in documents.items():
        target = site_dir / "data" / "api" / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document), encoding="utf-8")
    return site_dir


def _site(tmp_path: Path, **changes: Any) -> Path:
    documents = _documents()
    for key, value in changes.items():
        documents[key] = value
    return _write_site(tmp_path / "_site", documents)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise urllib.error.URLError("rede desligada nos testes")

    monkeypatch.setattr(CHECKER.urllib.request, "urlopen", refuse)


def _live_site(monkeypatch: pytest.MonkeyPatch, reference_date: str) -> list[str]:
    requested: list[str] = []

    def answer(url: str, timeout: int) -> io.BytesIO:
        requested.append(url)
        return io.BytesIO(json.dumps({"reference_date": reference_date}).encode())

    monkeypatch.setattr(CHECKER.urllib.request, "urlopen", answer)
    return requested


def _history(*dates: str) -> dict[str, Any]:
    points = [{"reference_date": value, "n_simulations": 100} for value in dates]
    return {f"seasons/{SEASON}/probability-history.json": points}


def test_synthetic_export_passes(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path), SEASON, None, SEED) == []


def test_reference_date_regression_against_live_site_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _live_site(monkeypatch, "2026-10-27")
    assert CHECKER.check(_site(tmp_path), SEASON, LIVE_URL) == [
        "reference_date regrediu: no ar 2026-10-27, novo 2026-10-20"
    ]


def test_same_or_older_live_reference_date_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _live_site(monkeypatch, "2026-10-20")
    assert CHECKER.check(_site(tmp_path), SEASON, LIVE_URL) == []


def test_live_url_is_requested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requested = _live_site(monkeypatch, "2026-10-01")
    CHECKER.check(_site(tmp_path), SEASON, LIVE_URL)
    assert requested == [LIVE_URL]


def test_unreachable_live_site_skips_regression_check(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path), SEASON, LIVE_URL) == []


@pytest.mark.parametrize("crest", CHECKER.NON_FREE_CRESTS)
def test_non_free_crest_in_artifact_fails(tmp_path: Path, crest: str) -> None:
    site_dir = _site(tmp_path)
    (site_dir / "assets" / "crests").mkdir(parents=True)
    (site_dir / "assets" / "crests" / crest).write_bytes(b"synthetic")
    assert CHECKER.check(site_dir, SEASON, None)[0].startswith("escudos não livres no artefato")


def test_divergent_model_version_fails(tmp_path: Path) -> None:
    metrics = {"models/metrics.json": {"model_version": "synthetic-model-0"}}
    assert CHECKER.check(_site(tmp_path, **metrics), SEASON, None)[0].startswith("model_version divergente")


def test_divergent_data_version_fails(tmp_path: Path) -> None:
    rounds = _documents()[f"seasons/{SEASON}/rounds.json"] | {"data_version": "synthetic-data-0"}
    changes = {f"seasons/{SEASON}/rounds.json": rounds}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        "data_version de rounds.json diferente da do snapshot"
    ]


def test_data_until_different_from_reference_date_fails(tmp_path: Path) -> None:
    rounds = _documents()[f"seasons/{SEASON}/rounds.json"] | {"data_until": "2026-10-13"}
    changes = {f"seasons/{SEASON}/rounds.json": rounds}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        "rounds.data_until 2026-10-13 diferente de reference_date 2026-10-20"
    ]


def test_history_with_future_date_fails(tmp_path: Path) -> None:
    changes = _history("2026-10-13", "2026-10-27")
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        "probability-history tem data posterior ao snapshot"
    ]


def test_empty_history_fails(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path, **_history()), SEASON, None) == ["probability-history vazio"]


def test_history_point_without_simulations_fails(tmp_path: Path) -> None:
    points = [{"reference_date": "2026-10-20"}]
    changes = {f"seasons/{SEASON}/probability-history.json": points}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        "probability-history com ponto sem n_simulations"
    ]


def test_unexpected_seed_fails(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path), SEASON, None, SEED + 1) == [
        f"semente de predictions é {SEED}, esperada {SEED + 1}",
        f"semente de rounds é {SEED}, esperada {SEED + 1}",
    ]


def test_history_point_with_other_seed_fails(tmp_path: Path) -> None:
    points = [{"reference_date": "2026-10-20", "n_simulations": 100, "seed": 7}]
    changes = {f"seasons/{SEASON}/probability-history.json": points}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None, SEED) == [
        f"semente de probability-history[0] é 7, esperada {SEED}"
    ]


def test_missing_document_fails(tmp_path: Path) -> None:
    site_dir = _site(tmp_path)
    (site_dir / "data" / "api" / "models" / "metrics.json").unlink()
    assert CHECKER.check(site_dir, SEASON, None) == [
        f"ausente: {(site_dir / 'data/api/models/metrics.json').as_posix()}"
    ]


def test_invalid_json_fails(tmp_path: Path) -> None:
    site_dir = _site(tmp_path)
    (site_dir / "data" / "api" / "seasons.json").write_text("{", encoding="utf-8")
    assert CHECKER.check(site_dir, SEASON, None)[0].startswith("JSON inválido")


def test_main_exits_with_error_when_a_check_fails(tmp_path: Path) -> None:
    site_dir = _site(tmp_path, **_history("2026-10-27"))
    with pytest.raises(SystemExit) as raised:
        CHECKER.main(["--site-dir", str(site_dir), "--season", str(SEASON), "--seed", str(SEED)])
    assert raised.value.code == 1
