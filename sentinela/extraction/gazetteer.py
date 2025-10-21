"""Gazetteer matching utilities for city resolution."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List

from .disambiguation import DisambiguationResult, disambiguate_city
from .models import CityResolution


@dataclass(frozen=True, slots=True)
class CityRecord:
    """Representation of an entry in the IBGE gazetteer."""

    id: str
    name: str
    uf: str
    alt_names: tuple[str, ...] = ()
    latitude: float | None = None
    longitude: float | None = None
    country: str = "BR"

    def variants(self) -> List[str]:
        base = [self.name]
        base.extend(self.alt_names)
        normalized_variants = []
        for value in base:
            cleaned = value.strip()
            if cleaned:
                normalized_variants.append(cleaned)
        return normalized_variants


class CityGazetteer:
    """Simple in-memory gazetteer resolver."""

    def __init__(self, cities: Iterable[CityRecord]):
        self._cities: tuple[CityRecord, ...] = tuple(cities)
        self._by_name: Dict[str, List[CityRecord]] = defaultdict(list)
        for city in self._cities:
            for variant in city.variants():
                self._by_name[self._normalize(variant)].append(city)

    @staticmethod
    def _normalize(name: str) -> str:
        return re.sub(r"\s+", " ", name).strip().lower()

    def resolve(
        self,
        surface: str,
        *,
        uf_surface: str | None,
        context_states: Iterable[str] | None = None,
    ) -> CityResolution:
        """Resolve a city mention to the gazetteer using contextual hints."""

        normalized_surface = self._normalize(surface)
        candidates = list(self._by_name.get(normalized_surface, []))

        result: DisambiguationResult = disambiguate_city(
            surface,
            candidates,
            uf_surface=uf_surface,
            context_states=context_states,
        )

        resolved_id = result.city.id if result.city is not None else None

        return CityResolution(
            city_id=resolved_id,
            surface=surface,
            start=-1,
            end=-1,
            sentence="",
            status=result.status,
            uf_surface=uf_surface,
            method="gazetteer",
            confidence=result.confidence,
            candidates=result.candidates,
        )


_CITY_UF_PATTERN = re.compile(
    r"(?P<name>[A-ZÁ-ÚÂÊÎÔÛÃÕÇ][\wÀ-ÿ' .-]{2,}?)\s*[-/]\s*(?P<uf>[A-Z]{2})"
)
_PREFEITO_PATTERN = re.compile(
    r"prefeit[ao]a?\s+de\s+(?P<name>[A-ZÁ-ÚÂÊÎÔÛÃÕÇ][\wÀ-ÿ' .-]+)",
    re.IGNORECASE,
)
_MUNICIPIO_PATTERN = re.compile(
    r"munic[ií]pio\s+de\s+(?P<name>[A-ZÁ-ÚÂÊÎÔÛÃÕÇ][\wÀ-ÿ' .-]+)",
    re.IGNORECASE,
)


def find_city_pattern_matches(text: str) -> list[tuple[str, tuple[int, int], str | None]]:
    """Return city candidates based on deterministic patterns."""

    matches: list[tuple[str, tuple[int, int], str | None]] = []
    for match in _CITY_UF_PATTERN.finditer(text):
        matches.append((match.group(0).strip(), match.span(), match.group("uf")))
    for pattern in (_PREFEITO_PATTERN, _MUNICIPIO_PATTERN):
        for match in pattern.finditer(text):
            matches.append((match.group("name").strip(), match.span("name"), None))
    return matches


__all__ = [
    "CityGazetteer",
    "CityRecord",
    "find_city_pattern_matches",
]
