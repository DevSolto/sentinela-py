"""Infrastructure public API for Sentinela.

Exposes concrete implementations and helpers so consumers can import from
``sentinela.infrastructure`` directly.
"""

from .database import MongoClientFactory, MongoSettings
from .extraction import MongoNewsRepository, PostgresExtractionResultWriter
from .repositories import (
    MongoArticleReadRepository,
    MongoArticleRepository,
    MongoPortalRepository,
)
from .scraper import RequestsSoupScraper, Scraper

__all__ = [
    "MongoSettings",
    "MongoClientFactory",
    "MongoPortalRepository",
    "MongoArticleRepository",
    "MongoArticleReadRepository",
    "MongoNewsRepository",
    "PostgresExtractionResultWriter",
    "Scraper",
    "RequestsSoupScraper",
]
