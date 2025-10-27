"""Leitura do catálogo versionado de municípios."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from copy import deepcopy
from collections.abc import Mapping, Sequence
from typing import Any, Callable, Protocol, runtime_checkable

from .config import CITY_CACHE_VERSION

_STATE_CAPITAL_IBGE_IDS: dict[str, str] = {
    "AC": "1200401",
    "AL": "2704302",
    "AP": "1600303",
    "AM": "1302603",
    "BA": "2927408",
    "CE": "2304400",
    "DF": "5300108",
    "ES": "3205309",
    "GO": "5208707",
    "MA": "2111300",
    "MT": "5103403",
    "MS": "5002704",
    "MG": "3106200",
    "PA": "1501402",
    "PB": "2507507",
    "PR": "4106902",
    "PE": "2611606",
    "PI": "2211001",
    "RJ": "3304557",
    "RN": "2408102",
    "RS": "4314902",
    "RO": "1100205",
    "RR": "1400100",
    "SC": "4205407",
    "SP": "3550308",
    "SE": "2800308",
    "TO": "1721000",
}

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


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_coords(entry: Mapping[str, Any]) -> dict[str, float] | None:
    candidate = entry.get("coords")
    if isinstance(candidate, Mapping):
        lat = _to_float(candidate.get("lat") or candidate.get("latitude"))
        lon = _to_float(candidate.get("lon") or candidate.get("longitude"))
        if lat is not None and lon is not None:
            return {"lat": lat, "lon": lon}

    lat = _to_float(entry.get("latitude"))
    lon = _to_float(entry.get("longitude"))
    if lat is None or lon is None:
        return None
    return {"lat": lat, "lon": lon}


def _normalize_bbox(entry: Mapping[str, Any]) -> dict[str, float] | None:
    raw_bbox = entry.get("bbox") or entry.get("bounding_box")
    if isinstance(raw_bbox, Mapping):
        normalized: dict[str, float] = {}
        key_map = {
            "south": ("south", "min_lat", "min_latitude", "min_y"),
            "west": ("west", "min_lon", "min_longitude", "min_x"),
            "north": ("north", "max_lat", "max_latitude", "max_y"),
            "east": ("east", "max_lon", "max_longitude", "max_x"),
        }
        for target, candidates in key_map.items():
            for candidate_key in candidates:
                value = raw_bbox.get(candidate_key)
                normalized_value = _to_float(value)
                if normalized_value is not None:
                    normalized[target] = normalized_value
                    break
        return normalized or None

    if isinstance(raw_bbox, Sequence) and not isinstance(raw_bbox, (str, bytes)):
        if len(raw_bbox) == 4:
            west, south, east, north = raw_bbox
            normalized_west = _to_float(west)
            normalized_south = _to_float(south)
            normalized_east = _to_float(east)
            normalized_north = _to_float(north)
            if None not in (
                normalized_west,
                normalized_south,
                normalized_east,
                normalized_north,
            ):
                return {
                    "south": normalized_south,
                    "west": normalized_west,
                    "north": normalized_north,
                    "east": normalized_east,
                }
    return None


def _summarize_state_capital(entry: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("ibge_id", "name", "uf"):
        value = entry.get(key)
        if value not in (None, ""):
            summary[key] = value
    coords = entry.get("coords")
    if isinstance(coords, Mapping):
        summary["coords"] = dict(coords)
    bbox = entry.get("bbox")
    if isinstance(bbox, Mapping):
        summary["bbox"] = dict(bbox)
    return summary


def _build_ibge_context(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    context: dict[str, Any] = {}
    for key in (
        "region",
        "state",
        "intermediate_region",
        "immediate_region",
        "mesoregion",
        "microregion",
    ):
        value = entry.get(key)
        if value not in (None, ""):
            context[key] = value
    capital = entry.get("state_capital")
    if isinstance(capital, Mapping) and capital:
        context["state_capital"] = {k: v for k, v in capital.items() if v not in (None, "")}
        if "coords" in capital and isinstance(capital["coords"], Mapping):
            context["state_capital"]["coords"] = dict(capital["coords"])
        if "bbox" in capital and isinstance(capital["bbox"], Mapping):
            context["state_capital"]["bbox"] = dict(capital["bbox"])
    return context or None


def _enrich_catalog_entries(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if len(entries) <= 1:
        return [dict(entry) for entry in entries if isinstance(entry, Mapping)]
    enriched: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        enriched_entry = dict(entry)
        ibge_id_raw = enriched_entry.get("ibge_id")
        ibge_id = str(ibge_id_raw) if ibge_id_raw is not None else None
        if ibge_id is not None:
            enriched_entry["ibge_id"] = ibge_id
        coords = _normalize_coords(enriched_entry)
        enriched_entry["coords"] = coords
        bbox = _normalize_bbox(enriched_entry)
        enriched_entry["bbox"] = bbox
        uf_value = enriched_entry.get("uf")
        uf_code = str(uf_value) if uf_value not in (None, "") else None
        is_capital = bool(enriched_entry.get("capital"))
        if ibge_id is not None and uf_code and _STATE_CAPITAL_IBGE_IDS.get(uf_code) == ibge_id:
            is_capital = True
        enriched_entry["capital"] = is_capital
        enriched.append(enriched_entry)

    capitals: dict[str, dict[str, Any]] = {}
    for entry in enriched:
        uf = entry.get("uf")
        if not uf:
            continue
        uf_code = str(uf)
        if entry.get("capital"):
            capitals[uf_code] = _summarize_state_capital(entry)
        elif _STATE_CAPITAL_IBGE_IDS.get(uf_code) == entry.get("ibge_id"):
            capitals[uf_code] = _summarize_state_capital(entry)

    for entry in enriched:
        uf = entry.get("uf")
        if uf:
            capital_summary = capitals.get(str(uf))
            if capital_summary:
                entry["state_capital"] = dict(capital_summary)
        entry["ibge_context"] = _build_ibge_context(entry) or {}

    return enriched


def _enrich_catalog_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return dict(payload)
    cloned = dict(payload)
    data = cloned.get("data")
    if isinstance(data, Sequence):
        cloned["data"] = _enrich_catalog_entries(data)
    return cloned


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

    updated_payload = _enrich_catalog_payload({"metadata": metadata, "data": cities})

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
                    enriched_stored = _enrich_catalog_payload(stored_payload)
                    _persist_payload(cache_path, enriched_stored)
                    return enriched_stored
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

    payload = _enrich_catalog_payload(_load_payload(cache_path))

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
                enriched_cached = _enrich_catalog_payload(cached_payload)
                _persist_payload(cache_path, enriched_cached)
                return enriched_cached

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
