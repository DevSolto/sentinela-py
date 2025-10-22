"""Leitura do catálogo versionado de municípios."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from copy import deepcopy
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from .config import CITY_CACHE_VERSION

log = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_DEFAULT_MIN_RECORD_COUNT = 5000


def get_cache_path(version: str | None = None) -> Path:
    """Retorna o caminho para o arquivo de cache da versão informada."""

    selected_version = version or CITY_CACHE_VERSION
    filename = f"municipios_br_{selected_version}.json"
    return _DATA_DIR / filename


@runtime_checkable
class CityCatalogStorage(Protocol):
    """Abstração para persistir e recuperar catálogos de cidades."""

    def load(self, version: str) -> Mapping[str, Any] | None:
        """Retorna o catálogo previamente persistido para a versão informada."""

        raise NotImplementedError

    def save(self, version: str, payload: Mapping[str, Any]) -> None:
        """Persiste o catálogo para a versão informada."""

        raise NotImplementedError


def _get_record_count(metadata: Mapping[str, Any] | None) -> int | None:
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get("record_count")
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _compute_checksum(cities: list[dict[str, Any]]) -> str:
    serialized = json.dumps(
        cities,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _now_isoformat() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clone_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        return deepcopy(payload)
    return deepcopy(dict(payload))


def _should_refresh(metadata: Mapping[str, Any] | None, minimum_record_count: int) -> bool:
    record_count = _get_record_count(metadata)
    if record_count is None:
        return True
    return record_count < minimum_record_count


def _load_payload(cache_path: Path) -> dict[str, Any]:
    with cache_path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _persist_payload(cache_path: Path, payload: Mapping[str, Any]) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except OSError as exc:
        log.warning("Falha ao persistir catálogo atualizado em %s: %s", cache_path, exc)


def _refresh_catalog(
    *,
    cache_path: Path,
    payload: dict[str, Any],
    version: str | None,
    primary_source: str,
    fetcher: Callable[[str], tuple[list[dict[str, Any]], str]] | None,
    storage: CityCatalogStorage | None,
) -> dict[str, Any] | None:
    try:
        if fetcher is None:
            from .build_cache import CityCatalogError, fetch_catalog

            fetcher = fetch_catalog
        else:
            from .build_cache import CityCatalogError
    except ImportError:  # pragma: no cover - cenário improvável
        log.warning("Não foi possível importar utilitários de catálogo remoto")
        return None

    try:
        cities, source = fetcher(primary_source)
    except CityCatalogError as exc:
        log.warning(
            "Falha ao baixar catálogo completo de municípios a partir de %s: %s",
            primary_source,
            exc,
        )
        return None

    metadata = dict(payload.get("metadata") or {})
    metadata.update(
        {
            "version": version or CITY_CACHE_VERSION,
            "primary_source": primary_source,
            "source": source,
            "downloaded_at": _now_isoformat(),
            "record_count": len(cities),
            "checksum": _compute_checksum(cities),
        }
    )

    updated_payload = {"metadata": metadata, "data": cities}

    _persist_payload(cache_path, updated_payload)

    if storage is not None:
        try:
            storage.save(version or CITY_CACHE_VERSION, updated_payload)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("Falha ao persistir catálogo no armazenamento externo: %s", exc)

    return updated_payload


def load_city_catalog(
    version: str | None = None,
    *,
    ensure_complete: bool = False,
    primary_source: str = "ibge",
    minimum_record_count: int = _DEFAULT_MIN_RECORD_COUNT,
    fetcher: Callable[[str], tuple[list[dict[str, Any]], str]] | None = None,
    storage: CityCatalogStorage | None = None,
) -> dict[str, Any]:
    """Carrega o catálogo de municípios da versão informada.

    Quando ``ensure_complete`` é ``True`` e o arquivo versionado contiver poucos
    municípios (amostra de capitais utilizada em ambientes offline), o catálogo
    completo é baixado dinamicamente antes de ser retornado.
    """

    selected_version = version or CITY_CACHE_VERSION
    cache_path = get_cache_path(version)

    stored_payload: dict[str, Any] | None = None
    if storage is not None:
        try:
            cached = storage.load(selected_version)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning(
                "Falha ao carregar catálogo do armazenamento externo: %s", exc
            )
        else:
            if isinstance(cached, Mapping):
                stored_payload = _clone_payload(cached)
                stored_metadata = (
                    stored_payload.get("metadata")
                    if isinstance(stored_payload.get("metadata"), Mapping)
                    else None
                )
                if not ensure_complete or not _should_refresh(
                    stored_metadata, minimum_record_count
                ):
                    _persist_payload(cache_path, stored_payload)
                    return stored_payload
            elif cached is not None:  # pragma: no cover - defensive
                log.warning(
                    "Catálogo retornado pelo armazenamento externo possui formato inesperado: %s",
                    type(cached),
                )

    if not cache_path.exists():
        raise FileNotFoundError(
            f"Catálogo de municípios não encontrado em {cache_path}. "
            "Execute o builder de cache ou informe outra versão."
        )

    payload = _load_payload(cache_path)

    if not ensure_complete:
        return payload

    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    if not _should_refresh(metadata, minimum_record_count):
        if storage is not None:
            try:
                storage.save(selected_version, payload)
            except Exception as exc:  # pragma: no cover - defensive
                log.warning(
                    "Falha ao sincronizar catálogo completo no armazenamento: %s", exc
                )
        return payload

    if storage is not None:
        cached_payload = stored_payload
        if cached_payload is None:
            try:
                cached = storage.load(selected_version)
            except Exception as exc:  # pragma: no cover - defensive
                log.warning(
                    "Falha ao carregar catálogo do armazenamento externo: %s", exc
                )
                cached = None
            if isinstance(cached, Mapping):
                cached_payload = _clone_payload(cached)
        if cached_payload is not None:
            cached_metadata = (
                cached_payload.get("metadata")
                if isinstance(cached_payload.get("metadata"), Mapping)
                else None
            )
            if not _should_refresh(cached_metadata, minimum_record_count):
                _persist_payload(cache_path, cached_payload)
                return cached_payload

    refreshed = _refresh_catalog(
        cache_path=cache_path,
        payload=payload if isinstance(payload, dict) else {},
        version=version,
        primary_source=primary_source,
        fetcher=fetcher,
        storage=storage,
    )
    return refreshed or payload


__all__ = ["CityCatalogStorage", "get_cache_path", "load_city_catalog"]
