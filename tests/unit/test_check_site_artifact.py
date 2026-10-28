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


MODEL_VERSION = "synthetic-model-1"
HISTORY_PATH = f"seasons/{SEASON}/probability-history.json"


def _point(reference_date: str, reconstructed: Any = False, **extra: Any) -> dict[str, Any]:
    point = {
        "reference_date": reference_date,
        "generated_at": "2026-10-20T12:00:00+00:00",
        "model_version": MODEL_VERSION,
        "reconstructed": reconstructed,
        "n_simulations": 100,
    } | extra
    return {key: value for key, value in point.items() if value is not None}


PREDICTIONS_PATH = f"seasons/{SEASON}/predictions.json"
ROUNDS_PATH = f"seasons/{SEASON}/rounds.json"
CURRENT_ROUND_PATH = f"seasons/{SEASON}/current-round.json"
GENERATED_AT = "2026-10-20T12:00:00+00:00"
CLUBS = ("synthetic-a", "synthetic-b")


def _match(match_id: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"match_id": match_id, "status": status, "home_goals": None, "away_goals": None} | extra


def _view_values(title: float) -> dict[str, dict[str, float]]:
    """Visão sintética: valores por clube com uma métrica extra (`points`) que o baseline não carrega."""
    return {
        club: {"title": title / (index + 1), "top4": 0.9, "relegation": 0.05, "points": 60.0}
        for index, club in enumerate(CLUBS)
    }


def _baseline(**changes: Any) -> dict[str, Any]:
    teams = {
        club: {metric: values[metric] for metric in CHECKER.BASELINE_METRICS}
        for club, values in _view_values(0.5).items()
    }
    baseline = {
        "reference_date": "2026-10-13",
        "model_version": MODEL_VERSION,
        "n_simulations": 100,
        "reconstructed": True,
        "teams": teams,
    }
    return baseline | changes


def _round_info(**changes: Any) -> dict[str, Any]:
    info = {
        "round_number": 1,
        "state": "in_progress",
        "starts_on": "2026-10-18",
        "ends_on": "2026-10-21",
        "match_ids": ["m1", "m2"],
        "rescheduled_match_ids": ["m3"],
        "baseline": _baseline(),
    }
    return info | changes


def _current_round(**changes: Any) -> dict[str, Any]:
    current = {
        "synthetic": True,
        "schema_version": "1.0",
        "season": SEASON,
        "updated_at": GENERATED_AT,
        "model_version": MODEL_VERSION,
        "data_version": "synthetic-data-1",
        "round": _round_info(),
    }
    return current | changes


def _documents() -> dict[str, Any]:
    """Export mínimo e sintético (não é dado real), com os campos que o script lê."""
    return {
        "seasons.json": [
            {
                "season": SEASON,
                "latest_reference_date": "2026-10-20",
                "history_mode": "reconstructed",
                "synthetic": True,
            }
        ],
        PREDICTIONS_PATH: {
            "synthetic": True,
            "reference_date": "2026-10-20",
            "generated_at": GENERATED_AT,
            "seed": SEED,
            "model": {"model_version": "synthetic-model-1"},
            "data": {"version": "synthetic-data-1"},
            "teams": [{"club_id": club} for club in CLUBS],
            "matches": [
                _match("m1", "finished", home_goals=1, away_goals=0),
                _match("m2", "scheduled"),
                _match("m3", "postponed"),
            ],
        },
        HISTORY_PATH: [_point("2026-10-13", reconstructed=True), _point("2026-10-20")],
        ROUNDS_PATH: {
            "synthetic": True,
            "model_version": "synthetic-model-1",
            "data_version": "synthetic-data-1",
            "data_until": "2026-10-20",
            "seed": SEED,
            "rounds": [
                {"round_number": 0, "reference_date": "2026-10-13", "teams": _view_values(0.5)},
                {"round_number": 1, "reference_date": "2026-10-20", "teams": _view_values(0.6)},
            ],
        },
        CURRENT_ROUND_PATH: _current_round(),
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
    points = [_point(value) for value in dates]
    return {HISTORY_PATH: points}


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
    points = [_point("2026-10-20", n_simulations=None)]
    changes = {HISTORY_PATH: points}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        "probability-history com ponto sem n_simulations"
    ]


def test_unexpected_seed_fails(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path), SEASON, None, SEED + 1) == [
        f"semente de predictions é {SEED}, esperada {SEED + 1}",
        f"semente de rounds é {SEED}, esperada {SEED + 1}",
    ]


def test_history_point_with_other_seed_fails(tmp_path: Path) -> None:
    points = [_point("2026-10-20", seed=7)]
    changes = {HISTORY_PATH: points}
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


