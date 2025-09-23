"""Implementação MongoDB do repositório de artigos de publicações."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from pymongo.collection import Collection

from ..domain import Article
from ..domain.repositories import ArticleRepository


class MongoArticleRepository(ArticleRepository):
    """Persiste entidades :class:`Article` utilizando MongoDB."""

    def __init__(self, collection: Collection) -> None:
        self._collection: Collection = collection
        """Coleção MongoDB responsável por armazenar os artigos."""

        self._collection.create_index(
            [
                ("portal_name", 1),
                ("url", 1),
            ],
            unique=True,
            background=True,
        )
        self._collection.create_index(
            [
                ("portal_name", 1),
                ("published_at", 1),
            ],
            background=True,
        )

    def save_many(self, articles: Iterable[Article]) -> None:
        documents = [self._serialize_article(article) for article in articles]
        if documents:
            self._collection.insert_many(documents, ordered=False)

    def exists(self, portal_name: str, url: str) -> bool:
        return (
            self._collection.count_documents(
                {"portal_name": portal_name, "url": url}, limit=1
            )
            > 0
        )

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
            yield self._deserialize_article(data)

    def _serialize_article(self, article: Article) -> dict:
        return {
            "portal_name": article.portal_name,
            "title": article.title,
            "url": article.url,
            "content": article.content,
            "summary": article.summary,
            "published_at": article.published_at,
            "raw": article.raw,
        }

    def _deserialize_article(self, data: dict) -> Article:
        return Article(
            portal_name=data["portal_name"],
            title=data["title"],
            url=data["url"],
            content=data["content"],
            summary=data.get("summary"),
            published_at=data["published_at"],
            raw=data.get("raw", {}),
        )


__all__ = ["MongoArticleRepository"]
