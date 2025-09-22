"""Dependency container for news collection services."""
from __future__ import annotations

from dataclasses import dataclass

from sentinela.application.services import NewsCollectorService
from sentinela.infrastructure.database import MongoClientFactory
from sentinela.infrastructure.repositories import (
    MongoArticleRepository,
    MongoPortalRepository,
)
from sentinela.infrastructure.scraper import RequestsSoupScraper


@dataclass
class NewsContainer:
    """Container exposing news collection service dependencies."""

    portal_repository: MongoPortalRepository
    article_repository: MongoArticleRepository
    scraper: RequestsSoupScraper
    collector_service: NewsCollectorService


def build_news_container(
    factory: MongoClientFactory | None = None,
) -> NewsContainer:
    """Build the news collection service container."""

    factory = factory or MongoClientFactory()
    database = factory.get_database()

    portal_repository = MongoPortalRepository(database["portals"])
    article_repository = MongoArticleRepository(database["articles"])
    scraper = RequestsSoupScraper()

    collector_service = NewsCollectorService(
        portal_repository=portal_repository,
        article_repository=article_repository,
        scraper=scraper,
    )

    return NewsContainer(
        portal_repository=portal_repository,
        article_repository=article_repository,
        scraper=scraper,
        collector_service=collector_service,
    )
