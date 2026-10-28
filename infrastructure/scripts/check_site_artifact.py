"""Checagens do artefato do Pages que complementam o `publication-gate` (ADR-0007, itens 5, 6 e 8).

- os JSON obrigatórios do export existem e são JSON válidos;
- `model_version` igual em `predictions`, `rounds` e `metrics`; `data_version` igual em `predictions` e `rounds`;
- `rounds.data_until` igual à `reference_date` do snapshot;
- semente de `predictions` e `rounds` igual à esperada (`--seed`, opcional);
- `probability-history` sem data posterior à do snapshot e com número de simulações em cada ponto (os pontos
  não trazem semente no export; se um dia trouxerem, ela também é comparada com `--seed`);
- `seasons.json` com `history_mode` (`reconstructed` ou `recorded`) para a temporada publicada (ADR-0008, ajuste 1);
- todo ponto de `probability-history` com `generated_at` com fuso, `model_version` e `reconstructed` booleano;
  todos os `model_version` do histórico iguais ao de `predictions` (curva de um único modelo) e o último ponto
  com `reconstructed` falso;
- nenhum dos escudos não livres no artefato (D-028/D-029);
- `reference_date` não regride em relação ao site no ar (`--live-url`, opcional; sem resposta, a checagem é pulada);
- nenhum jogo do `predictions.json` com placar sem status `finished`;
- `current-round.json` (ADR-0009, Decisão 3), exigido quando o snapshot tem jogos: `schema_version` conhecido,
  `updated_at`/`model_version`/`data_version` iguais aos do `predictions.json`; `round` nulo ou com
  `match_ids` e `rescheduled_match_ids` disjuntos e todos no `predictions.json`; `baseline` nulo ou com o
  `model_version` do snapshot, exatamente os clubes do snapshot, data anterior a `starts_on` e os valores de
  `title`/`top4`/`relegation` da visão do `rounds.json` com a mesma `reference_date`.

A saída tem só datas, versões e contagens, nunca placares. Código de saída 1 se alguma checagem falhar.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

NON_FREE_CRESTS = ("bragantino.png", "corinthians.png", "vasco.svg")
HISTORY_MODES = ("reconstructed", "recorded")
TIMEOUT_SECONDS = 30
CURRENT_ROUND_SCHEMA_VERSIONS = ("1.0",)
BASELINE_METRICS = ("title", "top4", "relegation")


def _load(path: Path, problems: list[str]) -> Any:
    if not path.is_file():
        problems.append(f"ausente: {path.as_posix()}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        problems.append(f"JSON inválido: {path.as_posix()} ({error.msg})")
        return None


def _live_reference_date(url: str) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            document = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    value = document.get("reference_date") if isinstance(document, dict) else None
    return str(value) if value else None


def _seed_problems(seed: int, predictions: Any, rounds: Any, history: list[Any]) -> list[str]:
    found = {"predictions": predictions.get("seed"), "rounds": rounds.get("seed")}
    found.update(
        {f"probability-history[{index}]": point["seed"] for index, point in enumerate(history) if "seed" in point}
    )
    return [f"semente de {name} é {value}, esperada {seed}" for name, value in found.items() if value != seed]


def _history_mode_problems(seasons: Any, season: int) -> list[str]:
    entries = [entry for entry in seasons if isinstance(entry, dict) and entry.get("season") == season]
    if not entries:
        return [f"seasons.json sem a temporada {season}"]
    mode = entries[0].get("history_mode")
    if mode not in HISTORY_MODES:
        return [f"seasons.json com history_mode inválido para {season}: {mode!r}"]
    return []


def _has_timezone(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _provenance_problems(history: list[Any], model_version: str) -> list[str]:
    """Origem de cada ponto (ADR-0008, ajuste 1); o site publicado mostra a curva de um único modelo."""
    problems: list[str] = []
    for index, point in enumerate(history):
        if not _has_timezone(point.get("generated_at")):
            problems.append(f"probability-history[{index}] sem generated_at com fuso")
        if not point.get("model_version"):
            problems.append(f"probability-history[{index}] sem model_version")
        if not isinstance(point.get("reconstructed"), bool):
            problems.append(f"probability-history[{index}] sem reconstructed booleano")
    versions = sorted({str(point["model_version"]) for point in history if point.get("model_version")})
    if any(version != model_version for version in versions):
        problems.append(f"probability-history com model_version {versions}, esperado só {model_version}")
    if history and history[-1].get("reconstructed") is not False:
        problems.append("último ponto de probability-history não tem reconstructed == false")
    return problems


def _score_problems(predictions: Any) -> list[str]:
    """Placar só em jogo `finished` (jogo sem resultado nunca sai com placar); a saída tem só os ids."""
    leaked = [
        str(match.get("match_id"))
        for match in predictions.get("matches") or []
        if isinstance(match, dict)
        and match.get("status") != "finished"
        and (match.get("home_goals") is not None or match.get("away_goals") is not None)
    ]
    return [f"predictions.json com placar em jogo não finished: {leaked}"] if leaked else []


def _baseline_values(teams: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(teams, dict):
        return {}
    return {
        str(club): {metric: values.get(metric) for metric in BASELINE_METRICS}
        for club, values in teams.items()
        if isinstance(values, dict)
    }


def _baseline_problems(baseline: Any, starts_on: Any, predictions: Any, rounds: Any) -> list[str]:
    if not isinstance(baseline, dict):
        return ["current-round.baseline não é objeto nem null"]
    problems: list[str] = []
    model_version = predictions["model"]["model_version"]
    if baseline.get("model_version") != model_version:
        problems.append(
            f"current-round.baseline.model_version {baseline.get('model_version')} diferente de {model_version}"
        )
    clubs = {str(team.get("club_id")) for team in predictions.get("teams") or [] if isinstance(team, dict)}
    teams = baseline.get("teams")
    baseline_clubs = set(teams) if isinstance(teams, dict) else set()
    if baseline_clubs != clubs:
        problems.append(
            f"current-round.baseline com clubes diferentes do snapshot: "
            f"faltam {sorted(clubs - baseline_clubs)}, sobram {sorted(baseline_clubs - clubs)}"
        )
    reference_date = str(baseline.get("reference_date"))
    if not reference_date < str(starts_on):
        problems.append(
            f"current-round.baseline.reference_date {reference_date} não é anterior a starts_on {starts_on}"
        )
    views = [
        view
        for view in rounds.get("rounds") or []
        if isinstance(view, dict) and view.get("reference_date") == reference_date
    ]
    if not views:
        problems.append(f"current-round.baseline sem visão de {reference_date} no rounds.json")
    elif all(_baseline_values(view.get("teams")) != _baseline_values(teams) for view in views):
        problems.append(f"current-round.baseline diferente da visão de {reference_date} do rounds.json")
    return problems


def _round_problems(info: Any, predictions: Any, rounds: Any) -> list[str]:
    if not isinstance(info, dict):
        return ["current-round.round não é objeto nem null"]
    problems: list[str] = []
    known = {str(match.get("match_id")) for match in predictions.get("matches") or [] if isinstance(match, dict)}
    listed = info.get("match_ids")
    rescheduled = info.get("rescheduled_match_ids")
    if not isinstance(listed, list) or not isinstance(rescheduled, list):
        return ["current-round.round sem as listas match_ids e rescheduled_match_ids"]
    unknown = sorted({str(match_id) for match_id in [*listed, *rescheduled]} - known)
    if unknown:
        problems.append(f"current-round com jogos ausentes do predictions.json: {unknown}")
    shared = sorted({str(match_id) for match_id in listed} & {str(match_id) for match_id in rescheduled})
    if shared:
        problems.append(f"current-round com jogos em match_ids e rescheduled_match_ids: {shared}")
    if info.get("baseline") is not None:
        problems.extend(_baseline_problems(info["baseline"], info.get("starts_on"), predictions, rounds))
    return problems


def _current_round_problems(current: Any, season: int, predictions: Any, rounds: Any) -> list[str]:
    """Contrato do `current-round.json` (ADR-0009, Decisão 3) contra o snapshot e a revisão publicados."""
    if not isinstance(current, dict):
        return ["current-round.json não é objeto"]
    problems: list[str] = []
    if current.get("schema_version") not in CURRENT_ROUND_SCHEMA_VERSIONS:
        problems.append(f"current-round.schema_version {current.get('schema_version')!r} não suportado")
    expected = {
        "season": season,
        "updated_at": predictions.get("generated_at"),
        "model_version": predictions["model"]["model_version"],
        "data_version": predictions["data"]["version"],
    }
    problems.extend(
        f"current-round.{key} {current.get(key)} diferente de {value} do predictions.json"
        for key, value in expected.items()
        if current.get(key) != value
    )
    if current.get("round") is not None:
        problems.extend(_round_problems(current["round"], predictions, rounds))
    return problems


def check(site_dir: Path, season: int, live_url: str | None, seed: int | None = None) -> list[str]:
    problems: list[str] = []
    api = site_dir / "data" / "api"
    seasons = _load(api / "seasons.json", problems)
    predictions = _load(api / "seasons" / str(season) / "predictions.json", problems)
    history = _load(api / "seasons" / str(season) / "probability-history.json", problems)
    rounds = _load(api / "seasons" / str(season) / "rounds.json", problems)
    metrics = _load(api / "models" / "metrics.json", problems)
    if problems:
        return problems
    reference_date = str(predictions["reference_date"])
    model_versions = {
        "predictions": predictions["model"]["model_version"],
        "rounds": rounds.get("model_version"),
        "metrics": metrics.get("model_version"),
    }
    if len(set(model_versions.values())) != 1:
        problems.append(f"model_version divergente: {model_versions}")
    problems.extend(_history_mode_problems(seasons if isinstance(seasons, list) else [], season))
    if rounds.get("data_version") != predictions["data"]["version"]:
        problems.append("data_version de rounds.json diferente da do snapshot")
    if rounds.get("data_until") != reference_date:
        problems.append(f"rounds.data_until {rounds.get('data_until')} diferente de reference_date {reference_date}")
    if not history:
        problems.append("probability-history vazio")
    elif any(str(point["reference_date"]) > reference_date for point in history):
        problems.append("probability-history tem data posterior ao snapshot")
    elif any(not point.get("n_simulations") for point in history):
        problems.append("probability-history com ponto sem n_simulations")
    problems.extend(_provenance_problems(history or [], str(model_versions["predictions"])))
    problems.extend(_score_problems(predictions))
    current_path = api / "seasons" / str(season) / "current-round.json"
    current: Any = None
    if current_path.is_file() or predictions.get("matches"):
        current_problems: list[str] = []
        current = _load(current_path, current_problems)
        problems.extend(current_problems or _current_round_problems(current, season, predictions, rounds))
    if seed is not None:
        problems.extend(_seed_problems(seed, predictions, rounds, history or []))
    crests = [path.as_posix() for name in NON_FREE_CRESTS for path in site_dir.rglob(name)]
    if crests:
        problems.append(f"escudos não livres no artefato: {crests}")
    if live_url:
        live_date = _live_reference_date(live_url)
        if live_date is None:
            print(f"site no ar sem predictions.json legível em {live_url}; checagem de regressão pulada")
        elif reference_date < live_date:
            problems.append(f"reference_date regrediu: no ar {live_date}, novo {reference_date}")
    current_round = current.get("round") if isinstance(current, dict) else None
    shown = (
        f"{current_round.get('round_number')} ({current_round.get('state')})"
        if isinstance(current_round, dict)
        else "nenhuma"
    )
    print(
        f"snapshot {reference_date} | modelo {model_versions['predictions']} | "
        f"pontos no histórico: {len(history)} | visões por rodada: {len(rounds.get('rounds', []))} | "
        f"rodada atual: {shown}"
    )
    return problems


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--live-url", default=None, help="predictions.json do site no ar")
    parser.add_argument("--seed", type=int, default=None, help="semente usada no simulate e no review-rounds")
    arguments = parser.parse_args(argv)
    problems = check(arguments.site_dir, arguments.season, arguments.live_url, arguments.seed)
    for problem in problems:
        print(f"[artefato] {problem}")
    print(f"checagem do artefato: {'REPROVADA' if problems else 'aprovada'} ({len(problems)} achados)")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
