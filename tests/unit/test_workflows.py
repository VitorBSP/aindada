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


def test_token_is_scoped_to_ingest_steps() -> None:
    """ADR-0008, cláusula 6.1, generalizada no ADR-0011: o token só aparece em passos de ingestão."""
    steps = _text(PUBLISH).split("      - name: ")
    with_token = [step.splitlines()[0] for step in steps if "secrets.FOOTBALL_DATA_ORG_TOKEN" in step]
    assert with_token == ["Ingestão de publicação", "Ingestão das ligas europeias"]


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


# --- ADR-0009: atualizar-rodada.yml e inputs do publish-site ---------------------------------------

MATCH_UPDATES = ACTIVE / "atualizar-rodada.yml"


def test_match_updates_crons_are_12_37_and_18_37_brasilia() -> None:
    assert re.findall(r'cron:\s*"([^"]+)"', _text(MATCH_UPDATES)) == ["37 15 * * *", "37 21 * * *"]


def test_match_updates_requires_publish_switch_and_not_off() -> None:
    job = _text(MATCH_UPDATES).split("\n  watch:\n", 1)[1]
    assert all(clause in job for clause in ("vars.PUBLISH_ENABLED == 'true'", "vars.MATCH_UPDATES != 'off'"))


def test_match_updates_has_no_workflow_level_permissions() -> None:
    assert "\npermissions: {}\n" in _text(MATCH_UPDATES)


def test_match_updates_job_permissions_are_minimal() -> None:
    assert "    permissions:\n      contents: read\n      actions: write\n    steps:" in _text(MATCH_UPDATES)


def test_match_updates_job_fits_in_six_hours() -> None:
    assert "timeout-minutes: 360" in _text(MATCH_UPDATES)


def test_match_updates_uses_the_token_once() -> None:
    assert _text(MATCH_UPDATES).count("secrets.FOOTBALL_DATA_ORG_TOKEN") == 1


def test_match_updates_runs_script_isolated() -> None:
    assert "python -I infrastructure/scripts/match_updates.py" in _text(MATCH_UPDATES)


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda path: path.name)
def test_inputs_never_interpolated_inside_run(workflow: Path) -> None:
    """Inputs só entram nos scripts por variável de ambiente (ADR-0009, "Como publica")."""
    run_blocks = re.findall(r"run: [|>]-?\n((?:\s{10,}.*\n?)+)|run: (.*)", _text(workflow))
    code = "\n".join(block or line for block, line in run_blocks)
    assert "${{ inputs." not in code


def test_publish_site_has_trigger_and_match_ids_inputs() -> None:
    publish = _text(PUBLISH)
    assert all(name in publish for name in ("      trigger:\n", "      match_ids:\n", "run-name:"))


def test_publish_site_checks_match_ids_with_a_regex() -> None:
    assert '[[ "$MATCH_IDS" =~ ^([0-9]' in _text(PUBLISH)


def test_publish_site_keeps_its_concurrency_group() -> None:
    assert "concurrency:\n  group: publish-site\n  cancel-in-progress: false" in _text(PUBLISH)


# --- ADR-0010: Série B no mesmo artefato do Pages ----------------------------------------------------


def test_serie_b_failure_never_blocks_serie_a() -> None:
    assert re.search(r"id: serie_b\n\s+continue-on-error: true", _text(PUBLISH)) is not None


def test_serie_b_runs_its_gate_before_entering_the_artifact() -> None:
    text = _text(PUBLISH)
    assert text.index("brasileirao.serie_b.cli gate") < text.index('cp -r "$RUNNER_TEMP/serie-b" _site/serie-b')


def test_serie_b_steps_come_after_the_serie_a_artifact_check() -> None:
    text = _text(PUBLISH)
    assert text.index("check_site_artifact.py") < text.index("brasileirao.serie_b.cli ingest")


def test_serie_b_ingest_uses_no_secret() -> None:
    step = _text(PUBLISH).split("id: serie_b", 1)[1].split("- name:", 1)[0]
    assert "secrets." not in step


# --- ADR-0011: ligas europeias no mesmo artefato do Pages -------------------------------------------


def test_league_failures_never_block_the_rest() -> None:
    text = _text(PUBLISH)
    ingest = re.search(r"id: leagues_ingest\n\s+continue-on-error: true", text)
    forecast = re.search(r"id: leagues\n\s+continue-on-error: true", text)
    assert ingest is not None and forecast is not None


def test_league_forecast_step_uses_no_secret() -> None:
    step = _text(PUBLISH).split("id: leagues\n", 1)[1].split("- name:", 1)[0]
    assert "secrets." not in step


def test_league_fallback_runs_the_standalone_gate() -> None:
    step = _text(PUBLISH).split("Ligas europeias — incluir no artefato", 1)[1].split("- name:", 1)[0]
    assert 'brasileirao.leagues.cli "$league" gate --standalone' in step


# --- ADR-0013: Mundial de LoL no mesmo artefato do Pages ---------------------------------------------


def test_lol_failure_never_blocks_the_rest() -> None:
    assert re.search(r"id: lol\n\s+continue-on-error: true", _text(PUBLISH)) is not None


def test_lol_step_uses_no_secret() -> None:
    step = _text(PUBLISH).split("id: lol\n", 1)[1].split("- name:", 1)[0]
    assert "secrets." not in step


def test_lol_runs_its_gate_before_entering_the_artifact() -> None:
    text = _text(PUBLISH)
    assert text.index("brasileirao.esports.cli gate") < text.index(
        'cp -r "$RUNNER_TEMP/site-mundial-lol" _site/mundial-lol'
    )


def test_lol_fallback_runs_the_gate() -> None:
    step = _text(PUBLISH).split("Mundial de LoL — incluir no artefato", 1)[1].split("- name:", 1)[0]
    assert "brasileirao.esports.cli gate --site-dir _site/mundial-lol" in step
