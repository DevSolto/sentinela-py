"""Dependency container wiring infrastructure components."""
from __future__ import annotations

from dataclasses import dataclass

from sentinela.application.services import (
    NewsCollectorService,
    PortalRegistrationService,
)
from sentinela.infrastructure.database import MongoClientFactory
from sentinela.infrastructure.repositories import (
    MongoArticleRepository,
    MongoPortalRepository,
)
from sentinela.infrastructure.scraper import RequestsSoupScraper


@dataclass
class Container:
    portal_service: PortalRegistrationService
    collector_service: NewsCollectorService


def build_container() -> Container:
    factory = MongoClientFactory()
    database = factory.get_database()

    portal_repository = MongoPortalRepository(database["portals"])
    article_repository = MongoArticleRepository(database["articles"])
    scraper = RequestsSoupScraper()

    portal_service = PortalRegistrationService(portal_repository)
    collector_service = NewsCollectorService(
        portal_repository=portal_repository,
        article_repository=article_repository,
        scraper=scraper,
    )

    return Container(
        portal_service=portal_service,
        collector_service=collector_service,
    )
