"""Representações imutáveis dos resultados de enriquecimento."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sentinela.extraction import CityOccurrence, PersonOccurrence


@dataclass(frozen=True, slots=True)
class EnrichedArticleResult:
    """Instantâneo das entidades encontradas em uma notícia."""

    url: str
    ner_version: str
    gazetteer_version: str
    updated_at: datetime
    people: tuple[PersonOccurrence, ...]
    cities: tuple[CityOccurrence, ...]


__all__ = ["EnrichedArticleResult"]
