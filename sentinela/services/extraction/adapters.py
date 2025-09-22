"""Adapters used by the extraction microservice service layer."""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Iterable, Iterator, MutableMapping
from uuid import uuid4

import requests

from sentinela.extraction import (
    CityOccurrence,
    NewsDocument,
    NewsRepository,
    PersonOccurrence,
    ExtractionResultWriter,
)


@dataclass
class PendingNewsQueue:
    """In-memory queue coordinating pending news delivery between services."""

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _queue: list[NewsDocument] = field(default_factory=list, init=False, repr=False)
    _inflight: MutableMapping[str, NewsDocument] = field(
        default_factory=dict, init=False, repr=False
    )

    def enqueue(self, document: NewsDocument) -> None:
        """Add a document to the pending queue."""

        with self._lock:
            if document.url in self._inflight:
                # Avoid duplicating inflight messages. It will be re-queued on error.
                return
            self._queue.append(document)

    def pull(self, batch_size: int) -> list[NewsDocument]:
        """Return up to ``batch_size`` documents, marking them as inflight."""

        batch: list[NewsDocument] = []
        with self._lock:
            while self._queue and len(batch) < batch_size:
                document = self._queue.pop(0)
                self._inflight[document.url] = document
                batch.append(document)
        return batch

    def ack(self, url: str) -> None:
        """Acknowledge processing of the document with the given URL."""

        with self._lock:
            self._inflight.pop(url, None)

    def retry(self, url: str) -> None:
        """Return a document to the queue so it can be retried."""

        with self._lock:
            document = self._inflight.pop(url, None)
            if document:
                self._queue.append(document)

    def queued_count(self) -> int:
        """Number of documents waiting to be processed."""

        with self._lock:
            return len(self._queue)

    def inflight_count(self) -> int:
        """Number of documents currently being processed."""

        with self._lock:
            return len(self._inflight)

    def __len__(self) -> int:  # pragma: no cover - trivial helper
        with self._lock:
            return len(self._queue) + len(self._inflight)


class QueueNewsRepository(NewsRepository):
    """``NewsRepository`` backed by :class:`PendingNewsQueue`."""

    def __init__(self, queue: PendingNewsQueue) -> None:
        self._queue = queue

    def fetch_pending(
        self, batch_size: int, ner_version: str, gazetteer_version: str
    ) -> Iterable[NewsDocument]:
        return self._queue.pull(batch_size)

    def mark_processed(
        self, url: str, ner_version: str, gazetteer_version: str, processed_at: datetime
    ) -> None:
        self._queue.ack(url)

    def mark_error(self, url: str, message: str) -> None:
        self._queue.retry(url)