def _seasons_entry(**changes: Any) -> dict[str, Any]:
    entry = _documents()["seasons.json"][0] | changes
    return {"seasons.json": [{key: value for key, value in entry.items() if value is not None}]}


@pytest.mark.parametrize("mode", CHECKER.HISTORY_MODES)
def test_valid_history_mode_passes(tmp_path: Path, mode: str) -> None:
    assert CHECKER.check(_site(tmp_path, **_seasons_entry(history_mode=mode)), SEASON, None) == []


@pytest.mark.parametrize("mode", [None, "", "mixed"])
def test_missing_or_invalid_history_mode_fails(tmp_path: Path, mode: str | None) -> None:
    assert CHECKER.check(_site(tmp_path, **_seasons_entry(history_mode=mode)), SEASON, None) == [
        f"seasons.json com history_mode inválido para {SEASON}: {mode!r}"
    ]


def test_seasons_without_published_season_fails(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path, **_seasons_entry(season=SEASON - 1)), SEASON, None) == [
        f"seasons.json sem a temporada {SEASON}"
    ]


@pytest.mark.parametrize("generated_at", [None, "2026-10-20T12:00:00", "20/10/2026", 1760961600])
def test_history_point_without_aware_generated_at_fails(tmp_path: Path, generated_at: Any) -> None:
    point = _point("2026-10-20") | {"generated_at": generated_at}
    changes = {HISTORY_PATH: [point]}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        "probability-history[0] sem generated_at com fuso"
    ]


def test_history_point_with_brasilia_offset_passes(tmp_path: Path) -> None:
    changes = {HISTORY_PATH: [_point("2026-10-20", generated_at="2026-10-20T09:00:00-03:00")]}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == []


def test_history_point_without_model_version_fails(tmp_path: Path) -> None:
    changes = {HISTORY_PATH: [_point("2026-10-13", reconstructed=True, model_version=None), _point("2026-10-20")]}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == ["probability-history[0] sem model_version"]


@pytest.mark.parametrize("reconstructed", [None, "true", 1])
def test_history_point_without_boolean_reconstructed_fails(tmp_path: Path, reconstructed: Any) -> None:
    changes = {HISTORY_PATH: [_point("2026-10-13", reconstructed=reconstructed), _point("2026-10-20")]}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        "probability-history[0] sem reconstructed booleano"
    ]


def test_history_with_other_model_version_fails(tmp_path: Path) -> None:
    older = _point("2026-10-13", reconstructed=True, model_version="synthetic-model-0")
    changes = {HISTORY_PATH: [older, _point("2026-10-20")]}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        f"probability-history com model_version ['synthetic-model-0', '{MODEL_VERSION}'], esperado só {MODEL_VERSION}"
    ]


def test_reconstructed_last_point_fails(tmp_path: Path) -> None:
    changes = {HISTORY_PATH: [_point("2026-10-13", reconstructed=True), _point("2026-10-20", reconstructed=True)]}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        "último ponto de probability-history não tem reconstructed == false"
    ]


def _with_round(**changes: Any) -> dict[str, Any]:
    return {CURRENT_ROUND_PATH: _current_round(round=_round_info(**changes))}


def _with_baseline(**changes: Any) -> dict[str, Any]:
    return _with_round(baseline=_baseline(**changes))


def _predictions(**changes: Any) -> dict[str, Any]:
    return {PREDICTIONS_PATH: _documents()[PREDICTIONS_PATH] | changes}


def test_missing_current_round_with_matches_fails(tmp_path: Path) -> None:
    site_dir = _site(tmp_path)
    current_path = site_dir / "data" / "api" / CURRENT_ROUND_PATH
    current_path.unlink()
    assert CHECKER.check(site_dir, SEASON, None) == [f"ausente: {current_path.as_posix()}"]


def test_missing_current_round_without_matches_passes(tmp_path: Path) -> None:
    site_dir = _site(tmp_path, **_predictions(matches=[]))
    (site_dir / "data" / "api" / CURRENT_ROUND_PATH).unlink()
    assert CHECKER.check(site_dir, SEASON, None) == []


def test_invalid_current_round_json_fails(tmp_path: Path) -> None:
    site_dir = _site(tmp_path)
    (site_dir / "data" / "api" / CURRENT_ROUND_PATH).write_text("{", encoding="utf-8")
    assert CHECKER.check(site_dir, SEASON, None)[0].startswith("JSON inválido")


def test_null_round_passes(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path, **{CURRENT_ROUND_PATH: _current_round(round=None)}), SEASON, None) == []


def test_null_baseline_passes(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path, **_with_round(baseline=None)), SEASON, None) == []


