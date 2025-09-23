"""Implementação MongoDB do repositório somente leitura de publicações."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from pymongo.collection import Collection

from ..domain import Article
from ..domain.repositories import ArticleReadRepository


class MongoArticleReadRepository(ArticleReadRepository):
    """Consulta artigos persistidos no MongoDB sem permitir alterações."""

    def __init__(self, collection: Collection) -> None:
        self._collection: Collection = collection
        """Coleção MongoDB da qual os artigos são consultados."""

    def list_by_period(
        self, portal_name: str, start: datetime, end: datetime
    ) -> Iterable[Article]:
        cursor = self._collection.find(
            {
                "portal_name": portal_name,
                "published_at": {"$gte": start, "$lte": end},
            }
        ).sort("published_at", 1)
        for data in cursor:
            yield Article(
                portal_name=data["portal_name"],
                title=data["title"],
                url=data["url"],
                content=data["content"],
                summary=data.get("summary"),
                published_at=data["published_at"],
                raw=data.get("raw", {}),
            )


__all__ = ["MongoArticleReadRepository"]
