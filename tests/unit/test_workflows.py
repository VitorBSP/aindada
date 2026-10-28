"""Invariantes dos workflows do GitHub Actions (ADR-0008: cláusula 6.1, Decisão 3 e G5). Checagem textual."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = ROOT / ".github" / "workflows"
COPIES = ROOT / "infrastructure" / "github-workflows"
WORKFLOWS = sorted(ACTIVE.glob("*.yml"))
PUBLISH = ACTIVE / "publish-site.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_copies_match_active_workflows() -> None:
    copies = {path.name: _text(path) for path in COPIES.glob("*.yml")}
    assert copies == {path.name: _text(path) for path in WORKFLOWS}


@pytest.mark.parametrize("workflow", [path for path in WORKFLOWS if "secrets." in _text(path)], ids=str)
def test_workflow_with_secrets_never_runs_on_pull_requests(workflow: Path) -> None:
    assert re.search(r"^\s*pull_request", _text(workflow), flags=re.MULTILINE) is None


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_no_workflow_uploads_data_files(workflow: Path) -> None:
    assert re.search(r"\.sqlite|\.csv|data/(raw|silver|gold|snapshots)/", _upload_paths(_text(workflow))) is None


def _upload_paths(text: str) -> str:
    """Linhas de cada passo `actions/upload-*`, do `uses:` até o próximo passo."""
    selected: list[str] = []
    inside = False
    for line in text.splitlines():
        if re.match(r"\s*- ", line):
            inside = False
        if "uses: actions/upload-" in line:
            inside = True
        if inside:
            selected.append(line)
    return "\n".join(selected)


def test_deploy_requires_publish_switch() -> None:
    deploy = _text(PUBLISH).split("\n  deploy:\n", 1)[1]
    assert "if: vars.PUBLISH_ENABLED == 'true'" in deploy


def test_publish_runs_gate_with_explicit_season() -> None:
    assert 'publication-gate --season "$SEASON"' in _text(PUBLISH)


def test_token_is_scoped_to_the_ingest_step() -> None:
    assert _text(PUBLISH).count("secrets.FOOTBALL_DATA_ORG_TOKEN") == 1
