"""Job para enriquecer geograficamente artigos pendentes no MongoDB."""

from __future__ import annotations

import gc
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from pymongo import ASCENDING
from pymongo.collection import Collection

from sentinela.infrastructure.database import MongoClientFactory
from sentinela.services.publications.city_matching import CityMatcher, load_city_catalog
from sentinela.services.publications.city_matching.storage import MongoCityCatalogStorage
from sentinela.services.publications.city_matching.extractor import extract_cities_from_article
from sentinela.services.publications.geo_cli import (
    GeoOutput,
    RawMatch,
    _aggregate_result,
    _apply_signals,
    _build_raw_matches,
    _disambiguate_matches,
    _geo_output_to_mapping,
    _prepare_catalog_entries,
    _resolve_article_id,
    enrich_geo,
)


@dataclass(frozen=True)
class GeoEnrichmentJobResult:
    """Resumo das métricas coletadas ao executar o job de geo enrichment."""

    scanned: int
    processed: int
    enriched: int
    skipped: int
    errors: tuple[tuple[str, str], ...]
    elapsed_ms_total: int
    dry_run: bool = False

    def to_mapping(self) -> dict[str, Any]:
        """Serializa o resultado completo para inspeção ou logs."""

        return {
            "scanned": self.scanned,
            "processed": self.processed,
            "enriched": self.enriched,
            "skipped": self.skipped,
            "errors": [list(item) for item in self.errors],
            "elapsed_ms_total": self.elapsed_ms_total,
            "dry_run": self.dry_run,
        }

    def to_summary(self) -> dict[str, int]:
        """Retorna um resumo reduzido com as principais métricas."""

        return {
            "processed": self.processed,
            "enriched": self.enriched,
            "skipped": self.skipped,
            "elapsed_ms_total": self.elapsed_ms_total,
        }


