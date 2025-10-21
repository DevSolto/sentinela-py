"""Gerador do cache versionado de municípios brasileiros."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

import requests

from .catalog import get_cache_path
from .config import CITY_CACHE_VERSION

log = logging.getLogger(__name__)


class CityCatalogError(RuntimeError):
    """Erro durante o download ou normalização do catálogo."""


@dataclass(slots=True)
class CitySource:
    name: str
    url: str


_PRIMARY_SOURCE = "ibge"
_SOURCES: dict[str, CitySource] = {
    "ibge": CitySource(
        name="IBGE Localidades API",
        url="https://servicodados.ibge.gov.br/api/v1/localidades/municipios",
    ),
    "brasilapi": CitySource(
        name="BrasilAPI",
        url="https://brasilapi.com.br/api/ibge/municipios/v1",
    ),
}


_UF_METADATA = {
    "AC": {"name": "Acre", "region": "Norte"},
    "AL": {"name": "Alagoas", "region": "Nordeste"},
    "AP": {"name": "Amapá", "region": "Norte"},
    "AM": {"name": "Amazonas", "region": "Norte"},
    "BA": {"name": "Bahia", "region": "Nordeste"},
    "CE": {"name": "Ceará", "region": "Nordeste"},
    "DF": {"name": "Distrito Federal", "region": "Centro-Oeste"},
    "ES": {"name": "Espírito Santo", "region": "Sudeste"},
    "GO": {"name": "Goiás", "region": "Centro-Oeste"},
    "MA": {"name": "Maranhão", "region": "Nordeste"},
    "MT": {"name": "Mato Grosso", "region": "Centro-Oeste"},
    "MS": {"name": "Mato Grosso do Sul", "region": "Centro-Oeste"},
    "MG": {"name": "Minas Gerais", "region": "Sudeste"},
    "PA": {"name": "Pará", "region": "Norte"},
    "PB": {"name": "Paraíba", "region": "Nordeste"},
    "PR": {"name": "Paraná", "region": "Sul"},
    "PE": {"name": "Pernambuco", "region": "Nordeste"},
    "PI": {"name": "Piauí", "region": "Nordeste"},
    "RJ": {"name": "Rio de Janeiro", "region": "Sudeste"},
    "RN": {"name": "Rio Grande do Norte", "region": "Nordeste"},
    "RS": {"name": "Rio Grande do Sul", "region": "Sul"},
    "RO": {"name": "Rondônia", "region": "Norte"},
    "RR": {"name": "Roraima", "region": "Norte"},
    "SC": {"name": "Santa Catarina", "region": "Sul"},
    "SP": {"name": "São Paulo", "region": "Sudeste"},
    "SE": {"name": "Sergipe", "region": "Nordeste"},
    "TO": {"name": "Tocantins", "region": "Norte"},
}


def _download_raw(source: str) -> list[dict[str, Any]]:
    try:
        descriptor = _SOURCES[source]
    except KeyError as exc:  # pragma: no cover - erro de programação
        raise CityCatalogError(f"Fonte desconhecida: {source}") from exc

    try:
        response = requests.get(descriptor.url, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CityCatalogError(f"Falha ao acessar {descriptor.name}: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise CityCatalogError(
            f"Resposta inválida da fonte {descriptor.name}: JSON não pôde ser decodificado"
        ) from exc

    if not isinstance(payload, list):
        raise CityCatalogError(
            f"Resposta inesperada da fonte {descriptor.name}: era esperado uma lista"
        )

    return payload


def _normalize_ibge(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in records:
        uf_info = (
            (item.get("microrregiao") or {})
            .get("mesorregiao", {})
            .get("UF", {})
        )
        region_info = uf_info.get("regiao") or {}
        normalized.append(
            {
                "ibge_id": str(item.get("id")),
                "name": item.get("nome"),
                "uf": uf_info.get("sigla"),
                "state": uf_info.get("nome"),
                "region": region_info.get("nome"),
                "mesoregion": (item.get("microrregiao") or {})
                .get("mesorregiao", {})
                .get("nome"),
                "microregion": (item.get("microrregiao") or {}).get("nome"),
            }
        )
    return normalized


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_brasilapi(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in records:
        uf_code = item.get("estado") or item.get("uf")
        uf_details = _UF_METADATA.get(uf_code or "")
        latitude = _to_float(item.get("latitude"))
        longitude = _to_float(item.get("longitude"))
        normalized.append(
            {
                "ibge_id": str(item.get("codigo_ibge") or item.get("codigo")),
                "name": item.get("nome"),
                "uf": uf_code,
                "state": (uf_details or {}).get("name"),
                "region": (uf_details or {}).get("region") or item.get("regiao"),
                "latitude": latitude,
                "longitude": longitude,
                "capital": bool(item.get("capital", False)),
                "siafi_id": item.get("siafi_id"),
                "ddd": item.get("ddd"),
                "timezone": item.get("fuso_horario") or item.get("timezone"),
            }
        )
    return normalized


def _normalize_records(source: str, raw_records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    if source == "ibge":
        records = _normalize_ibge(raw_records)
    elif source == "brasilapi":
        records = _normalize_brasilapi(raw_records)
    else:  # pragma: no cover - erro de programação
        raise CityCatalogError(f"Normalizador não definido para a fonte {source}")

    filtered = [record for record in records if record.get("ibge_id") and record.get("name")]
    if not filtered:
        raise CityCatalogError(
            f"Fonte {source} não retornou registros válidos após normalização"
        )

    dedup: dict[str, dict[str, Any]] = {}
    for record in filtered:
        key = str(record["ibge_id"])
        dedup.setdefault(key, record)
    ordered = sorted(dedup.values(), key=lambda item: (int(item["ibge_id"]) if str(item["ibge_id"]).isdigit() else item["ibge_id"], item["name"]))
    return ordered


def fetch_catalog(primary: str) -> tuple[list[dict[str, Any]], str]:
    """Obtém o catálogo usando a fonte primária e fallback automático."""

    tried: list[str] = []
    errors: list[str] = []
    for source in [primary, *[s for s in _SOURCES if s != primary]]:
        if source in tried:
            continue
        tried.append(source)
        try:
            raw_records = _download_raw(source)
            normalized = _normalize_records(source, raw_records)
            log.info("Fonte %s retornou %s municípios", source, len(normalized))
            return normalized, source
        except CityCatalogError as exc:
            log.warning("Falha ao usar fonte %s: %s", source, exc)
            errors.append(f"{source}: {exc}")
            continue

    joined = "; ".join(errors)
    raise CityCatalogError(f"Não foi possível obter o catálogo de municípios ({joined})")


def _compute_checksum(cities: list[dict[str, Any]]) -> str:
    serialized = json.dumps(cities, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def _now_isoformat() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_cache(
    *,
    primary_source: str,
    output_path: Path,
    refresh: bool,
    version: str,
) -> Path:
    if output_path.exists() and not refresh:
        log.info("Cache %s já existe; use --refresh para sobrescrever.", output_path)
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cities, final_source = fetch_catalog(primary_source)

    checksum = _compute_checksum(cities)
    metadata = {
        "version": version,
        "primary_source": primary_source,
        "source": final_source,
        "downloaded_at": _now_isoformat(),
        "record_count": len(cities),
        "checksum": checksum,
    }

    payload = {"metadata": metadata, "data": cities}

    with output_path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")

    log.info(
        "Cache salvo em %s com %s municípios (fonte efetiva: %s)",
        output_path,
        len(cities),
        final_source,
    )

    return output_path


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=_PRIMARY_SOURCE,
        choices=tuple(_SOURCES.keys()),
        help="Fonte primária para download do catálogo (default: %(default)s)",
    )
    parser.add_argument(
        "--version",
        default=CITY_CACHE_VERSION,
        help="Versão do catálogo a ser gravada (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Caminho para o arquivo de saída. Por padrão utiliza sentinela/data",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignora o cache existente e força novo download",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Nível de log (default: %(default)s)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_argument_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))

    output = args.output or get_cache_path(args.version)

    try:
        build_cache(
            primary_source=args.source,
            output_path=output,
            refresh=args.refresh,
            version=args.version,
        )
    except CityCatalogError as exc:
        log.error("Falha ao gerar o catálogo: %s", exc)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
