"""Casos de uso relacionados à consulta de publicações."""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from ..domain import Article
from ..domain.repositories import ArticleReadRepository


class ArticleQueryService:
    """Fornece acesso somente leitura aos artigos armazenados."""

    def __init__(self, repository: ArticleReadRepository) -> None:
        self._repository = repository

    def list_articles(
        self,
        portal_name: str,
        start_date: date,
        end_date: date,
        *,
        city: str | None = None,
    ) -> Iterable[Article]:
        """Lista artigos publicados dentro do intervalo de datas informado."""

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        return self._repository.list_by_period(
            portal_name, start_dt, end_dt, city=city
        )


__all__ = ["ArticleQueryService"]
