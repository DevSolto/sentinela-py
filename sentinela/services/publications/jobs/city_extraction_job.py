"""Job em lote para extração de cidades na coleção de artigos."""
from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv
from pymongo import ASCENDING
from pymongo.collection import Collection

from sentinela.domain.entities.article import CityMention
from sentinela.extraction.models import ArticleCitiesWriter
from sentinela.infrastructure.database import MongoClientFactory
from sentinela.services.publications.city_matching import (
    CityMatcher,
    extract_cities_from_article,
    load_city_catalog,
)
from sentinela.services.publications.city_matching.storage import MongoCityCatalogStorage
from sentinela.services.publications.infrastructure import MongoArticleCitiesWriter


@dataclass(frozen=True)
class CityExtractionJobResult:
    """Resumo das métricas coletadas ao executar o job."""

    scanned: int
    processed: int
    updated: int
    skipped: int
    ambiguous: int
    errors: tuple[tuple[str, str], ...]
    elapsed_ms_total: int
    dry_run: bool = False

    def to_mapping(self) -> dict[str, Any]:
        """Serializa o resultado para impressão ou depuração."""

        return {
            "scanned": self.scanned,
            "processed": self.processed,
            "updated": self.updated,
            "skipped": self.skipped,
            "ambiguous": self.ambiguous,
            "errors": [list(item) for item in self.errors],
            "elapsed_ms_total": self.elapsed_ms_total,
            "dry_run": self.dry_run,
        }

    def to_summary(self) -> dict[str, int]:
        """Retorna o resumo final com as métricas globais do job."""

        return {
            "processed": self.processed,
            "updated": self.updated,
            "skipped": self.skipped,
            "ambiguous": self.ambiguous,
            "elapsed_ms_total": self.elapsed_ms_total,
        }


@dataclass(frozen=True)
class _ComputedExtraction:
    """Representa o payload gerado para um único documento."""

    mentions: tuple[CityMention, ...]
    metadata: dict[str, Any]
    payload_hash: str


