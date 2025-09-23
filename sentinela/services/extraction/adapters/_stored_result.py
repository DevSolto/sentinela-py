"""Estruturas auxiliares usadas pelo armazenamento em memória."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sentinela.extraction import CityOccurrence, PersonOccurrence


@dataclass
class _StoredResult:
    """Representa o estado mutável de uma notícia enriquecida."""

    url: str
    ner_version: str
    gazetteer_version: str
    people: list[PersonOccurrence] = field(default_factory=list)
    cities: list[CityOccurrence] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = ["_StoredResult"]
