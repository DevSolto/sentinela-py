"""Dataclasses and shared models for the entity extraction microservice."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Protocol


@dataclass(frozen=True, slots=True)
class NewsDocument:
    """Representation of a news article stored in MongoDB."""

    url: str
    title: str
    body: str
    published_at: datetime
    source: str | None = None

    def combined_text(self) -> str:
        """Return the text to be analysed by the NER pipeline."""

        parts = [part.strip() for part in (self.title, self.body) if part]
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class EntitySpan:
    """Entity mention identified by the NER engine or rules."""

    label: str
    text: str
    start: int
    end: int
    score: float
    method: str = "ner"


@dataclass(frozen=True, slots=True)
class NormalizedPersonName:
    """Canonical representation for a person mention."""

    canonical_name: str
    aliases: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class PersonOccurrence:
    """Occurrence of a person mention inside a news article."""

    person_id: str
    canonical_name: str
    surface: str
    start: int
    end: int
    sentence: str
    method: str
    confidence: float


@dataclass(frozen=True, slots=True)
class CityCandidate:
    """Candidate resolution for a city mention."""

    city_id: str
    name: str
    uf: str
    score: float


@dataclass(frozen=True, slots=True)
class CityOccurrence:
    """Representation of a city mention in a news article."""

    city_id: str | None
    surface: str
    start: int
    end: int
    sentence: str
    status: str
    uf_surface: str | None
    method: str
    confidence: float
    candidates: tuple[CityCandidate, ...]


@dataclass(frozen=True, slots=True)
class CityResolution(CityOccurrence):
    """Alias for readability when returning resolved city information."""


@dataclass(frozen=True, slots=True)
class ProcessedBatchResult:
    """Outcome summary for a processed batch of news."""

    processed: int
    errors: tuple[tuple[str, str], ...]
    skipped_empty: int = 0


class NewsRepository(Protocol):
    """Abstraction over MongoDB access used by the extraction microservice."""

    def fetch_pending(
        self, batch_size: int, ner_version: str, gazetteer_version: str
    ) -> Iterable[NewsDocument]:
        """Retrieve a batch of articles pending entity extraction."""

    def mark_processed(
        self, url: str, ner_version: str, gazetteer_version: str, processed_at: datetime
    ) -> None:
        """Mark a document as processed with the given versions."""

    def mark_error(self, url: str, message: str) -> None:
        """Register that a document failed to be processed."""


class ExtractionResultWriter(Protocol):
    """Persists entities and relations into the relational store."""

    def ensure_person(self, canonical_name: str, aliases: set[str]) -> str:
        """Return the identifier of the person, inserting if necessary."""

    def record_person_occurrence(self, url: str, occurrence: PersonOccurrence) -> None:
        """Persist the relation between the news and the person occurrence."""

    def record_city_occurrence(self, url: str, occurrence: CityOccurrence) -> None:
        """Persist the relation between the news and the city occurrence."""


class ArticleCitiesWriter(Protocol):
    """Synchronizes the aggregated list of cities associated with an article."""

    def update_article_cities(
        self, url: str, cities: tuple[str, ...], *, portal: str | None = None
    ) -> None:
        """Persist the list of resolved cities for the given article."""