class PublicationsAPIRepository(NewsRepository):
    """``NewsRepository`` implementation talking to the publications HTTP API."""

    def __init__(
        self,
        base_url: str,
        *,
        session: requests.Session | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._timeout = timeout

    def fetch_pending(
        self, batch_size: int, ner_version: str, gazetteer_version: str
    ) -> Iterable[NewsDocument]:
        response = self._session.get(
            f"{self._base_url}/extraction/pending",
            params={
                "limit": batch_size,
                "ner_version": ner_version,
                "gazetteer_version": gazetteer_version,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items", [])
        return [self._deserialize(item) for item in items]

    def mark_processed(
        self, url: str, ner_version: str, gazetteer_version: str, processed_at: datetime
    ) -> None:
        self._session.post(
            f"{self._base_url}/extraction/processed",
            json={
                "url": url,
                "ner_version": ner_version,
                "gazetteer_version": gazetteer_version,
                "processed_at": processed_at.isoformat(),
            },
            timeout=self._timeout,
        ).raise_for_status()

    def mark_error(self, url: str, message: str) -> None:
        self._session.post(
            f"{self._base_url}/extraction/error",
            json={"url": url, "message": message},
            timeout=self._timeout,
        ).raise_for_status()

    @staticmethod
    def _deserialize(data: dict) -> NewsDocument:
        published_raw = data.get("published_at")
        published_at = _parse_datetime(published_raw)
        return NewsDocument(
            url=str(data["url"]),
            title=str(data.get("title") or ""),
            body=str(data.get("body") or data.get("content") or ""),
            published_at=published_at,
            source=data.get("source"),
        )


@dataclass(frozen=True, slots=True)
class EnrichedArticleResult:
    """Snapshot of the enriched entities associated with a news article."""

    url: str
    ner_version: str
    gazetteer_version: str
    updated_at: datetime
    people: tuple[PersonOccurrence, ...]
    cities: tuple[CityOccurrence, ...]


@dataclass
class _StoredResult:
    url: str
    ner_version: str
    gazetteer_version: str
    people: list[PersonOccurrence] = field(default_factory=list)
    cities: list[CityOccurrence] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def snapshot(self) -> EnrichedArticleResult:
        return EnrichedArticleResult(
            url=self.url,
            ner_version=self.ner_version,
            gazetteer_version=self.gazetteer_version,
            updated_at=self.updated_at,
            people=tuple(self.people),
            cities=tuple(self.cities),
        )


class ExtractionResultStore:
    """Thread-safe store containing enriched extraction results."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._people_index: dict[str, str] = {}
        self._aliases: dict[str, set[str]] = {}
        self._results: dict[str, _StoredResult] = {}

    def ensure_person(self, canonical_name: str, aliases: set[str]) -> str:
        with self._lock:
            person_id = self._people_index.get(canonical_name)
            if not person_id:
                person_id = str(uuid4())
                self._people_index[canonical_name] = person_id
                self._aliases[person_id] = set(aliases)
            else:
                self._aliases.setdefault(person_id, set()).update(aliases)
            return person_id

    def _ensure_record(
        self, url: str, ner_version: str, gazetteer_version: str
    ) -> _StoredResult:
        record = self._results.get(url)
        if record is None:
            record = _StoredResult(
                url=url,
                ner_version=ner_version,
                gazetteer_version=gazetteer_version,
            )
            self._results[url] = record
        elif (
            record.ner_version != ner_version
            or record.gazetteer_version != gazetteer_version
        ):
            record.ner_version = ner_version
            record.gazetteer_version = gazetteer_version
            record.people.clear()
            record.cities.clear()
        record.updated_at = datetime.now(timezone.utc)
        return record

    def append_person(
        self,
        url: str,
        occurrence: PersonOccurrence,
        *,
        ner_version: str,
        gazetteer_version: str,
    ) -> None:
        with self._lock:
            record = self._ensure_record(url, ner_version, gazetteer_version)
            record.people = _append_unique_person(record.people, occurrence)

    def append_city(
        self,
        url: str,
        occurrence: CityOccurrence,
        *,
        ner_version: str,
        gazetteer_version: str,
    ) -> None:
        with self._lock:
            record = self._ensure_record(url, ner_version, gazetteer_version)
            record.cities = _append_unique_city(record.cities, occurrence)

    def get(self, url: str) -> EnrichedArticleResult | None:
        with self._lock:
            record = self._results.get(url)
            if not record:
                return None
            return record.snapshot()

    def list(self) -> Iterator[EnrichedArticleResult]:
        with self._lock:
            for record in list(self._results.values()):
                yield record.snapshot()

    def serialize(self) -> str:
        """Serialize the store content for debugging purposes."""  # pragma: no cover

        payload = {
            url: {
                "ner_version": record.ner_version,
                "gazetteer_version": record.gazetteer_version,
                "updated_at": record.updated_at.isoformat(),
                "people": [asdict(occ) for occ in record.people],
                "cities": [
                    {
                        **asdict(occ),
                        "candidates": [asdict(candidate) for candidate in occ.candidates],
                    }
                    for occ in record.cities
                ],
            }
            for url, record in self._results.items()
        }
        return json.dumps(payload, ensure_ascii=False)


class ExtractionResultStoreWriter(ExtractionResultWriter):
    """Store-backed ``ExtractionResultWriter`` implementation."""

    def __init__(
        self,
        store: ExtractionResultStore,
        *,
        ner_version: str,
        gazetteer_version: str,
    ) -> None:
        self._store = store
        self._ner_version = ner_version
        self._gazetteer_version = gazetteer_version

    def ensure_person(self, canonical_name: str, aliases: set[str]) -> str:
        return self._store.ensure_person(canonical_name, aliases)

    def record_person_occurrence(self, url: str, occurrence: PersonOccurrence) -> None:
        self._store.append_person(
            url,
            occurrence,
            ner_version=self._ner_version,
            gazetteer_version=self._gazetteer_version,
        )

    def record_city_occurrence(self, url: str, occurrence: CityOccurrence) -> None:
        self._store.append_city(
            url,
            occurrence,
            ner_version=self._ner_version,
            gazetteer_version=self._gazetteer_version,
        )


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(value, fmt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                continue
    return datetime.fromtimestamp(0, timezone.utc)


def _append_unique_person(
    values: list[PersonOccurrence], occurrence: PersonOccurrence
) -> list[PersonOccurrence]:
    filtered = [
        value
        for value in values
        if not (
            value.person_id == occurrence.person_id
            and value.start == occurrence.start
            and value.end == occurrence.end
        )
    ]
    filtered.append(occurrence)
    return filtered


def _append_unique_city(
    values: list[CityOccurrence], occurrence: CityOccurrence
) -> list[CityOccurrence]:
    filtered = [
        value
        for value in values
        if not (
            value.city_id == occurrence.city_id
            and value.start == occurrence.start
            and value.end == occurrence.end
        )
    ]
    filtered.append(occurrence)
    return filtered


__all__ = [
    "EnrichedArticleResult",
    "ExtractionResultStore",
    "ExtractionResultStoreWriter",
    "PendingNewsQueue",
    "PublicationsAPIRepository",
    "QueueNewsRepository",
]
