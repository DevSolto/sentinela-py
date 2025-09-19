"""Application services orchestrating domain operations."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable, Iterable, List
import sys
import logging
import time

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
        self,
        portal_name: str,
        start_page: int = 1,
        max_pages: int | None = None,
        min_published_date: date | None = None,
    ) -> List[Article]:
        log = logging.getLogger("sentinela.service")
        portal = self._portal_repository.get_by_name(portal_name)
        if not portal:
            raise ValueError(f"Portal '{portal_name}' not found")
        total_new = 0
        total_seen = 0
        total_skipped_in_run = 0
        total_skipped_existing_db = 0
        total_skipped_by_date = 0
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
            current_page = page
            start_ts = time.perf_counter()
            collected = self._scraper.collect_all(
                portal, start_page=current_page, max_pages=1
            )
            elapsed = time.perf_counter() - start_ts
            if not collected:
                status(
                    f"Portal '{portal_name}': página {current_page} sem itens, encerrando."
                )
                break

            page_seen_raw = len(collected)
            total_seen += page_seen_raw
            # Filtra duplicados existentes no banco e duplicados dentro do mesmo run
            new_articles: List[Article] = []
            page_skipped_in_run = 0
            page_skipped_existing_db = 0
            page_skipped_by_date = 0
            stop_due_to_min_date = False

            if min_published_date is not None:
                filtered: List[Article] = []
                for article in collected:
                    if article.published_at.date() < min_published_date:
                        page_skipped_by_date += 1
                        stop_due_to_min_date = True
                        continue
                    filtered.append(article)
                collected = filtered

            for a in collected:
                if a.url in saved_urls:
                    page_skipped_in_run += 1
                    continue
                if not self._article_repository.exists(a.portal_name, a.url):
                    new_articles.append(a)
                    saved_urls.add(a.url)
                else:
                    page_skipped_existing_db += 1
            page_seen_considered = len(collected)
            total_skipped_in_run += page_skipped_in_run
            total_skipped_existing_db += page_skipped_existing_db
            total_skipped_by_date += page_skipped_by_date

            # Salva incrementalmente
            if new_articles:
                self._article_repository.save_many(new_articles)
                total_new += len(new_articles)
                all_new.extend(new_articles)

            status(
                "Página {page}: itens {page_seen_raw}, considerados {page_seen_considered}, novos {len_new}, "
                "descartados(run) {skip_run}, descartados(db) {skip_db}, descartados(data) {skip_date} | "
                "Tempo {elapsed:.2f}s | Totais: vistos {total_seen}, novos {total_new}, descartados(run) {total_skip_run}, "
                "descartados(db) {total_skip_db}, descartados(data) {total_skip_date}"
                .format(
                    page=current_page,
                    page_seen_raw=page_seen_raw,
                    page_seen_considered=page_seen_considered,
                    len_new=len(new_articles),
                    skip_run=page_skipped_in_run,
                    skip_db=page_skipped_existing_db,
                    skip_date=page_skipped_by_date,
                    elapsed=elapsed,
                    total_seen=total_seen,
                    total_new=total_new,
                    total_skip_run=total_skipped_in_run,
                    total_skip_db=total_skipped_existing_db,
                    total_skip_date=total_skipped_by_date,
                )
            )

            page += 1
            pages_processed += 1

            if stop_due_to_min_date:
                status(
                    "Portal '{portal}': data mínima {date} atingida na página {page}, encerrando."
                    .format(
                        portal=portal_name,
                        date=min_published_date.isoformat(),
                        page=current_page,
                    )
                )
                break

        log.info(
            "Concluído. Páginas: {pages}, vistos: {seen}, novos: {new}, descartados(run): {skip_run}, "
            "descartados(db): {skip_db}, descartados(data): {skip_date}".format(
                pages=pages_processed,
                seen=total_seen,
                new=total_new,
                skip_run=total_skipped_in_run,
                skip_db=total_skipped_existing_db,
                skip_date=total_skipped_by_date,
            )
        )
        return all_new
