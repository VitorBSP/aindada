"""Escudos e logos dos sites das outras competições (D-043), com a regra da Série A (D-028).

Para cada time de `data/reference/crest_sources.csv`: artigo da Wikipédia em inglês → item do Wikidata → logo
(P154, posto preferido ou o último) → licença no Wikimedia Commons. Só entra arquivo em domínio público ou CC0,
baixado como PNG de 128 px. Sem logo livre (ou sem artigo), o time recebe o marcador neutro com a sigla.
Proveniência por arquivo em `data/reference/crests_provenance_<competição>.json`.

Uso: `python -m brasileirao.crests` (rede) e `python -m brasileirao.crests --offline` (só refaz os manifestos).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from brasileirao.config import PATHS
from brasileirao.serie_b.sources import sha256_bytes

USER_AGENT = "AIndaDa/0.1 (https://github.com/VitorBSP/aindada)"
FREE_LICENSES = frozenset({"Public domain", "CC0"})
THUMB_WIDTH = 128
APPS = {
    "serie-b": "web-serie-b",
    "premier-league": "web-ligas",
    "la-liga": "web-ligas",
    "champions-league": "web-champions",
    "mundial-lol": "web-lol",
}
FORECASTS = {
    "serie-b": "https://vitorbsp.github.io/aindada/serie-b/data/forecast.json",
    "premier-league": "https://vitorbsp.github.io/aindada/premier-league/data/forecast.json",
    "la-liga": "https://vitorbsp.github.io/aindada/la-liga/data/forecast.json",
    "champions-league": "https://vitorbsp.github.io/aindada/champions-league/data/forecast.json",
    "mundial-lol": "https://vitorbsp.github.io/aindada/mundial-lol/data/forecast.json",
}
BADGE = {"bg": "#E2E1DB", "fg": "#17191C"}
# O Wikidata registra cores genéricas ("vermelho" = #FF0000); no marcador vira um tom institucional, sem neon.
SHADES = {
    "#FF0000": "#C8102E",
    "#0000FF": "#1F3F8F",
    "#00FF00": "#1E7B3A",
    "#008000": "#1E7B3A",
    "#FFFF00": "#F2C300",
    "#77B5FE": "#6CABDD",
    "#FFBF00": "#F2A900",
}
SOURCES = PATHS.reference / "crest_sources.csv"


def _get(url: str, params: dict[str, str] | None = None) -> Any:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    request = urllib.request.Request(url + query, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        content: bytes = response.read()
    return content


def entity_claims(title: str) -> dict[str, Any]:
    payload = _get(
        "https://www.wikidata.org/w/api.php",
        {"action": "wbgetentities", "sites": "enwiki", "titles": title, "props": "claims", "format": "json"},
    )
    claims: dict[str, Any] = next(iter(payload["entities"].values())).get("claims", {})
    return claims


def _values(claims: dict[str, Any], prop: str) -> list[Any]:
    found = [claim for claim in claims.get(prop, []) if "datavalue" in claim["mainsnak"]]
    preferred = [claim for claim in found if claim.get("rank") == "preferred"]
    return [claim["mainsnak"]["datavalue"]["value"] for claim in (preferred or found)]


def logo_file(claims: dict[str, Any]) -> str | None:
    """Arquivo do logo (P154); posto preferido primeiro, senão o último."""
    values = _values(claims, "P154")
    return str(values[-1]) if values else None


def club_colors(claims: dict[str, Any]) -> list[str]:
    """Cores oficiais (P6364), em `#RRGGBB` pelo código sRGB (P465) de cada item de cor."""
    ids = [value["id"] for value in _values(claims, "P6364")]
    if not ids:
        return []
    payload = _get(
        "https://www.wikidata.org/w/api.php",
        {"action": "wbgetentities", "ids": "|".join(ids), "props": "claims", "format": "json"},
    )
    colors = []
    for color_id in ids:
        hexes = _values(payload["entities"].get(color_id, {}).get("claims", {}), "P465")
        if hexes and re.fullmatch(r"[0-9A-Fa-f]{6}", str(hexes[0])):
            colors.append(f"#{str(hexes[0]).upper()}")
    return colors


def _luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def badge_colors(colors: list[str]) -> dict[str, str]:
    """Fundo = primeira cor oficial; texto branco ou tinta, o de maior contraste (WCAG). Sem cor: neutro."""
    if not colors:
        return dict(BADGE)
    background = SHADES.get(colors[0], colors[0])
    text = max(("#FFFFFF", "#17191C"), key=lambda candidate: contrast(background, candidate))
    return {"bg": background, "fg": text}


def commons_info(file_name: str) -> dict[str, str]:
    payload = _get(
        "https://commons.wikimedia.org/w/api.php",
        {
            "action": "query",
            "titles": f"File:{file_name}",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": str(THUMB_WIDTH),
            "format": "json",
        },
    )
    page = next(iter(payload["query"]["pages"].values()))
    info = page["imageinfo"][0]
    meta = info.get("extmetadata", {})
    return {
        "thumb_url": info["thumburl"],
        "source_url": info["url"],
        "file_page_url": info["descriptionurl"],
        "license": meta.get("LicenseShortName", {}).get("value", ""),
        "author": meta.get("Artist", {}).get("value", ""),
    }


def load_sources(path: Path = SOURCES) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def short_names() -> dict[tuple[str, str], str]:
    """Sigla de cada time pelo `forecast.json` publicado (a mesma que o site mostra)."""
    names: dict[tuple[str, str], str] = {}
    for competition, url in FORECASTS.items():
        payload = _get(url)
        for team in payload.get("teams") or payload.get("clubs") or []:
            names[(competition, team.get("club_id") or team["team_id"])] = team["short_name"]
    return names


def collect(
    rows: list[dict[str, str]], names: dict[tuple[str, str], str], pause: float = 0.3
) -> dict[str, dict[str, dict[str, str]]]:
    """Baixa os logos livres para `apps/<app>/assets/crests/`; devolve a proveniência por competição."""
    provenance: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        competition, team_id, title = row["competition"], row["team_id"], row["wikipedia_title"]
        record: dict[str, str] = {
            "wikipedia_title": title,
            "short_name": names.get((competition, team_id), team_id[:3].upper()),
            "license_status": "sem logo livre",
        }
        if row.get("skip_logo"):
            record["note"] = row["skip_logo"]
        claims = entity_claims(title) if title else {}
        record.update(badge_colors(club_colors(claims)))
        file_name = logo_file(claims) if not row.get("skip_logo") else None
        if file_name:
            info = commons_info(file_name)
            record.update(
                {
                    "commons_file": file_name,
                    **{key: info[key] for key in ("source_url", "thumb_url", "file_page_url", "license")},
                }
            )
            record["author"] = info["author"][:200]
            if info["license"] in FREE_LICENSES:
                content = _download(info["thumb_url"])
                target = PATHS.root / "apps" / APPS[competition] / "assets" / "crests" / f"{team_id}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                record.update(
                    {
                        "file": target.name,
                        "license_status": "livre",
                        "sha256": sha256_bytes(content),
                        "retrieved_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                    }
                )
        provenance[competition][team_id] = record
        time.sleep(pause)
    return provenance


def write_manifests(provenance: dict[str, dict[str, dict[str, str]]]) -> None:
    manifests: dict[str, dict[str, Any]] = defaultdict(dict)
    for competition, teams in provenance.items():
        for team_id, record in sorted(teams.items()):
            if record.get("file"):
                manifests[APPS[competition]][team_id] = {"file": record["file"]}
            else:
                badge = {"label": record["short_name"], "bg": record["bg"], "fg": record["fg"]}
                manifests[APPS[competition]][team_id] = {"badge": badge}
    for app, manifest in manifests.items():
        path = PATHS.root / "apps" / app / "assets" / "crests" / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def provenance_path(competition: str) -> Path:
    return PATHS.reference / f"crests_provenance_{competition.replace('-', '_')}.json"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="brasileirao-crests", description="Escudos livres das outras competições")
    parser.add_argument("--offline", action="store_true", help="refaz só os manifestos a partir da proveniência")
    arguments = parser.parse_args(argv)
    competitions = sorted({row["competition"] for row in load_sources()})
    if arguments.offline:
        provenance = {
            competition: json.loads(provenance_path(competition).read_text(encoding="utf-8"))
            for competition in competitions
        }
    else:
        provenance = collect(load_sources(), short_names())
        for competition, teams in provenance.items():
            provenance_path(competition).write_text(
                json.dumps(teams, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    write_manifests(provenance)
    for competition in competitions:
        teams = provenance[competition]
        free = sum(1 for record in teams.values() if record.get("file"))
        print(f"{competition}: {free} logos livres, {len(teams) - free} marcadores")


if __name__ == "__main__":
    main()
