"""Infrastructure public API for Sentinela.

Exposes concrete implementations and helpers so consumers can import from
``sentinela.infrastructure`` directly.
"""

from .database import MongoClientFactory, MongoSettings
from .repositories import MongoArticleRepository, MongoPortalRepository
from .scraper import RequestsSoupScraper, Scraper

__all__ = [
    "MongoSettings",
    "MongoClientFactory",
    "MongoPortalRepository",
    "MongoArticleRepository",
    "Scraper",
    "RequestsSoupScraper",
]