class CityExtractionJob:
    """Processa artigos em lotes atualizando as cidades extraídas."""

    def __init__(
        self,
        collection: Collection,
        writer: ArticleCitiesWriter,
        matcher: CityMatcher,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._collection = collection
        self._writer = writer
        self._matcher = matcher
        self._log = logger or logging.getLogger("sentinela.city_extraction")

    def run(
        self,
        *,
        batch_size: int = 100,
        force: bool = False,
        only_missing: bool = False,
        dry_run: bool = False,
        portal: str | None = None,
    ) -> CityExtractionJobResult:
        """Executa o job paginando por ``_id`` na coleção MongoDB."""

        if batch_size <= 0:
            raise ValueError("batch_size deve ser maior que zero")

        job_start = time.perf_counter()

        scanned = 0
        processed = 0
        updated = 0
        skipped = 0
        ambiguous_total = 0
        errors: list[tuple[str, str]] = []
        last_id: Any | None = None
        batch_index = 0

        while True:
            criteria: dict[str, Any] = {}
            if last_id is not None:
                criteria["_id"] = {"$gt": last_id}
            if portal:
                criteria["portal_name"] = portal

            cursor = self._collection.find(criteria).sort("_id", ASCENDING).limit(batch_size)
            documents = list(cursor)
            if not documents:
                break

            scanned += len(documents)
            batch_index += 1

            batch_processed = 0
            batch_updated = 0
            batch_skipped = 0
            batch_ambiguous = 0
            batch_start = time.perf_counter()

            for document in documents:
                document_id = document.get("_id")
                if document_id is not None:
                    last_id = document_id

                if only_missing and self._has_existing_hash(document):
                    skipped += 1
                    batch_skipped += 1
                    continue

                processed += 1
                batch_processed += 1

                try:
                    computed = self._compute_extraction(document)
                except Exception as exc:  # pragma: no cover - defensive logging
                    identifier = str(document.get("url") or document.get("_id"))
                    message = str(exc)
                    errors.append((identifier, message))
                    self._log.exception(
                        "Falha ao extrair cidades para o artigo %s", identifier
                    )
                    continue

                existing_hash = self._get_existing_hash(document)
                if not force and existing_hash == computed.payload_hash:
                    skipped += 1
                    batch_skipped += 1
                    continue

                ambiguous_mentions = sum(
                    1 for mention in computed.mentions if mention.city_id is None
                )
                ambiguous_total += ambiguous_mentions
                batch_ambiguous += ambiguous_mentions

                updated += 1
                batch_updated += 1
                url = document.get("url")
                portal = document.get("portal_name")
                if dry_run:
                    self._log.info(
                        "[dry-run] Atualizaria %s com %d cidades (%s)",
                        url,
                        len(computed.mentions),
                        computed.metadata.get("hash"),
                    )
                    continue

                self._writer.update_article_cities(
                    url,
                    computed.mentions,
                    portal=portal,
                    metadata=computed.metadata,
                )
                self._log.info(
                    "Artigo %s sincronizado com %d cidades", url, len(computed.mentions)
                )

            batch_elapsed_ms = int((time.perf_counter() - batch_start) * 1000)
            self._log.info(
                json.dumps(
                    {
                        "event": "batch_summary",
                        "batch_index": batch_index,
                        "scanned": len(documents),
                        "processed": batch_processed,
                        "updated": batch_updated,
                        "skipped": batch_skipped,
                        "ambiguous": batch_ambiguous,
                        "elapsed_ms": batch_elapsed_ms,
                    },
                    ensure_ascii=False,
                )
            )

        elapsed_ms_total = int((time.perf_counter() - job_start) * 1000)

        result = CityExtractionJobResult(
            scanned=scanned,
            processed=processed,
            updated=updated,
            skipped=skipped,
            ambiguous=ambiguous_total,
            errors=tuple(errors),
            elapsed_ms_total=elapsed_ms_total,
            dry_run=dry_run,
        )

        self._log.info(json.dumps(result.to_summary(), ensure_ascii=False))
        return result

    def _compute_extraction(self, document: Mapping[str, Any]) -> _ComputedExtraction:
        payload = extract_cities_from_article(document, self._matcher)
        mentions = _aggregate_matches(payload.get("matches") or ())
        metadata, payload_hash = self._build_metadata(payload)
        return _ComputedExtraction(mentions=mentions, metadata=metadata, payload_hash=payload_hash)

    @staticmethod
    def _has_existing_hash(document: Mapping[str, Any]) -> bool:
        metadata = document.get("cities_extraction")
        if isinstance(metadata, Mapping):
            return bool(metadata.get("hash"))
        return False

    @staticmethod
    def _get_existing_hash(document: Mapping[str, Any]) -> str | None:
        metadata = document.get("cities_extraction")
        if isinstance(metadata, Mapping):
            hash_value = metadata.get("hash")
            if hash_value:
                return str(hash_value)
        return None

    def _build_metadata(self, payload: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
        fields = payload.get("fields") or {}
        matches = payload.get("matches") or []
        payload_data = {
            "fields": copy.deepcopy(fields),
            "matches": copy.deepcopy(matches),
        }
        serialized = json.dumps(payload_data, ensure_ascii=False, sort_keys=True)
        payload_hash = sha256(serialized.encode("utf-8")).hexdigest()
        metadata = dict(payload.get("cities_extraction") or {})
        metadata.update(
            {
                "hash": payload_hash,
                "matches_count": len(matches),
                "payload": payload_data,
            }
        )
        return metadata, payload_hash


def _aggregate_matches(matches: Sequence[Mapping[str, Any]]) -> tuple[CityMention, ...]:
    entries: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    label_index: dict[str, str] = {}

    for match in matches:
        surface = str(match.get("surface") or match.get("name") or "").strip()
        canonical = str(match.get("name") or surface)
        normalized_label = canonical.strip().lower()
        city_id_value = match.get("city_id")
        city_id = str(city_id_value) if city_id_value not in (None, "") else None
        method = match.get("method")
        uf = match.get("uf") or None

        if not surface and not city_id:
            continue

        fallback_key = normalized_label or surface.lower() or city_id or surface
        key = city_id or (label_index.get(normalized_label) if normalized_label else None)
        key = key or fallback_key

        if (
            city_id
            and city_id not in entries
            and normalized_label
            and normalized_label in label_index
        ):
            previous_key = label_index[normalized_label]
            if previous_key in entries:
                entry = entries.pop(previous_key)
                try:
                    idx = order.index(previous_key)
                    order[idx] = city_id
                except ValueError:
                    order.append(city_id)
                else:
                    entries[city_id] = entry
                entry["identifier"] = city_id
                entry["city_id"] = city_id
                entries[city_id] = entry
                label_index[normalized_label] = city_id
                key = city_id

        if key not in entries:
            identifier = city_id or surface or fallback_key
            entries[key] = {
                "identifier": identifier,
                "city_id": city_id,
                "label": canonical.strip() or surface or None,
                "uf": uf,
                "occurrences": 0,
                "sources": [],
            }
            order.append(key)
            if normalized_label:
                label_index[normalized_label] = key

        entry = entries[key]
        entry["occurrences"] += 1
        if entry.get("city_id") is None and city_id:
            entry["city_id"] = city_id
            entry["identifier"] = city_id
        if not entry.get("label") and (canonical.strip() or surface):
            entry["label"] = canonical.strip() or surface
        if entry.get("uf") is None and uf:
            entry["uf"] = uf
        if method:
            sources = entry.setdefault("sources", [])
            if method not in sources:
                sources.append(method)

    mentions: list[CityMention] = []
    for key in order:
        data = entries.get(key)
        if not data or not data.get("city_id"):
            continue
        identifier = data.get("identifier") or data.get("label") or data.get("city_id") or key
        mentions.append(
            CityMention(
                identifier=str(data.get("city_id") or identifier),
                city_id=str(data["city_id"]) if data.get("city_id") is not None else None,
                label=str(data.get("label")) if data.get("label") is not None else None,
                uf=str(data.get("uf")) if data.get("uf") is not None else None,
                occurrences=int(data.get("occurrences", 1)),
                sources=tuple(data.get("sources", ())),
            )
        )
    return tuple(mentions)


def build_default_job() -> CityExtractionJob:
    """Constrói o job usando dependências reais configuradas via ambiente."""

    factory = MongoClientFactory()
    database = factory.get_database()

    catalog_storage = MongoCityCatalogStorage(database["city_catalog"])
    catalog = load_city_catalog(ensure_complete=True, storage=catalog_storage)
    matcher = CityMatcher(catalog)

    collection: Collection = database["articles"]
    writer = MongoArticleCitiesWriter(collection)

    return CityExtractionJob(collection, writer, matcher)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extrai cidades em lote para artigos")
    parser.add_argument(
        "--portal",
        type=str,
        help="Limita o processamento a um portal específico",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocessa artigos mesmo quando não há mudanças detectadas",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Limita o processamento a artigos sem hash de extração registrado",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Quantidade de documentos por página ao consultar o MongoDB",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa sem persistir alterações, exibindo apenas o resumo",
    )
    parser.add_argument(
        "--metrics-file",
        type=str,
        help="Exporta o resumo final para um arquivo JSON",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Ponto de entrada CLI para executar o job via ``python -m``."""

    load_dotenv()
    args = _parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    job = build_default_job()
    result = job.run(
        batch_size=args.batch_size,
        force=args.force,
        only_missing=args.only_missing,
        dry_run=args.dry_run,
        portal=args.portal,
    )

    summary = result.to_summary()
    print(json.dumps(summary, ensure_ascii=False))

    if args.metrics_file:
        try:
            with open(args.metrics_file, "w", encoding="utf-8") as stream:
                json.dump(summary, stream, ensure_ascii=False)
                stream.write("\n")
        except OSError as exc:  # pragma: no cover - falha de IO rara
            logging.getLogger("sentinela.city_extraction").error(
                "Falha ao escrever métricas em %s: %s", args.metrics_file, exc
            )

    if result.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
