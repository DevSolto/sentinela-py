"""Serviços de aplicação agregados para compatibilidade retroativa."""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from sentinela.domain import Article
from sentinela.domain.repositories import ArticleReadRepository

from .servico_coleta_noticias import NewsCollectorService
from .servico_registro_portal import PortalRegistrationService


class ArticleQueryService:
    """Provides read-only access to collected articles."""

    def __init__(self, repository: ArticleReadRepository) -> None:
        self._repository = repository

    def list_articles(
        self, portal_name: str, start_date: date, end_date: date
    ) -> Iterable[Article]:
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        return self._repository.list_by_period(portal_name, start_dt, end_dt)


__all__ = [
    "PortalRegistrationService",
    "NewsCollectorService",
    "ArticleQueryService",
]
