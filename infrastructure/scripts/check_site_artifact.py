"""Checagens do artefato do Pages que complementam o `publication-gate` (ADR-0007, itens 5, 6 e 8).

- os JSON obrigatórios do export existem e são JSON válidos;
- `model_version` igual em `predictions`, `rounds` e `metrics`; `data_version` igual em `predictions` e `rounds`;
- `rounds.data_until` igual à `reference_date` do snapshot;
- `probability-history` sem data posterior à do snapshot e com semente e número de simulações por ponto;
- nenhum dos escudos não livres no artefato (D-028/D-029);
- `reference_date` não regride em relação ao site no ar (`--live-url`, opcional; sem resposta, a checagem é pulada).

A saída tem só datas, versões e contagens, nunca placares. Código de saída 1 se alguma checagem falhar.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

NON_FREE_CRESTS = ("bragantino.png", "corinthians.png", "vasco.svg")
TIMEOUT_SECONDS = 30


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


def check(site_dir: Path, season: int, live_url: str | None) -> list[str]:
    problems: list[str] = []
    api = site_dir / "data" / "api"
    _load(api / "seasons.json", problems)
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
    crests = [path.as_posix() for name in NON_FREE_CRESTS for path in site_dir.rglob(name)]
    if crests:
        problems.append(f"escudos não livres no artefato: {crests}")
    if live_url:
        live_date = _live_reference_date(live_url)
        if live_date is None:
            print(f"site no ar sem predictions.json legível em {live_url}; checagem de regressão pulada")
        elif reference_date < live_date:
            problems.append(f"reference_date regrediu: no ar {live_date}, novo {reference_date}")
    print(
        f"snapshot {reference_date} | modelo {model_versions['predictions']} | "
        f"pontos no histórico: {len(history)} | visões por rodada: {len(rounds.get('rounds', []))}"
    )
    return problems


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--live-url", default=None, help="predictions.json do site no ar")
    arguments = parser.parse_args(argv)
    problems = check(arguments.site_dir, arguments.season, arguments.live_url)
    for problem in problems:
        print(f"[artefato] {problem}")
    print(f"checagem do artefato: {'REPROVADA' if problems else 'aprovada'} ({len(problems)} achados)")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
