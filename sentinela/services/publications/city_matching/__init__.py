"""Utilidades para trabalhar com o catálogo de municípios."""

from .aggregator import (
    AggregatedCity,
    aggregate_city_mentions,
    aggregate_with_primary_city,
    primary_city_selection,
)
from .catalog import CityCatalogStorage, get_cache_path, load_city_catalog
from .config import CITY_CACHE_VERSION
from .extractor import extract_cities_from_article
from .matcher import CityMatch, CityMatcher
from .signals import enrich_matches_with_signals
from .storage import MongoCityCatalogStorage

__all__ = [
    "CITY_CACHE_VERSION",
    "CityCatalogStorage",
    "CityMatch",
    "CityMatcher",
    "AggregatedCity",
    "aggregate_city_mentions",
    "aggregate_with_primary_city",
    "MongoCityCatalogStorage",
    "enrich_matches_with_signals",
    "primary_city_selection",
    "extract_cities_from_article",
    "get_cache_path",
    "load_city_catalog",
]
