"""Dependency container for news collection services."""
from __future__ import annotations

import os
from dataclasses import dataclass

from sentinela.application.services import NewsCollectorService
from sentinela.infrastructure.scraper import RequestsSoupScraper
from .clients import PortalServiceClient, PublicationServiceClient


def _default_portals_url() -> str:
    return os.getenv("PORTALS_SERVICE_URL", "http://localhost:8001")


def _default_publications_url() -> str:
    return os.getenv("PUBLICATIONS_SERVICE_URL", "http://localhost:8002")


@dataclass
class NewsContainer:
    """Container exposing news collection service dependencies."""

    portal_gateway: PortalServiceClient
    article_sink: PublicationServiceClient
    scraper: RequestsSoupScraper
    collector_service: NewsCollectorService


def build_news_container(
    *,
    portals_url: str | None = None,
    publications_url: str | None = None,
) -> NewsContainer:
    """Build the news collection service container."""

    scraper = RequestsSoupScraper()
    portal_gateway = PortalServiceClient(portals_url or _default_portals_url())
    article_sink = PublicationServiceClient(
        publications_url or _default_publications_url()
    )

    collector_service = NewsCollectorService(
        portal_gateway=portal_gateway,
        article_sink=article_sink,
        scraper=scraper,
    )

    return NewsContainer(
        portal_gateway=portal_gateway,
        article_sink=article_sink,
        scraper=scraper,
        collector_service=collector_service,
    )


__all__ = ["NewsContainer", "build_news_container"]