class GeoEnrichmentJob:
    """Processa artigos pendentes aplicando enriquecimento geográfico."""

    def __init__(
        self,
        collection: Collection,
        matcher: CityMatcher,
        catalog_payload: Mapping[str, Any],
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._collection = collection
        self._matcher = matcher
        self._catalog_payload = catalog_payload
        try:
            self._catalog_entries = tuple(_prepare_catalog_entries(catalog_payload))
        except ValueError as exc:
            raise RuntimeError("Catálogo carregado não possui formato esperado") from exc
        metadata_value = catalog_payload.get("metadata") if isinstance(catalog_payload, Mapping) else None
        self._catalog_metadata = metadata_value if isinstance(metadata_value, Mapping) else None
        self._log = logger or logging.getLogger("sentinela.geo_enrichment_job")

    def run(
        self,
        *,
        batch_size: int = 100,
        dry_run: bool = False,
        portal: str | None = None,
        include_extraction: bool = True,
        id_field: str = "id",
        fallback_ids: Sequence[str] | None = None,
    ) -> GeoEnrichmentJobResult:
        """Executa o job varrendo artigos pendentes por ``geo-enriquecido``."""

        if batch_size <= 0:
            raise ValueError("batch_size deve ser maior que zero")

        fallback_ids = tuple(fallback_ids or ("url", "_id"))

        job_start = time.perf_counter()

        scanned = 0
        processed = 0
        enriched = 0
        skipped = 0
        errors: list[tuple[str, str]] = []

        criteria: dict[str, Any] = {
            "$or": [
                {"geo-enriquecido": {"$exists": False}},
                {"geo-enriquecido": False},
            ]
        }
        if portal:
            criteria["portal_name"] = portal

        cursor = self._collection.find(criteria).sort("_id", ASCENDING)
        try:
            cursor = cursor.batch_size(batch_size)
        except AttributeError:
            # Coleções falsas usadas em testes podem não implementar batch_size
            pass

        try:
            for document in cursor:
                scanned += 1
                identifier = self._resolve_identifier(document)
                article_doc = document
                payload: Mapping[str, Any] | None = None
                try:
                    try:
                        payload = self._compute_enrichment(
                            article_doc,
                            id_field=id_field,
                            fallback_ids=fallback_ids,
                            include_extraction=include_extraction,
                        )
                    except Exception as exc:  # pragma: no cover - logging defensivo
                        message = str(exc)
                        errors.append((identifier, message))
                        self._log.exception(
                            "Falha ao enriquecer geograficamente o artigo %s", identifier
                        )
                        continue

                    processed += 1

                    if dry_run:
                        self._log.info(
                            "[dry-run] Atualizaria %s com enriquecimento geográfico",
                            identifier,
                        )
                        enriched += 1
                    else:
                        if not self._persist_enrichment(article_doc, payload):
                            skipped += 1
                            errors.append(
                                (
                                    identifier,
                                    "Não foi possível atualizar o documento com o enriquecimento",
                                )
                            )
                            continue
                        enriched += 1
                finally:
                    if payload is not None:
                        del payload
                    del article_doc
                    del document
                    gc.collect()
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()

        elapsed_ms = int((time.perf_counter() - job_start) * 1000)

        return GeoEnrichmentJobResult(
            scanned=scanned,
            processed=processed,
            enriched=enriched,
            skipped=skipped,
            errors=tuple(errors),
            elapsed_ms_total=elapsed_ms,
            dry_run=dry_run,
        )

    def _compute_enrichment(
        self,
        document: Mapping[str, Any],
        *,
        id_field: str,
        fallback_ids: Sequence[str],
        include_extraction: bool,
    ) -> Mapping[str, Any]:
        article_payload = self._build_article_payload(document)
        extraction_payload = extract_cities_from_article(article_payload, self._matcher)
        raw_matches: Iterable[RawMatch] = _build_raw_matches(extraction_payload)
        article_id = _resolve_article_id(article_payload, id_field, fallback_ids)

        def load_catalog() -> Sequence[Mapping[str, Any]]:
            return self._catalog_entries

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
                catalog_metadata=self._catalog_metadata,
            )

        output = enrich_geo(
            article_payload,
            raw_matches,
            load_catalog=load_catalog,
            apply_signals=apply_signals,
            disambiguate=disambiguate,
            aggregate=aggregate,
        )

        include_extraction_payload = include_extraction and isinstance(extraction_payload, Mapping)
        payload = _geo_output_to_mapping(
            output,
            include_extraction=include_extraction_payload,
            extraction_payload=extraction_payload,
        )
        return payload

    def _build_article_payload(self, document: Mapping[str, Any]) -> dict[str, Any]:
        keys_to_copy = {
            "id",
            "url",
            "title",
            "body",
            "content",
            "summary",
            "classification",
            "catalog_metadata",
            "catalog_version",
            "raw",
            "portal_name",
            "published_at",
        }
        payload: dict[str, Any] = {}
        for key in keys_to_copy:
            if key in document:
                payload[key] = document[key]
        return payload

    def _persist_enrichment(self, document: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
        update = {
            "$set": {
                "geo-enriquecido": True,
                "geo_enriquecido": True,
                "geo_enrichment": payload,
                "geo_enriched_at": datetime.now(timezone.utc),
            }
        }

        criteria: dict[str, Any] | None = None
        document_id = document.get("_id")
        if document_id is not None:
            criteria = {"_id": document_id}
        elif document.get("url"):
            criteria = {"url": document.get("url")}

        if criteria is None:
            return False

        result = self._collection.update_one(criteria, update)
        if getattr(result, "modified_count", 0):
            return True

        if criteria.get("_id") and document.get("url"):
            fallback_result = self._collection.update_one({"url": document.get("url")}, update)
            if getattr(fallback_result, "modified_count", 0):
                return True

        return False

    def _resolve_identifier(self, document: Mapping[str, Any]) -> str:
        candidates = (
            document.get("url"),
            document.get("id"),
            document.get("_id"),
        )
        for value in candidates:
            if value not in (None, ""):
                return str(value)
        return "unknown-article"


def build_geo_enrichment_job(
    *,
    factory: MongoClientFactory | None = None,
    catalog_version: str | None = None,
    ensure_complete: bool = False,
    primary_source: str = "ibge",
    minimum_record_count: int = 5000,
) -> GeoEnrichmentJob:
    """Constroi o job padrão de enriquecimento geográfico."""

    factory = factory or MongoClientFactory()
    database = factory.get_database()
    collection = database["articles"]
    catalog_storage = MongoCityCatalogStorage(database["city_catalog"])

    catalog_payload = load_city_catalog(
        version=catalog_version,
        ensure_complete=ensure_complete,
        primary_source=primary_source,
        minimum_record_count=minimum_record_count,
        storage=catalog_storage,
    )

    matcher = CityMatcher(catalog_payload)

    return GeoEnrichmentJob(collection, matcher, catalog_payload)


__all__ = [
    "GeoEnrichmentJob",
    "GeoEnrichmentJobResult",
    "build_geo_enrichment_job",
]

