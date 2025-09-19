"""Application services orchestrating domain operations."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable, Iterable, List
import sys
import logging

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
        self,
        portal_name: str,
        start_date: date,
        end_date: date,
        status_callback: Callable[[str], None] | None = None,
    ) -> List[Article]:
        if start_date > end_date:
            raise ValueError("start_date must be earlier than end_date")

        portal = self._portal_repository.get_by_name(portal_name)
        if not portal:
            raise ValueError(f"Portal '{portal_name}' not found")

        if status_callback:
            status_callback(
                f"Iniciando coleta para '{portal_name}' entre {start_date} e {end_date}"
            )

        collected: List[Article] = []
        current = start_date
        while current <= end_date:
            if status_callback:
                status_callback(
                    f"Buscando artigos de {current.isoformat()}"
                )
            day_articles = self._scraper.collect_for_date(portal, current)
            new_articles = [
                article
                for article in day_articles
                if not self._article_repository.exists(article.portal_name, article.url)
            ]
            if new_articles:
                self._article_repository.save_many(new_articles)
                collected.extend(new_articles)
            if status_callback:
                status_callback(
                    f"{current.isoformat()}: encontrados {len(day_articles)} artigos, "
                    f"novos salvos {len(new_articles)}"
                )
            current += timedelta(days=1)
        if status_callback:
            status_callback(
                f"Coleta finalizada para '{portal_name}'. Total de novos artigos: {len(collected)}"
            )
        return collected

    def list_articles(
        self, portal_name: str, start_date: date, end_date: date
    ) -> Iterable[Article]:
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        return self._article_repository.list_by_period(portal_name, start_dt, end_dt)

    def collect_all_for_portal(
        self, portal_name: str, start_page: int = 1, max_pages: int | None = None
    ) -> List[Article]:
        log = logging.getLogger("sentinela.service")
        portal = self._portal_repository.get_by_name(portal_name)
        if not portal:
            raise ValueError(f"Portal '{portal_name}' not found")
        total_new = 0
        total_seen = 0
        page = max(1, start_page)
        pages_processed = 0
        saved_urls: set[str] = set()

        def status(msg: str) -> None:
            log.info(msg)

        status(
            f"Portal '{portal_name}': iniciando na página {page}"
            + (f" (limite {max_pages})" if max_pages else "")
        )

        all_new: List[Article] = []
        while True:
            if max_pages is not None and pages_processed >= max_pages:
                break

            # Coleta apenas uma página usando o scraper existente por paginação.
            collected = self._scraper.collect_all(
                portal, start_page=page, max_pages=1
            )
            if not collected:
                status(
                    f"Portal '{portal_name}': página {page} sem itens, encerrando."
                )
                break

            page_seen = len(collected)
            total_seen += page_seen
            # Filtra duplicados existentes no banco e duplicados dentro do mesmo run
            new_articles: List[Article] = []
            for a in collected:
                if a.url in saved_urls:
                    continue
                if not self._article_repository.exists(a.portal_name, a.url):
                    new_articles.append(a)
                    saved_urls.add(a.url)

            # Salva incrementalmente
            if new_articles:
                self._article_repository.save_many(new_articles)
                total_new += len(new_articles)
                all_new.extend(new_articles)

            status(
                f"Página {page}: itens {page_seen}, novos salvos {len(new_articles)} | Total: vistos {total_seen}, novos {total_new}"
            )

            page += 1
            pages_processed += 1

        log.info(
            f"Concluído. Páginas: {pages_processed}, vistos: {total_seen}, novos salvos: {total_new}"
        )
        return all_new
