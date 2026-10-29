"""Resumo do método por competição para a seção "Como calculamos" de todos os sites (D-040).

Lê só arquivos versionados (configurações e relatórios agregados em `data/gold/`) e grava
`apps/web/assets/methods.json`. Um teste reprova se o arquivo versionado estiver desatualizado.
Uso: `python -m brasileirao.methods`.
"""

from __future__ import annotations

import json
from typing import Any

from brasileirao.config import PATHS

OUTPUT = PATHS.root / "apps" / "web" / "assets" / "methods.json"


def _read(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((PATHS.gold / name).read_text(encoding="utf-8"))
    return payload


def _seasons(seasons: list[int]) -> str:
    labels = [str(season) for season in seasons]
    return labels[0] if len(labels) == 1 else f"{labels[0]}–{labels[-1]}"


def _european_seasons(seasons: list[int]) -> str:
    first, last = min(seasons), max(seasons)
    return (
        f"{first}/{str(first + 1)[2:]}" if first == last else f"{first}/{str(first + 1)[2:]}–{last}/{str(last + 1)[2:]}"
    )


def _number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _elo(params: dict[str, Any], newcomer: str) -> dict[str, Any]:
    return {
        "k_factor": params["k_factor"],
        "home_advantage": params["home_advantage"],
        "season_regression": params["season_regression"],
        "newcomer": newcomer,
    }


def _validation(model: dict[str, Any], base: dict[str, Any], seasons: str) -> dict[str, Any]:
    return {
        "seasons": seasons,
        "n_matches": model["n_matches"],
        "log_loss": model["log_loss"],
        "base_rate": base["log_loss"],
    }


def _uncertainty(config: dict[str, Any]) -> str:
    strength = float(config.get("simulation_uncertainty", {}).get("strength_sd", 0.0))
    if strength > 0:
        return (
            f"Cada simulação sorteia uma variação de força de cada clube (desvio {_number(strength)} "
            "na escala dos gols)"
        )
    return "Sem variação extra de força entre simulações"


def build_methods() -> dict[str, Any]:
    serie_a = _read("model_config.json")
    serie_a_rates = serie_a["rating_params"]["attack_defense"]
    serie_a_report = _read("backtest_report.json")
    serie_b = _read("serie_b_model_config.json")
    serie_b_report = _read("serie_b_backtest_report.json")
    champions = _read("champions_model_config.json")
    champions_report = _read("champions_tuning_report.json")
    competitions: list[dict[str, Any]] = [
        {
            "id": "serie-a",
            "name": "Brasileirão Série A",
            "path": "",
            "data": "Adão Duque (Kaggle v18, 2003–2025) e football-data.org (temporada atual).",
            "elo": _elo(serie_a["rating_params"]["elo"], "clube que sobe entra com a média de quem saiu da divisão"),
            "extras": [
                f"Ataque e defesa de cada clube (taxa {_number(serie_a_rates['learning_rate'])})",
                f"Forma recente ({serie_a['rating_params']['form']['span_matches']} jogos)",
                _uncertainty(serie_a),
            ],
            "rules": "Regulamento da CBF: pontos, vitórias, saldo, gols, confronto direto; vagas na Libertadores e "
            "na Sul-Americana em faixa quando dependem de outras copas.",
            "validation": _validation(
                serie_a_report["test_metrics"][serie_a_report["chosen_feature_set"]],
                serie_a_report["test_metrics"]["base_rate"],
                _seasons(serie_a_report["test_seasons"]),
            ),
        },
        {
            "id": "serie-b",
            "name": "Série B",
            "path": "serie-b/",
            "data": "openfootball (2018–2024), Wikipédia em português (2025 e temporada atual).",
            "elo": _elo(serie_b["rating_params"]["elo"], "clube que chega entra com a média de quem saiu da divisão"),
            "extras": [
                f"Ataque e defesa (taxa {_number(serie_b['rating_params']['attack_defense']['learning_rate'])})",
                "A ordem dos jogos de 2026 é aproximada: a fonte não traz datas",
                _uncertainty(serie_b),
            ],
            "rules": "Regulamento da CBF: 2 sobem direto, 3º a 6º jogam playoff de ida e volta, 4 caem.",
            "validation": _validation(
                serie_b_report["match_level"][serie_b_report["feature_set"]],
                serie_b_report["match_level"]["base_rate"],
                _seasons(serie_b_report["test_seasons"]),
            ),
        },
    ]
    for code, name, rules in (
        ("premier-league", "Premier League", "Handbook da Premier League: pontos, saldo, gols, confronto direto."),
        ("la-liga", "LaLiga", "RFEF, Art. 10: pontos e depois confronto direto (mini-tabela), saldo, gols."),
    ):
        config = _read(f"league_model_config_{code}.json")
        report = _read(f"league_tuning_report_{code}.json")
        chosen = report["match_level"][report["chosen_rating_params"]]["test"]
        competitions.append(
            {
                "id": code,
                "name": name,
                "path": f"{code}/",
                "data": "openfootball (histórico) e football-data.org (temporada atual).",
                "elo": _elo(config["rating_params"]["elo"], "clube que sobe entra com a média de quem saiu da liga"),
                "extras": [
                    f"Ataque e defesa (taxa {_number(config['rating_params']['attack_defense']['learning_rate'])})",
                    _uncertainty(config),
                ],
                "rules": rules,
                "validation": _validation(chosen, report["base_rate_test"], _european_seasons(report["test_seasons"])),
            }
        )
    elo = champions["elo"]
    competitions.append(
        {
            "id": "champions-league",
            "name": "Champions League",
            "path": "champions-league/",
            "data": "openfootball (7 ligas e as 3 copas europeias, 2021/22–2025/26) e football-data.org "
            "(temporada atual).",
            "elo": _elo(
                elo,
                f"clube novo de liga entra {_number(elo['newcomer_offset'])} pontos abaixo da média do país; "
                f"de país sem outro clube conhecido, {_number(elo['unknown_offset'])} abaixo de "
                f"{_number(elo['initial_rating'])}",
            ),
            "extras": [
                "Elo único para todos os clubes: as ligas ordenam cada país e as copas europeias ligam os países",
                "Modelo de gols treinado só com jogos europeus; final em campo neutro",
            ],
            "rules": "UEFA, Art. 18 (fase de liga, sem confronto direto) e Art. 19 (mata-mata com chaveamento fixo).",
            "validation": _validation(
                champions_report["match_level"]["elo_only"]["test"],
                champions_report["match_level"]["base_rate"]["test"],
                _european_seasons(champions_report["test_seasons"]),
            ),
        }
    )
    return {"schema_version": "1.0", "competitions": competitions}


def render_json() -> str:
    return json.dumps(build_methods(), ensure_ascii=False, indent=1) + "\n"


def main() -> None:
    OUTPUT.write_text(render_json(), encoding="utf-8")
    print(f"gravado em {OUTPUT}")


if __name__ == "__main__":
    main()
