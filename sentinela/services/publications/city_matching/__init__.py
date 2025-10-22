"""Utilidades para trabalhar com o catálogo de municípios."""

from .catalog import CityCatalogStorage, get_cache_path, load_city_catalog
from .config import CITY_CACHE_VERSION
from .extractor import extract_cities_from_article
from .matcher import CityMatch, CityMatcher
from .storage import MongoCityCatalogStorage

__all__ = [
    "CITY_CACHE_VERSION",
    "CityCatalogStorage",
    "CityMatch",
    "CityMatcher",
    "MongoCityCatalogStorage",
    "extract_cities_from_article",
    "get_cache_path",
    "load_city_catalog",
]
