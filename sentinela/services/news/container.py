"""Dependency container for news collection services."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from sentinela.application.servico_coleta_noticias import NewsCollectorService
from sentinela.infrastructure.scraper import RequestsSoupScraper
from sentinela.services.news.clients import (
    PortalServiceClient,
    PublicationsAPISink,
)
from sentinela.settings import get_api_base_url


@dataclass
class NewsContainer:
    """Container exposing news collection service dependencies."""

    portal_gateway: PortalServiceClient
    article_sink: PublicationsAPISink
    scraper: RequestsSoupScraper
    collector_service: NewsCollectorService


def build_news_container(
    *,
    portals_url: str | None = None,
    publications_url: str | None = None,
    status_publisher: Callable[[str], None] | None = None,
) -> NewsContainer:
    """Build the news collection service container."""

    default_portals_url = get_api_base_url()
    portals_url = (
        portals_url
        or os.getenv("PORTALS_SERVICE_URL")
        or default_portals_url
    )
    publications_url = publications_url or os.getenv(
        "PUBLICATIONS_SERVICE_URL", "http://localhost:8002"
    )

    portal_gateway = PortalServiceClient(portals_url)
    article_sink = PublicationsAPISink(publications_url)
    scraper = RequestsSoupScraper()

    collector_service = NewsCollectorService(
        portal_gateway=portal_gateway,
        article_sink=article_sink,
        scraper=scraper,
        status_publisher=status_publisher,
    )

    return NewsContainer(
        portal_gateway=portal_gateway,
        article_sink=article_sink,
        scraper=scraper,
        collector_service=collector_service,
    )
