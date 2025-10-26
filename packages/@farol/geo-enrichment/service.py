"""Serviços para orquestrar enriquecimento geográfico."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RawMatch:
    """Representa um match bruto identificado antes da desambiguação."""

    surface: str
    candidate_id: str | None
    score: float
    method: str
    signals: Mapping[str, Any] = field(default_factory=dict)
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class GeoOutput:
    """Estrutura padronizada do resultado do enriquecimento geográfico."""

    article_id: str
    matches: tuple[RawMatch, ...]
    primary_city: Mapping[str, Any] | None = None
    mentioned_cities: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    disambiguation: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


CatalogLoader = Callable[[], Sequence[Mapping[str, Any]]]
SignalApplicator = Callable[[Iterable[RawMatch], Mapping[str, Any], Sequence[Mapping[str, Any]]], Iterable[RawMatch]]
Disambiguator = Callable[[Iterable[RawMatch], Mapping[str, Any], Sequence[Mapping[str, Any]]], Iterable[RawMatch]]
Aggregator = Callable[[Iterable[RawMatch], Mapping[str, Any], Sequence[Mapping[str, Any]]], GeoOutput]


def enrich_geo(
    article: Mapping[str, Any],
    raw_matches: Iterable[RawMatch],
    *,
    load_catalog: CatalogLoader,
    apply_signals: SignalApplicator,
    disambiguate: Disambiguator,
    aggregate: Aggregator,
) -> GeoOutput:
    """Executa o fluxo completo de enriquecimento geográfico.

    A função segue os estágios descritos abaixo:

    1. Carrega o catálogo de localidades usando ``load_catalog``.
    2. Aplica sinais sobre os ``raw_matches`` através de ``apply_signals``.
    3. Desambigua os candidatos com ``disambiguate``.
    4. Consolida o resultado final com ``aggregate``.
    """

    catalog = tuple(load_catalog())
    initial_matches = tuple(raw_matches)

    enriched_matches = tuple(apply_signals(initial_matches, article, catalog))
    resolved_matches = tuple(disambiguate(enriched_matches, article, catalog))

    result = aggregate(resolved_matches, article, catalog)
    if not isinstance(result, GeoOutput):
        raise TypeError("aggregate must return GeoOutput")
    return result


__all__ = ["GeoOutput", "RawMatch", "enrich_geo"]