@pytest.mark.parametrize("version", [None, "2.0", 1])
def test_unknown_current_round_schema_version_fails(tmp_path: Path, version: Any) -> None:
    changes = {CURRENT_ROUND_PATH: _current_round(schema_version=version)}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        f"current-round.schema_version {version!r} não suportado"
    ]


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("updated_at", "2026-10-13T12:00:00+00:00", GENERATED_AT),
        ("model_version", "synthetic-model-0", MODEL_VERSION),
        ("data_version", "synthetic-data-0", "synthetic-data-1"),
        ("season", SEASON - 1, SEASON),
    ],
)
def test_current_round_versions_different_from_predictions_fail(
    tmp_path: Path, key: str, value: Any, expected: Any
) -> None:
    changes = {CURRENT_ROUND_PATH: _current_round(**{key: value})}
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        f"current-round.{key} {value} diferente de {expected} do predictions.json"
    ]


def test_current_round_with_unknown_match_fails(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path, **_with_round(match_ids=["m1", "m9"])), SEASON, None) == [
        "current-round com jogos ausentes do predictions.json: ['m9']"
    ]


def test_current_round_with_unknown_rescheduled_match_fails(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path, **_with_round(rescheduled_match_ids=["m8"])), SEASON, None) == [
        "current-round com jogos ausentes do predictions.json: ['m8']"
    ]


def test_current_round_with_overlapping_lists_fails(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path, **_with_round(rescheduled_match_ids=["m2", "m3"])), SEASON, None) == [
        "current-round com jogos em match_ids e rescheduled_match_ids: ['m2']"
    ]


def test_current_round_without_lists_fails(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path, **_with_round(match_ids=None)), SEASON, None) == [
        "current-round.round sem as listas match_ids e rescheduled_match_ids"
    ]


def test_baseline_with_other_model_version_fails(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path, **_with_baseline(model_version="synthetic-model-0")), SEASON, None) == [
        f"current-round.baseline.model_version synthetic-model-0 diferente de {MODEL_VERSION}"
    ]


def test_baseline_with_missing_club_fails(tmp_path: Path) -> None:
    teams = {CLUBS[0]: _baseline()["teams"][CLUBS[0]]}
    assert CHECKER.check(_site(tmp_path, **_with_baseline(teams=teams)), SEASON, None)[0] == (
        f"current-round.baseline com clubes diferentes do snapshot: faltam ['{CLUBS[1]}'], sobram []"
    )


def test_baseline_with_extra_club_fails(tmp_path: Path) -> None:
    teams = _baseline()["teams"] | {"synthetic-z": {"title": 0.0, "top4": 0.0, "relegation": 1.0}}
    assert CHECKER.check(_site(tmp_path, **_with_baseline(teams=teams)), SEASON, None)[0] == (
        "current-round.baseline com clubes diferentes do snapshot: faltam [], sobram ['synthetic-z']"
    )


def test_baseline_not_before_starts_on_fails(tmp_path: Path) -> None:
    changes = _with_round(starts_on="2026-10-13")
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        "current-round.baseline.reference_date 2026-10-13 não é anterior a starts_on 2026-10-13"
    ]


def test_baseline_without_matching_view_fails(tmp_path: Path) -> None:
    assert CHECKER.check(_site(tmp_path, **_with_baseline(reference_date="2026-10-06")), SEASON, None) == [
        "current-round.baseline sem visão de 2026-10-06 no rounds.json"
    ]


@pytest.mark.parametrize("metric", CHECKER.BASELINE_METRICS)
def test_baseline_value_different_from_view_fails(tmp_path: Path, metric: str) -> None:
    teams = _baseline()["teams"]
    teams[CLUBS[1]] = teams[CLUBS[1]] | {metric: 0.123}
    assert CHECKER.check(_site(tmp_path, **_with_baseline(teams=teams)), SEASON, None) == [
        "current-round.baseline diferente da visão de 2026-10-13 do rounds.json"
    ]


def test_baseline_from_other_view_fails(tmp_path: Path) -> None:
    changes = _with_round(starts_on="2026-10-21", baseline=_baseline(reference_date="2026-10-20"))
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        "current-round.baseline diferente da visão de 2026-10-20 do rounds.json"
    ]


@pytest.mark.parametrize("status", ["scheduled", "postponed", "cancelled"])
def test_score_in_unfinished_match_fails(tmp_path: Path, status: str) -> None:
    matches = [_match("m1", "finished", home_goals=1, away_goals=0), _match("m2", status, home_goals=0)]
    changes = _predictions(matches=matches) | _with_round(rescheduled_match_ids=[])
    assert CHECKER.check(_site(tmp_path, **changes), SEASON, None) == [
        "predictions.json com placar em jogo não finished: ['m2']"
    ]


def test_current_round_summary_is_printed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    CHECKER.check(_site(tmp_path), SEASON, None)
    assert "rodada atual: 1 (in_progress)" in capsys.readouterr().out
