"""Leitura do catálogo versionado de municípios."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import CITY_CACHE_VERSION

_DATA_DIR = Path(__file__).resolve().parents[4] / "data"


def get_cache_path(version: str | None = None) -> Path:
    """Retorna o caminho para o arquivo de cache da versão informada."""

    selected_version = version or CITY_CACHE_VERSION
    filename = f"municipios_br_{selected_version}.json"
    return _DATA_DIR / filename


def load_city_catalog(version: str | None = None) -> dict[str, Any]:
    """Carrega o catálogo de municípios da versão informada."""

    cache_path = get_cache_path(version)
    if not cache_path.exists():
        raise FileNotFoundError(
            f"Catálogo de municípios não encontrado em {cache_path}. "
            "Execute o builder de cache ou informe outra versão."
        )

    with cache_path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


__all__ = ["get_cache_path", "load_city_catalog"]
