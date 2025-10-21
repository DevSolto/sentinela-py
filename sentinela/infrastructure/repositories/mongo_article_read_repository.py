"""Repositório somente leitura de artigos com backend MongoDB."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from pymongo.collection import Collection

from sentinela.domain import Article
from sentinela.domain.repositories import ArticleReadRepository


class MongoArticleReadRepository(ArticleReadRepository):
    """Consulta artigos persistidos no MongoDB sem permitir alterações."""

    def __init__(self, collection: Collection) -> None:
        """Guarda a coleção de artigos utilizada para leitura."""

        self._collection: Collection = collection
        """Coleção MongoDB da qual os artigos são consultados."""

    def list_by_period(
        self,
        portal_name: str,
        start: datetime,
        end: datetime,
        *,
        city: str | None = None,
    ) -> Iterable[Article]:
        """Lista artigos de um portal dentro do intervalo informado."""

        criteria: dict[str, object] = {
            "portal_name": portal_name,
            "published_at": {"$gte": start, "$lte": end},
        }
        if city:
            criteria["cities"] = city
        cursor = self._collection.find(criteria).sort("published_at", 1)
        for data in cursor:
            cities = tuple(data.get("cities") or ())
            yield Article(
                portal_name=data["portal_name"],
                title=data["title"],
                url=data["url"],
                content=data["content"],
                summary=data.get("summary"),
                classification=data.get("classification"),
                published_at=data["published_at"],
                cities=cities,
                raw=data.get("raw", {}),
            )


__all__ = ["MongoArticleReadRepository"]
