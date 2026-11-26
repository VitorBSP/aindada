"""Probabilidades pré-jogo por partida, point-in-time, para o contrato da futura Base Global de Partidas.

Cada linha é uma partida com a previsão que o modelo faria ANTES da rodada dela, usando só partidas
encerradas em datas anteriores ao primeiro jogo da rodada (zero leakage temporal, AGENTS.md). O motor é o
mesmo dos snapshots: ratings Elo e ataque/defesa (`RatingEngine`) e `GoalsModel` (Poisson/Dixon-Coles com
dispersão), com a configuração de `data/gold/model_config.json`. Nada aqui sorteia: o resultado é determinístico.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from brasileirao.config import MODEL_VERSION, PATHS, ModelTrainingConfig
from brasileirao.contracts import MatchStatus
from brasileirao.data_pipeline.clubs import ClubRegistry
from brasileirao.data_pipeline.ingest import confirmed_kickoff_utc, sha256_of
from brasileirao.frame_values import as_int
from brasileirao.pipeline import ModelConfig
from brasileirao.prediction.goals_model import GoalsModel, outcome_probabilities, total_goals_at_least
from brasileirao.provenance import ProvenanceError, read_composition
from brasileirao.publication_gate import check_g1_gold_sources
from brasileirao.ratings.history import build_state_as_of
from brasileirao.validation.backtest import training_window

SCHEMA_VERSION = "1.0"
COMPETITION_IDS = {"serie_a": "brasileirao_serie_a"}
EXPORT_STATUSES = (MatchStatus.FINISHED.value, MatchStatus.SCHEDULED.value, MatchStatus.POSTPONED.value)

COLUMNS = [
    "competition_id",
    "season",
    "round",
    "match_id",
    "kickoff_utc",
    "status",
    "home_club_id",
    "home_club_name",
    "home_club_short",
    "away_club_id",
    "away_club_name",
    "away_club_short",
    "home_score",
    "away_score",
    "home_win_probability",
    "draw_probability",
    "away_win_probability",
    "home_expected_goals",
    "away_expected_goals",
    "home_clean_sheet_probability",
    "away_clean_sheet_probability",
    "over_1_5_probability",
    "over_2_5_probability",
    "under_2_5_probability",
    "model_version",
    "as_of_round",
]
MODEL_COLUMNS = COLUMNS[COLUMNS.index("home_win_probability") : COLUMNS.index("model_version")]
PROBABILITY_COLUMNS = [column for column in MODEL_COLUMNS if column.endswith("_probability")]
SUM_TOLERANCE = 1e-9


class ExportError(RuntimeError):
    """Entrada ou saída que violaria uma regra de integridade do export."""


def point_in_time_view(matches_data: pd.DataFrame, cutoff: date) -> pd.DataFrame:
    """Calendário completo, mas com placar e status de partida depois de `cutoff` apagados.

    O calendário (quem joga com quem) é público antes da temporada; o resultado de um jogo depois do corte
    nunca chega ao motor, mesmo que o chamador passe a base inteira.
    """
    view = matches_data.copy()
    hidden = view["match_date"].dt.date > cutoff
    view.loc[hidden, ["home_goals", "away_goals"]] = pd.NA
    view.loc[hidden & (view["status"] == MatchStatus.FINISHED.value), "status"] = MatchStatus.SCHEDULED.value
    return view


def round_cutoffs(season_matches: pd.DataFrame) -> dict[int, date]:
    """Para cada rodada, o último dia anterior ao primeiro jogo dela (data da base, em Brasília)."""
    first_days = season_matches.groupby("round")["match_date"].min()
    return {
        int(str(round_number)): first_day.date() - timedelta(days=1) for round_number, first_day in first_days.items()
    }


@dataclass(frozen=True)
class PriorInputs:
    matches_data: pd.DataFrame
    registry: ClubRegistry
    model_config: ModelConfig
    training: ModelTrainingConfig


def _fit_season_model(inputs: PriorInputs, season: int, first_cutoff: date) -> tuple[GoalsModel, int]:
    """Modelo de gols da temporada: treina só com temporadas anteriores, com ratings até o corte da rodada 1."""
    view = point_in_time_view(inputs.matches_data, first_cutoff)
    _, features = build_state_as_of(view, first_cutoff, season, inputs.model_config.rating_params)
    if features.empty:
        raise ExportError(f"temporada {season}: sem histórico anterior para treinar o modelo")
    training_features = training_window(
        features, season, inputs.training.training_seasons_window, inputs.training.first_training_season
    )
    if training_features.empty:
        raise ExportError(f"temporada {season}: sem histórico anterior para treinar o modelo")
    model = GoalsModel.fit(
        training_features,
        inputs.model_config.feature_set,
        alpha=inputs.training.poisson_alpha,
        max_goals=inputs.training.max_goals,
        draw_inflation=inputs.model_config.draw_inflation,
        goal_dispersion=inputs.model_config.goal_dispersion,
    )
    return model, int(features["season"].min())


def _as_of_round(view: pd.DataFrame, season: int, cutoff: date) -> int:
    used = view[
        (view["season"] == season)
        & (view["status"] == MatchStatus.FINISHED.value)
        & (view["match_date"].dt.date <= cutoff)
    ]
    return int(used["round"].max()) if len(used) else 0


def _round_rows(
    inputs: PriorInputs,
    model: GoalsModel,
    season: int,
    round_number: int,
    cutoff: date,
    round_matches: pd.DataFrame,
    competition_id: str,
) -> list[dict[str, Any]]:
    view = point_in_time_view(inputs.matches_data, cutoff)
    engine, _ = build_state_as_of(view, cutoff, season, inputs.model_config.rating_params)
    as_of_round = _as_of_round(view, season, cutoff)
    features = pd.DataFrame(
        [engine.pre_match_features(str(match.home_id), str(match.away_id)) for match in round_matches.itertuples()]
    )
    matrices = model.score_probabilities(features)
    home_rate, away_rate = model.expected_goals(features)
    markets = market_probabilities(matrices)
    rows: list[dict[str, Any]] = []
    for position, match in enumerate(round_matches.itertuples()):
        home, away = inputs.registry.clubs[str(match.home_id)], inputs.registry.clubs[str(match.away_id)]
        finished = str(match.status) == MatchStatus.FINISHED.value
        rows.append(
            {
                "competition_id": competition_id,
                "season": season,
                "round": round_number,
                "match_id": f"{season}-{home.club_id}-{away.club_id}",
                "kickoff_utc": _kickoff_text(match),
                "status": str(match.status),
                "home_club_id": home.club_id,
                "home_club_name": home.display_name,
                "home_club_short": home.short_name,
                "away_club_id": away.club_id,
                "away_club_name": away.display_name,
                "away_club_short": away.short_name,
                "home_score": as_int(match.home_goals) if finished else None,
                "away_score": as_int(match.away_goals) if finished else None,
                "home_win_probability": float(markets["home_win"][position]),
                "draw_probability": float(markets["draw"][position]),
                "away_win_probability": float(markets["away_win"][position]),
                "home_expected_goals": float(home_rate[position]),
                "away_expected_goals": float(away_rate[position]),
                "home_clean_sheet_probability": float(markets["home_clean_sheet"][position]),
                "away_clean_sheet_probability": float(markets["away_clean_sheet"][position]),
                "over_1_5_probability": float(markets["over_1_5"][position]),
                "over_2_5_probability": float(markets["over_2_5"][position]),
                "under_2_5_probability": float(markets["under_2_5"][position]),
                "model_version": MODEL_VERSION,
                "as_of_round": as_of_round,
            }
        )
    return rows


def market_probabilities(matrices: npt.NDArray[np.float64]) -> dict[str, npt.NDArray[np.float64]]:
    """Mercados derivados da matriz de placares (n, gols+1, gols+1), índice [mandante, visitante]."""
    outcome = outcome_probabilities(matrices)
    over_2_5 = total_goals_at_least(matrices, 3)
    return {
        "home_win": outcome[:, 0],
        "draw": outcome[:, 1],
        "away_win": outcome[:, 2],
        "home_clean_sheet": matrices[:, :, 0].sum(axis=1),
        "away_clean_sheet": matrices[:, 0, :].sum(axis=1),
        "over_1_5": total_goals_at_least(matrices, 2),
        "over_2_5": over_2_5,
        "under_2_5": 1.0 - over_2_5,
    }


def _kickoff_text(match: Any) -> str | None:
    kickoff = confirmed_kickoff_utc(getattr(match, "kickoff_utc", None), getattr(match, "kickoff_time_confirmed", None))
    if kickoff is None:
        return None
    return datetime.fromisoformat(kickoff).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_match_priors(inputs: PriorInputs, seasons: list[int], competition: str = "serie_a") -> pd.DataFrame:
    """Uma linha por partida de `seasons`, com a previsão feita antes da rodada dela."""
    if competition not in COMPETITION_IDS:
        raise ExportError(f"competição desconhecida {competition!r}; disponíveis: {sorted(COMPETITION_IDS)}")
    competition_id = COMPETITION_IDS[competition]
    matches_data = inputs.matches_data
    all_rows: list[dict[str, Any]] = []
    for season in sorted(seasons):
        season_matches = matches_data[
            (matches_data["season"] == season) & matches_data["status"].isin(EXPORT_STATUSES)
        ].sort_values(["round", "match_date", "match_id"])
        if season_matches.empty:
            raise ExportError(f"temporada {season} sem partidas na base gold")
        if season_matches["round"].isna().any():
            raise ExportError(f"temporada {season} tem partidas sem rodada")
        cutoffs = round_cutoffs(season_matches)
        model, _ = _fit_season_model(inputs, season, cutoffs[min(cutoffs)])
        for round_number, round_matches in season_matches.groupby("round", sort=True):
            number = int(str(round_number))
            all_rows.extend(_round_rows(inputs, model, season, number, cutoffs[number], round_matches, competition_id))
    frame = pd.DataFrame(all_rows, columns=COLUMNS)
    frame["season"] = frame["season"].astype("int64")
    frame["round"] = frame["round"].astype("int64")
    frame["as_of_round"] = frame["as_of_round"].astype("int64")
    frame["home_score"] = frame["home_score"].astype("Int64")
    frame["away_score"] = frame["away_score"].astype("Int64")
    return frame.sort_values(["season", "round", "kickoff_utc", "match_id"], na_position="last").reset_index(drop=True)


def validate_match_priors(frame: pd.DataFrame, expected_per_season: int | None = None) -> dict[str, Any]:
    """Falha (`ExportError`) se o contrato for violado; devolve o resumo de validação."""
    problems: list[str] = []
    if list(frame.columns) != COLUMNS:
        problems.append("colunas diferentes do schema canônico")
    if frame["match_id"].duplicated().any():
        problems.append(f"{int(frame['match_id'].duplicated().sum())} match_id repetidos")
    numeric = frame[MODEL_COLUMNS]
    nan_count = int(numeric.isna().sum().sum())
    if nan_count:
        problems.append(f"{nan_count} NaN em probabilidades ou gols esperados")
    if ((frame[PROBABILITY_COLUMNS] < 0) | (frame[PROBABILITY_COLUMNS] > 1)).any().any():
        problems.append("probabilidade fora de [0, 1]")
    outcome_sum = frame[["home_win_probability", "draw_probability", "away_win_probability"]].sum(axis=1)
    if (np.abs(outcome_sum - 1.0) > SUM_TOLERANCE).any():
        problems.append("vitória/empate/derrota não somam 1")
    totals = frame["over_2_5_probability"] + frame["under_2_5_probability"]
    if (np.abs(totals - 1.0) > SUM_TOLERANCE).any():
        problems.append("over 2,5 e under 2,5 não somam 1")
    if (frame["over_2_5_probability"] > frame["over_1_5_probability"] + SUM_TOLERANCE).any():
        problems.append("over 2,5 maior que over 1,5")
    if (frame[["home_expected_goals", "away_expected_goals"]] <= 0).any().any():
        problems.append("gols esperados não positivos")
    finished = frame["status"] == MatchStatus.FINISHED.value
    if frame.loc[~finished, ["home_score", "away_score"]].notna().any().any():
        problems.append("partida não encerrada com placar")
    if frame.loc[finished, ["home_score", "away_score"]].isna().any().any():
        problems.append("partida encerrada sem placar")
    if not set(frame["status"]) <= set(EXPORT_STATUSES):
        problems.append("status fora de finished/scheduled/postponed")
    counts = {int(str(season)): int(count) for season, count in frame.groupby("season").size().items()}
    if expected_per_season is not None:
        wrong = {season: count for season, count in counts.items() if count != expected_per_season}
        if wrong:
            problems.append(f"contagem por temporada diferente de {expected_per_season}: {wrong}")
    if problems:
        raise ExportError("; ".join(problems))
    return {
        "n_rows": len(frame),
        "rows_by_season": counts,
        "rows_by_status": {str(status): int(count) for status, count in frame.groupby("status").size().items()},
        "nan_in_model_columns": nan_count,
        "max_abs_outcome_sum_error": float(np.abs(outcome_sum - 1.0).max()),
        "duplicated_match_id": 0,
    }


def _git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(PATHS.root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def _source_entries(composition: dict[str, Any], seasons: list[int]) -> list[dict[str, Any]]:
    wanted = set(seasons)
    entries = []
    for entry in composition.get("sources") or []:
        covered = sorted(wanted & {int(season) for season in entry.get("seasons", [])})
        if covered:
            entries.append({**entry, "seasons": covered})
    return entries


def check_sources(matches_data: pd.DataFrame, composition: dict[str, Any], seasons: list[int]) -> None:
    findings = check_g1_gold_sources(matches_data, composition)
    if findings:
        raise ProvenanceError("; ".join(finding.detail for finding in findings))
    covered = {int(season) for season in (composition.get("seasons") or {})}
    missing = sorted(set(seasons) - covered)
    if missing:
        raise ProvenanceError(f"temporadas sem fonte na composição: {missing}")


def build_manifest(
    frame: pd.DataFrame,
    summary: dict[str, Any],
    inputs: PriorInputs,
    composition: dict[str, Any],
    seasons: list[int],
    competition: str,
    outputs: dict[str, Path],
    gold_path: Path,
    model_config_path: Path,
    clubs_path: Path,
    generated_at: datetime,
) -> dict[str, Any]:
    sources = _source_entries(composition, seasons)
    return {
        "schema_version": SCHEMA_VERSION,
        "export": "match_priors",
        "competition": competition,
        "competition_id": COMPETITION_IDS[competition],
        "seasons": sorted(seasons),
        "generated_at": generated_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "columns": COLUMNS,
        "validation": summary,
        "model": {
            "model_version": MODEL_VERSION,
            "feature_set": inputs.model_config.feature_set,
            "goal_dispersion": inputs.model_config.goal_dispersion,
            "draw_inflation": inputs.model_config.draw_inflation,
            "rating_params": asdict(inputs.model_config.rating_params),
            "training": asdict(inputs.training),
            "seed": None,
            "seed_note": "determinístico: ratings e regressões não sorteiam nada; não há semente",
            "history_first_season": int(inputs.matches_data["season"].min()),
        },
        "point_in_time": {
            "rule": (
                "previsão da rodada R usa só partidas encerradas com data (Brasília) anterior ao primeiro jogo "
                "da rodada R; o modelo de gols treina só com temporadas anteriores à da partida"
            ),
            "as_of_round": "maior rodada da temporada entre as partidas usadas (0 = nenhuma da temporada)",
            "kickoff_utc": "só com horário confirmado na fonte; senão nulo",
        },
        "sources": sources,
        "license": {
            "most_restrictive_status": _most_restrictive(sources),
            "allowed_uses": _common_uses(sources),
            "redistribution": False,
            "note": (
                "Uso local/protótipo do dono do produto. Dados de partida de terceiros (football-data.org, Adão Duque "
                "v18) não podem ser redistribuídos em lote sem decisão registrada (ADR-0008). Preservar a atribuição "
                "de cada fonte ao exibir."
            ),
            "attribution": [entry["attribution"] for entry in sources if entry.get("attribution")],
        },
        "inputs": {
            "gold_matches_csv": {"path": _display_path(gold_path), "sha256": sha256_of(gold_path)},
            "clubs_reference": {
                "path": _display_path(PATHS.clubs_reference),
                "sha256": sha256_of(PATHS.clubs_reference),
            },
            "model_config": {"path": _display_path(model_config_path), "sha256": sha256_of(model_config_path)},
        },
        "code": {"git_commit": _git_commit()},
        "outputs": {kind: {"file": path.name, "sha256": sha256_of(path)} for kind, path in outputs.items()},
    }


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PATHS.root))
    except ValueError:
        return str(path)


def _most_restrictive(sources: list[dict[str, Any]]) -> str | None:
    from brasileirao.contracts import LicenseStatus, most_restrictive_license  # noqa: PLC0415

    if not sources:
        return None
    return most_restrictive_license(LicenseStatus(str(entry["license_status"])) for entry in sources).value


def _common_uses(sources: list[dict[str, Any]]) -> list[str]:
    if not sources:
        return []
    common = set(sources[0].get("allowed_uses", []))
    for entry in sources[1:]:
        common &= set(entry.get("allowed_uses", []))
    return sorted(common - {"redistribution"})


def write_match_priors(
    frame: pd.DataFrame,
    output: Path,
    write_csv: bool = False,
) -> dict[str, Path]:
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False, engine="pyarrow")
    outputs = {"parquet": output}
    if write_csv:
        csv_path = output.with_suffix(".csv")
        frame.to_csv(csv_path, index=False)
        outputs["csv"] = csv_path
    return outputs


def manifest_path_for(output: Path) -> Path:
    return output.with_name(f"{output.stem}.manifest.json")


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_match_priors(
    competition: str,
    seasons: list[int],
    output: Path,
    matches_data: pd.DataFrame,
    registry: ClubRegistry,
    model_config: ModelConfig,
    gold_path: Path,
    model_config_path: Path,
    silver_dir: Path,
    clubs_path: Path = PATHS.clubs_reference,
    training: ModelTrainingConfig | None = None,
    write_csv: bool = False,
    expected_per_season: int | None = 380,
) -> tuple[dict[str, Path], dict[str, Any]]:
    composition = read_composition(silver_dir)
    check_sources(matches_data, composition, seasons)
    inputs = PriorInputs(matches_data, registry, model_config, training or ModelTrainingConfig())
    frame = build_match_priors(inputs, seasons, competition)
    summary = validate_match_priors(frame, expected_per_season)
    outputs = write_match_priors(frame, output, write_csv)
    manifest = build_manifest(
        frame,
        summary,
        inputs,
        composition,
        seasons,
        competition,
        outputs,
        gold_path,
        model_config_path,
        clubs_path,
        datetime.now(tz=UTC),
    )
    destination = manifest_path_for(output)
    destination.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {**outputs, "manifest": destination}, manifest
