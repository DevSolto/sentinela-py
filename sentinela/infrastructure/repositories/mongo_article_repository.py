"""Repositório de artigos com persistência em MongoDB."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from pymongo.collection import Collection

from sentinela.domain import Article
from sentinela.domain.repositories import ArticleRepository


class MongoArticleRepository(ArticleRepository):
    """Gerencia a persistência de :class:`Article` em coleções MongoDB."""

    def __init__(self, collection: Collection) -> None:
        """Configura índices e guarda a coleção utilizada pelo repositório."""

        self._collection: Collection = collection
        """Coleção MongoDB responsável por armazenar artigos coletados."""

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
        """Serializa e insere vários artigos de uma vez, evitando duplicatas."""

        documents = [self._serialize_article(article) for article in articles]
        if documents:
            self._collection.insert_many(documents, ordered=False)

    def exists(self, portal_name: str, url: str) -> bool:
        """Verifica se um artigo já foi gravado pela combinação portal/URL."""

        return (
            self._collection.count_documents(
                {"portal_name": portal_name, "url": url}, limit=1
            )
            > 0
        )

    def list_by_period(
        self, portal_name: str, start: datetime, end: datetime
    ) -> Iterable[Article]:
        """Recupera artigos de um portal dentro do intervalo informado."""

        cursor = self._collection.find(
            {
                "portal_name": portal_name,
                "published_at": {"$gte": start, "$lte": end},
            }
        ).sort("published_at", 1)
        for data in cursor:
            yield self._deserialize_article(data)

    def _serialize_article(self, article: Article) -> dict:
        """Converte ``Article`` em documento MongoDB preservando campos crus."""

        return {
            "portal_name": article.portal_name,
            "title": article.title,
            "url": article.url,
            "content": article.content,
            "summary": article.summary,
            "published_at": article.published_at,
            "cities": list(article.cities),
            "raw": article.raw,
        }

    def _deserialize_article(self, data: dict) -> Article:
        """Reconstrói ``Article`` a partir de um documento retornado pelo Mongo."""

        return Article(
            portal_name=data["portal_name"],
            title=data["title"],
            url=data["url"],
            content=data["content"],
            summary=data.get("summary"),
            published_at=data["published_at"],
            cities=tuple(data.get("cities") or ()),
            raw=data.get("raw", {}),
        )


__all__ = ["MongoArticleRepository"]
