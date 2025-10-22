"""Main orchestration service for entity extraction."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from sentinela.domain.entities.article import CityMention

from .gazetteer import CityGazetteer, find_city_pattern_matches
from .models import (
    ArticleCitiesWriter,
    CityOccurrence,
    EntitySpan,
    NewsDocument,
    PersonOccurrence,
    ProcessedBatchResult,
    ExtractionResultWriter,
    NewsRepository,
)
from .ner import NEREngine
from .normalization import (
    extract_state_mentions,
    find_sentence_containing,
    normalize_article_text,
    normalize_person_name,
)


_PERSON_LABELS = {"PERSON", "PER"}
_CITY_LABELS = {"LOC", "LOCATION", "GPE", "CITY"}


class EntityExtractionService:
    """Coordinates the full pipeline of the entity extraction microservice."""

    def __init__(
        self,
        *,
        news_repository: NewsRepository,
        result_writer: ExtractionResultWriter,
        ner_engine: NEREngine,
        gazetteer: CityGazetteer,
        ner_version: str,
        gazetteer_version: str,
        batch_size: int = 500,
        article_cities_writer: ArticleCitiesWriter | None = None,
    ) -> None:
        self._news_repository = news_repository
        self._result_writer = result_writer
        self._ner_engine = ner_engine
        self._gazetteer = gazetteer
        self._ner_version = ner_version
        self._gazetteer_version = gazetteer_version
        self._batch_size = batch_size
        self._article_cities_writer = article_cities_writer
        self._log = logging.getLogger("sentinela.entity_extraction")

    def process_next_batch(self) -> ProcessedBatchResult:
        """Fetch and process the next batch of news awaiting extraction."""

        batch = list(
            self._news_repository.fetch_pending(
                self._batch_size, self._ner_version, self._gazetteer_version
            )
        )
        processed = 0
        skipped_empty = 0
        errors: List[Tuple[str, str]] = []

        for document in batch:
            try:
                if not document.title and not document.body:
                    skipped_empty += 1
                    self._news_repository.mark_processed(
                        document.url,
                        self._ner_version,
                        self._gazetteer_version,
                        datetime.now(timezone.utc),
                    )
                    continue
                self._process_document(document)
                self._news_repository.mark_processed(
                    document.url,
                    self._ner_version,
                    self._gazetteer_version,
                    datetime.now(timezone.utc),
                )
                processed += 1
            except Exception as exc:  # pragma: no cover - defensive logging
                message = str(exc)
                errors.append((document.url, message))
                self._log.exception("Falha ao processar notícia %s", document.url)
                self._news_repository.mark_error(document.url, message)

        return ProcessedBatchResult(
            processed=processed,
            skipped_empty=skipped_empty,
            errors=tuple(errors),
        )

    def _process_document(self, document: NewsDocument) -> None:
        combined = document.combined_text()
        normalized_text = normalize_article_text(combined)
        entities = list(self._ner_engine.analyze(normalized_text))
        state_mentions = extract_state_mentions(normalized_text)

        person_entities = [e for e in entities if e.label in _PERSON_LABELS]
        city_entities = [e for e in entities if e.label in _CITY_LABELS]

        person_cache: Dict[str, str] = {}
        for entity in person_entities:
            normalized = normalize_person_name(entity.text)
            if not normalized.canonical_name:
                continue
            person_id = person_cache.get(normalized.canonical_name)
            if not person_id:
                person_id = self._result_writer.ensure_person(
                    normalized.canonical_name, normalized.aliases
                )
                person_cache[normalized.canonical_name] = person_id
            sentence = find_sentence_containing(
                normalized_text, entity.start, entity.end
            )
            occurrence = PersonOccurrence(
                person_id=person_id,
                canonical_name=normalized.canonical_name,
                surface=entity.text,
                start=entity.start,
                end=entity.end,
                sentence=sentence,
                method=entity.method,
                confidence=entity.score,
            )
            self._result_writer.record_person_occurrence(document.url, occurrence)

        # Augment city entities with deterministic pattern matches
        seen_spans: set[Tuple[int, int]] = {(e.start, e.end) for e in city_entities}
        for surface, span, uf_surface in find_city_pattern_matches(normalized_text):
            if span in seen_spans:
                continue
            city_entities.append(
                EntitySpan(
                    label="CITY_PATTERN",
                    text=surface,
                    start=span[0],
                    end=span[1],
                    score=0.9,
                    method="pattern",
                )
            )
            seen_spans.add(span)

        city_occurrences: list[CityOccurrence] = []
        for entity in city_entities:
            city_name, uf_surface = _split_city_surface(entity.text)
            resolution = self._gazetteer.resolve(
                city_name,
                uf_surface=uf_surface,
                context_states=state_mentions,
            )
            sentence = find_sentence_containing(
                normalized_text, entity.start, entity.end
            )
            occurrence = CityOccurrence(
                city_id=resolution.city_id,
                surface=entity.text,
                start=entity.start,
                end=entity.end,
                sentence=sentence,
                status=resolution.status,
                uf_surface=uf_surface,
                method=entity.method,
                confidence=entity.score * resolution.confidence,
                candidates=resolution.candidates,
            )
            city_occurrences.append(occurrence)

        aggregated_cities = _aggregate_city_mentions(city_occurrences)
        if self._article_cities_writer is not None:
            self._article_cities_writer.update_article_cities(
                document.url,
                aggregated_cities,
                portal=document.source,
            )

        for occurrence in city_occurrences:
            self._result_writer.record_city_occurrence(document.url, occurrence)


def _split_city_surface(surface: str) -> tuple[str, str | None]:
    """Extract the canonical city name and optional UF from a surface form."""

    text = surface.strip()
    for separator in ("-", "/"):
        if separator in text:
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) >= 2 and parts[-1].isalpha() and len(parts[-1]) == 2:
                uf = parts[-1].upper()
                name = separator.join(parts[:-1]).strip()
                return name, uf
    return text, None


def _aggregate_city_mentions(
    occurrences: list[CityOccurrence],
) -> tuple[CityMention, ...]:
    """Agrupa ocorrências de cidades preservando metadados relevantes."""

    entries: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    label_index: dict[str, str] = {}

    for occurrence in occurrences:
        surface = occurrence.surface.strip()
        if not surface and not occurrence.city_id:
            continue
        normalized_label = surface.lower()
        candidate = _select_candidate_for_occurrence(occurrence)
        city_id = occurrence.city_id or candidate.get("city_id")
        key = city_id or label_index.get(normalized_label) or normalized_label

        if city_id and city_id not in entries and normalized_label in label_index:
            previous_key = label_index[normalized_label]
            if previous_key in entries:
                entry = entries.pop(previous_key)
                idx = order.index(previous_key)
                order[idx] = city_id
                entry["identifier"] = city_id
                entry["city_id"] = city_id
                entries[city_id] = entry
                label_index[normalized_label] = city_id
                key = city_id

        if key not in entries:
            entries[key] = {
                "identifier": city_id or surface,
                "city_id": city_id,
                "label": candidate.get("label") or surface,
                "uf": candidate.get("uf") or occurrence.uf_surface,
                "occurrences": 0,
                "sources": [],
            }
            order.append(key)
            label_index[normalized_label] = key

        entry = entries[key]
        entry["occurrences"] += 1

        if entry.get("city_id") is None and city_id:
            entry["city_id"] = city_id
            entry["identifier"] = city_id
        if not entry.get("label") and candidate.get("label"):
            entry["label"] = candidate["label"]
        if not entry.get("uf") and (candidate.get("uf") or occurrence.uf_surface):
            entry["uf"] = candidate.get("uf") or occurrence.uf_surface

        method = occurrence.method
        sources = entry.setdefault("sources", [])
        if method and method not in sources:
            sources.append(method)

    mentions: list[CityMention] = []
    for key in order:
        data = entries[key]
        if not data.get("city_id"):
            continue
        mentions.append(
            CityMention(
                identifier=str(data.get("city_id") or data["identifier"]),
                city_id=str(data["city_id"]) if data.get("city_id") is not None else None,
                label=str(data["label"]) if data.get("label") is not None else None,
                uf=str(data["uf"]) if data.get("uf") is not None else None,
                occurrences=int(data.get("occurrences", 1)),
                sources=tuple(data.get("sources", ())),
            )
        )
    return tuple(mentions)


def _select_candidate_for_occurrence(occurrence: CityOccurrence) -> dict[str, Any]:
    """Seleciona o candidato mais adequado para enriquecer a menção."""

    if occurrence.city_id:
        for candidate in occurrence.candidates:
            if candidate.city_id == occurrence.city_id:
                return {
                    "city_id": candidate.city_id,
                    "label": candidate.name,
                    "uf": candidate.uf,
                }
    if occurrence.candidates:
        top = occurrence.candidates[0]
        return {
            "city_id": top.city_id,
            "label": top.name,
            "uf": top.uf,
        }
    return {
        "city_id": occurrence.city_id,
        "label": occurrence.surface.strip(),
        "uf": occurrence.uf_surface,
    }


__all__ = ["EntityExtractionService"]
