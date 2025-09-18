"""Application services orchestrating domain operations."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, List

from sentinela.domain.entities import Article, Portal
from sentinela.domain.repositories import ArticleRepository, PortalRepository
from sentinela.infrastructure.scraper import Scraper


class PortalRegistrationService:
    """Handles registration and retrieval of portals."""

    def __init__(self, repository: PortalRepository) -> None:
        self._repository = repository

    def register(self, portal: Portal) -> None:
        if self._repository.get_by_name(portal.name):
            raise ValueError(f"Portal '{portal.name}' already exists")
        self._repository.add(portal)

    def list_portals(self) -> Iterable[Portal]:
        return self._repository.list_all()

    def get_portal(self, name: str) -> Portal:
        portal = self._repository.get_by_name(name)
        if not portal:
            raise ValueError(f"Portal '{name}' not found")
        return portal


class NewsCollectorService:
    """Coordinates scraping and persistence of articles."""

    def __init__(
        self,
        portal_repository: PortalRepository,
        article_repository: ArticleRepository,
        scraper: Scraper,
    ) -> None:
        self._portal_repository = portal_repository
        self._article_repository = article_repository
        self._scraper = scraper

    def collect(
        self, portal_name: str, start_date: date, end_date: date
    ) -> List[Article]:
        if start_date > end_date:
            raise ValueError("start_date must be earlier than end_date")

        portal = self._portal_repository.get_by_name(portal_name)
        if not portal:
            raise ValueError(f"Portal '{portal_name}' not found")

        collected: List[Article] = []
        current = start_date
        while current <= end_date:
            day_articles = self._scraper.collect_for_date(portal, current)
            new_articles = [
                article
                for article in day_articles
                if not self._article_repository.exists(article.portal_name, article.url)
            ]
            if new_articles:
                self._article_repository.save_many(new_articles)
                collected.extend(new_articles)
            current += timedelta(days=1)
        return collected

    def list_articles(
        self, portal_name: str, start_date: date, end_date: date
    ) -> Iterable[Article]:
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        return self._article_repository.list_by_period(portal_name, start_dt, end_dt)
