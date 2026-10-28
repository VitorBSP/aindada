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


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_no_workflow_depends_on_event_repository_payload(workflow: Path) -> None:
    """`github.event.repository.*` pode vir vazio no `schedule` (ajuste 3 do 00)."""
    code = "\n".join(line for line in _text(workflow).splitlines() if not line.lstrip().startswith("#"))
    assert "github.event.repository" not in code


def test_live_url_is_built_from_github_repository() -> None:
    expected = 'live_url="https://${GITHUB_REPOSITORY%%/*}.github.io/${GITHUB_REPOSITORY#*/}/data/api/seasons/'
    assert expected in _text(PUBLISH)


def test_artifact_check_receives_the_live_url() -> None:
    assert '--live-url "${live_url,,}"' in _text(PUBLISH)


def test_upload_requires_publish_switch_or_private_repository_from_api() -> None:
    upload_step = re.compile(
        r"if: vars\.PUBLISH_ENABLED == 'true' \|\| steps\.visibility\.outputs\.private == 'true'\n"
        r"\s+uses: actions/upload-pages-artifact@"
    )
    assert upload_step.search(_text(PUBLISH)) is not None


def test_private_visibility_defaults_to_false_when_the_api_fails() -> None:
    assert '[ "$private" = "true" ] || private=false' in _text(PUBLISH)


def test_snapshot_database_lives_outside_the_checkout() -> None:
    publish = _text(PUBLISH)
    isolation = publish.index('BRASILEIRAO_SNAPSHOT_DB=$RUNNER_TEMP/snapshots/snapshots.sqlite" >> "$GITHUB_ENV"')
    assert isolation < publish.index("brasileirao.cli simulate")


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_actions_are_pinned_by_commit_sha(workflow: Path) -> None:
    references = re.findall(r"uses:\s*(\S+)", _text(workflow))
    assert [ref for ref in references if re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref) is None] == []


def test_schedule_avoids_minute_zero() -> None:
    crons = re.findall(r'cron:\s*"(\S+) ', _text(PUBLISH))
    assert crons and "0" not in crons


def test_summary_lists_sha256_of_exported_json() -> None:
    assert "xargs sha256sum" in _text(PUBLISH)
