"""CLI para executar o enriquecimento geográfico de artigos."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from dotenv import load_dotenv

from sentinela.services.publications.city_matching import (
    CityMatcher,
    aggregate_with_primary_city,
    extract_cities_from_article,
    load_city_catalog,
)


def _load_geo_module():
    """Carrega o módulo terceirizado de enriquecimento geográfico."""

    try:  # pragma: no cover - caminho preferencial quando instalado como pacote
        import farol_geo_enrichment  # type: ignore[import-not-found]

        return farol_geo_enrichment
    except Exception:  # pragma: no cover - fallback para layout monorepo
        import importlib.util

        module_path = (
            Path(__file__).resolve().parents[3]
            / "packages/@farol/geo-enrichment/__init__.py"
        )
        spec = importlib.util.spec_from_file_location(
            "farol_geo_enrichment",
            module_path,
            submodule_search_locations=[str(module_path.parent)],
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Não foi possível localizar o módulo de geo enrichment")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


_geo_module = _load_geo_module()
RawMatch = _geo_module.RawMatch
GeoOutput = _geo_module.GeoOutput
enrich_geo = _geo_module.enrich_geo


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa o pipeline de enriquecimento geográfico para um artigo"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    enrich = subparsers.add_parser(
        "enrich", help="Processa um artigo JSON e gera o payload enriquecido"
    )
    enrich.add_argument(
        "article",
        type=str,
        help="Caminho do arquivo JSON do artigo (use '-' para ler de stdin)",
    )
    enrich.add_argument(
        "--output",
        type=Path,
        help="Arquivo para salvar o resultado em JSON (padrão: stdout)",
    )
    enrich.add_argument(
        "--pretty",
        action="store_true",
        help="Formata o JSON de saída com indentação",
    )
    enrich.add_argument(
        "--catalog",
        type=Path,
        help="Caminho alternativo para o catálogo de municípios em JSON",
    )
    enrich.add_argument(
        "--catalog-version",
        default=None,
        help="Versão do catálogo quando usar o carregamento padrão",
    )
    enrich.add_argument(
        "--ensure-complete",
        action="store_true",
        help=(
            "Baixa o catálogo completo caso o arquivo local contenha apenas uma amostra"
        ),
    )
    enrich.add_argument(
        "--minimum-record-count",
        type=int,
        default=5000,
        help="Quantidade mínima de cidades esperada ao validar o catálogo",
    )
    enrich.add_argument(
        "--primary-source",
        default="ibge",
        help="Identificador da fonte primária usada ao atualizar o catálogo",
    )
    enrich.add_argument(
        "--id-field",
        default="id",
        help="Campo a usar como identificador principal do artigo (default: id)",
    )
    enrich.add_argument(
        "--fallback-id",
        action="append",
        default=["url"],
        help="Campos adicionais para tentar como identificador caso o principal esteja vazio",
    )
    enrich.add_argument(
        "--include-extraction",
        action="store_true",
        help="Inclui os dados de extração de cidades no JSON gerado",
    )
    enrich.add_argument(
        "--log-level",
        default=None,
        help="Nível de log (DEBUG, INFO, WARNING, ERROR). Padrão: INFO",
    )

    return parser.parse_args(argv)


def _read_article(path: str) -> Mapping[str, Any]:
    if path == "-":
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError as exc:  # pragma: no cover - proteção
            raise ValueError("Entrada JSON inválida em stdin") from exc
    else:
        article_path = Path(path)
        if not article_path.exists():
            raise FileNotFoundError(f"Arquivo de artigo não encontrado: {article_path}")
        with article_path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    if not isinstance(payload, Mapping):
        raise ValueError("O artigo deve ser um objeto JSON")
    return payload


def _load_catalog_from_args(args: argparse.Namespace) -> Mapping[str, Any]:
    if args.catalog:
        with args.catalog.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        if isinstance(payload, Sequence):
            return {"metadata": {"version": "custom"}, "data": list(payload)}
        if not isinstance(payload, Mapping):
            raise ValueError(
                "O catálogo informado deve ser um objeto JSON ou uma lista de cidades"
            )
        return payload

    return load_city_catalog(
        version=args.catalog_version,
        ensure_complete=args.ensure_complete,
        primary_source=args.primary_source,
        minimum_record_count=args.minimum_record_count,
    )


def _build_raw_matches(extraction_payload: Mapping[str, Any]) -> list[RawMatch]:
    matches: Sequence[Mapping[str, Any]] = extraction_payload.get("matches", [])  # type: ignore[assignment]
    raw_matches: list[RawMatch] = []
    for item in matches:
        if not isinstance(item, Mapping):
            continue
        candidate = item.get("city_id")
        candidate_id = str(candidate) if candidate not in (None, "") else None
        score = float(item.get("score") or 0.0)
        signals = item.get("signals") if isinstance(item.get("signals"), Mapping) else {}
        confidence = float(item.get("confidence") or score)
        raw_matches.append(
            RawMatch(
                surface=str(item.get("surface") or item.get("name") or ""),
                candidate_id=candidate_id,
                score=score,
                method=str(item.get("method") or "unknown"),
                signals=dict(signals),
                confidence=confidence,
            )
        )
    return raw_matches


def _normalize_name(text: str) -> str:
    return " ".join(text.lower().split())


def _prepare_catalog_entries(catalog: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    if isinstance(catalog, Mapping):
        data = catalog.get("data")
        if isinstance(data, Sequence):
            return data
    raise ValueError("O catálogo carregado não possui a chave 'data'")


def _build_name_index(entries: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    index: dict[str, list[Mapping[str, Any]]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        key = _normalize_name(name)
        index.setdefault(key, []).append(entry)
        alt_names = entry.get("alt_names")
        if isinstance(alt_names, Sequence) and not isinstance(alt_names, (str, bytes)):
            for alt in alt_names:
                alt_key = _normalize_name(str(alt))
                if alt_key:
                    index.setdefault(alt_key, []).append(entry)
    return index


def _apply_signals(
    matches: Iterable[RawMatch],
    _article: Mapping[str, Any],
    _catalog: Sequence[Mapping[str, Any]],
) -> Iterable[RawMatch]:
    for match in matches:
        signals = match.signals if isinstance(match.signals, Mapping) else {}
        confidence = match.confidence if match.confidence else match.score
        yield replace(match, signals=dict(signals), confidence=float(confidence))


def _disambiguate_matches(
    matches: Iterable[RawMatch],
    _article: Mapping[str, Any],
    catalog: Sequence[Mapping[str, Any]],
) -> Iterable[RawMatch]:
    name_index = _build_name_index(catalog)
    for match in matches:
        if match.candidate_id:
            yield match
            continue
        normalized = _normalize_name(match.surface)
        candidates = name_index.get(normalized, [])
        if not candidates:
            yield match
            continue
        context_uf = None
        if isinstance(match.signals, Mapping):
            context_uf = match.signals.get("context_uf")
        selected_id: str | None = None
        if len(candidates) == 1:
            candidate_id = candidates[0].get("ibge_id")
            if candidate_id:
                selected_id = str(candidate_id)
        elif context_uf:
            filtered = [
                item
                for item in candidates
                if str(item.get("uf") or "").upper() == str(context_uf).upper()
            ]
            if len(filtered) == 1:
                candidate_id = filtered[0].get("ibge_id")
                if candidate_id:
                    selected_id = str(candidate_id)
        if selected_id:
            yield replace(match, candidate_id=selected_id)
        else:
            yield match


def _aggregate_result(
    matches: Iterable[RawMatch],
    article: Mapping[str, Any],
    catalog: Sequence[Mapping[str, Any]],
    *,
    extraction_payload: Mapping[str, Any],
    article_id: str,
    catalog_metadata: Mapping[str, Any] | None,
) -> GeoOutput:
    prepared_matches: list[Mapping[str, Any]] = []
    for match in matches:
        signals = match.signals if isinstance(match.signals, Mapping) else {}
        prepared_matches.append(
            {
                "city_id": match.candidate_id,
                "candidate_id": match.candidate_id,
                "surface": match.surface,
                "method": match.method,
                "score": match.score,
                "confidence": match.confidence or match.score,
                "signals": dict(signals),
            }
        )

    aggregated = aggregate_with_primary_city(prepared_matches, catalog)

    metadata_value = extraction_payload.get("cities_extraction")
    if isinstance(metadata_value, Mapping):
        extraction_metadata = dict(metadata_value)
    else:
        extraction_metadata = {}

    metadata_payload: dict[str, Any] = {
        "catalog_version": None,
        "catalog_entries": len(catalog),
        "extraction": extraction_metadata,
        "matches_total": len(prepared_matches),
    }
    combined_catalog_meta: dict[str, Any] = {}
    if isinstance(catalog_metadata, Mapping):
        combined_catalog_meta.update(dict(catalog_metadata))
        metadata_payload["catalog_version"] = catalog_metadata.get("version")
    article_catalog = article.get("catalog_metadata")
    if isinstance(article_catalog, Mapping):
        combined_catalog_meta.update(article_catalog)
        if metadata_payload.get("catalog_version") is None:
            metadata_payload["catalog_version"] = article_catalog.get("version")
    payload_metadata = extraction_payload.get("metadata")
    if isinstance(payload_metadata, Mapping):
        combined_catalog_meta.update(payload_metadata)
        if metadata_payload.get("catalog_version") is None:
            metadata_payload["catalog_version"] = payload_metadata.get("version")
    if metadata_payload.get("catalog_version") is None:
        metadata_payload["catalog_version"] = article.get("catalog_version")
    if combined_catalog_meta:
        metadata_payload["catalog"] = combined_catalog_meta

    return GeoOutput(
        article_id=article_id,
        matches=tuple(matches),
        primary_city=aggregated.get("primary_city"),
        mentioned_cities=aggregated.get("mentioned_cities", ()),
        disambiguation=aggregated.get("disambiguation", {}),
        metadata=metadata_payload,
    )


def _resolve_article_id(
    article: Mapping[str, Any], id_field: str, fallbacks: Sequence[str]
) -> str:
    candidates = [id_field, *fallbacks]
    for field in candidates:
        value = article.get(field)
        if value not in (None, ""):
            return str(value)
    return "unknown-article"


def _geo_output_to_mapping(output: GeoOutput, *, include_extraction: bool, extraction_payload: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "article_id": output.article_id,
        "matches": [asdict(match) for match in output.matches],
        "primary_city": output.primary_city,
        "mentioned_cities": list(output.mentioned_cities),
        "disambiguation": output.disambiguation,
        "metadata": output.metadata,
    }
    if include_extraction:
        payload["extraction"] = {
            key: extraction_payload.get(key)
            for key in ("fields", "matches", "cities_extraction")
            if key in extraction_payload
        }
    return payload


def _configure_logging(level_name: str | None) -> None:
    level = getattr(logging, str(level_name).upper(), logging.INFO) if level_name else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def _run_enrich(args: argparse.Namespace) -> int:
    load_dotenv()
    _configure_logging(args.log_level or None)
    log = logging.getLogger("sentinela.geo_cli")

    article = _read_article(args.article)
    catalog_payload = _load_catalog_from_args(args)
    try:
        catalog_entries = _prepare_catalog_entries(catalog_payload)
    except ValueError as exc:
        raise RuntimeError("Catálogo carregado não possui formato esperado") from exc
    catalog_metadata = (
        catalog_payload.get("metadata")
        if isinstance(catalog_payload, Mapping)
        else None
    )

    matcher = CityMatcher(catalog_payload)
    extraction_payload = extract_cities_from_article(article, matcher)

    article_id = _resolve_article_id(article, args.id_field, args.fallback_id)
    raw_matches = _build_raw_matches(extraction_payload)

    def load_catalog() -> Sequence[Mapping[str, Any]]:
        return catalog_entries

    def apply_signals(
        matches: Iterable[RawMatch],
        article_doc: Mapping[str, Any],
        catalog: Sequence[Mapping[str, Any]],
    ) -> Iterable[RawMatch]:
        return tuple(_apply_signals(matches, article_doc, catalog))

    def disambiguate(
        matches: Iterable[RawMatch],
        article_doc: Mapping[str, Any],
        catalog: Sequence[Mapping[str, Any]],
    ) -> Iterable[RawMatch]:
        return tuple(_disambiguate_matches(matches, article_doc, catalog))

    def aggregate(
        matches: Iterable[RawMatch],
        article_doc: Mapping[str, Any],
        catalog: Sequence[Mapping[str, Any]],
    ) -> GeoOutput:
        return _aggregate_result(
            tuple(matches),
            article_doc,
            catalog,
            extraction_payload=extraction_payload,
            article_id=article_id,
            catalog_metadata=catalog_metadata,
        )

    output = enrich_geo(
        article,
        raw_matches,
        load_catalog=load_catalog,
        apply_signals=apply_signals,
        disambiguate=disambiguate,
        aggregate=aggregate,
    )

    if not isinstance(output, GeoOutput):  # pragma: no cover - proteção adicional
        raise RuntimeError("O pipeline retornou um tipo inesperado")

    log.info(
        "Artigo %s processado: %d matches, %d cidades mencionadas",
        article_id,
        len(output.matches),
        len(output.mentioned_cities),
    )

    payload = _geo_output_to_mapping(
        output, include_extraction=args.include_extraction, extraction_payload=extraction_payload
    )

    serialized = json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + ("\n" if not serialized.endswith("\n") else ""), encoding="utf-8")
    else:
        sys.stdout.write(serialized)
        sys.stdout.write("\n")

    return 0


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.command == "enrich":
        status = _run_enrich(args)
        raise SystemExit(status)
    raise SystemExit(1)


__all__ = ["main"]


if __name__ == "__main__":  # pragma: no cover - suporte a execução direta
    main()

