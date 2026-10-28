"""Baixa a versão 18 do dataset de Adão Duque no Kaggle e confere o SHA-256 (ADR-0008, Decisão 3, adendo).

Usado pelo workflow `publish-site.yml`. Os arquivos (GPL-2) só existem no runner efêmero: não são
versionados nem publicados. Só os arquivos fixados em `data/reference/source_pins.json` são extraídos;
qualquer hash diferente faz o script falhar sem deixar arquivo no destino.

Uso: python -I infrastructure/scripts/fetch_adaoduque_v18.py --pins data/reference/source_pins.json \
         --target data/raw/adaoduque/v18
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

SOURCE_NAME = "adaoduque_kaggle"
DOWNLOAD_URL = (
    "https://www.kaggle.com/api/v1/datasets/download/adaoduque/campeonato-brasileiro-de-futebol?datasetVersionNumber=18"
)
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
TIMEOUT_SECONDS = 120


def load_pinned_files(pins_path: Path) -> dict[str, str]:
    entry = json.loads(pins_path.read_text(encoding="utf-8")).get(SOURCE_NAME) or {}
    if entry.get("version") != "kaggle-v18":
        raise SystemExit(f"{pins_path}: versão fixada de {SOURCE_NAME} não é kaggle-v18")
    files = {str(name): str(digest) for name, digest in (entry.get("files") or {}).items()}
    if not files:
        raise SystemExit(f"{pins_path}: nenhum hash fixado para {SOURCE_NAME}")
    return files


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "brasileirao-predictions-ci"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        payload: bytes = response.read(MAX_ARCHIVE_BYTES + 1)
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise SystemExit("arquivo do Kaggle maior que o limite esperado; abortado")
    return payload


def extract_pinned(payload: bytes, pinned: dict[str, str]) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        missing = sorted(set(pinned) - names)
        if missing:
            raise SystemExit(f"arquivos fixados ausentes no zip do Kaggle: {missing}")
        contents = {name: archive.read(name) for name in pinned}
    for name, digest in pinned.items():
        actual = hashlib.sha256(contents[name]).hexdigest()
        if actual != digest:
            raise SystemExit(f"SHA-256 divergente em {name}: esperado {digest}, obtido {actual}")
    return contents


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pins", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--url", default=DOWNLOAD_URL)
    arguments = parser.parse_args(argv)
    pinned = load_pinned_files(arguments.pins)
    contents = extract_pinned(download(arguments.url), pinned)
    arguments.target.mkdir(parents=True, exist_ok=True)
    for name, data in contents.items():
        (arguments.target / name).write_bytes(data)
        print(f"ok  {pinned[name]}  {name}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
