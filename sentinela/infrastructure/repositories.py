"""Mongo repository implementations."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from pymongo.collection import Collection

from sentinela.domain import Article, Portal, PortalSelectors, Selector
from sentinela.domain.repositories import (
    ArticleReadRepository,
    ArticleRepository,
    PortalRepository,
)


class MongoPortalRepository(PortalRepository):
    """MongoDB implementation of :class:`PortalRepository`."""

    def __init__(self, collection: Collection) -> None:
        self._collection = collection

    def add(self, portal: Portal) -> None:
        self._collection.insert_one(self._serialize_portal(portal))

    def get_by_name(self, name: str) -> Optional[Portal]:
        data = self._collection.find_one({"name": name})
        if not data:
            return None
        return self._deserialize_portal(data)

    def list_all(self) -> Iterable[Portal]:
        for data in self._collection.find():
            yield self._deserialize_portal(data)

    def _serialize_portal(self, portal: Portal) -> dict:
        return {
            "name": portal.name,
            "base_url": portal.base_url,
            "listing_path_template": portal.listing_path_template,
            "headers": portal.headers,
            "date_format": portal.date_format,
            "selectors": {
                "listing_article": portal.selectors.listing_article.__dict__,
                "listing_title": portal.selectors.listing_title.__dict__,
                "listing_url": portal.selectors.listing_url.__dict__,
                "article_content": portal.selectors.article_content.__dict__,
                "article_date": portal.selectors.article_date.__dict__,
                "listing_summary": portal.selectors.listing_summary.__dict__
                if portal.selectors.listing_summary
                else None,
            },
        }

    def _deserialize_portal(self, data: dict) -> Portal:
        selectors = data["selectors"]
        return Portal(
            name=data["name"],
            base_url=data["base_url"],
            listing_path_template=data["listing_path_template"],
            headers=data.get("headers", {}),
            date_format=data.get("date_format", "%Y-%m-%d"),
            selectors=PortalSelectors(
                listing_article=Selector(**selectors["listing_article"]),
                listing_title=Selector(**selectors["listing_title"]),
                listing_url=Selector(**selectors["listing_url"]),
                article_content=Selector(**selectors["article_content"]),
                article_date=Selector(**selectors["article_date"]),
                listing_summary=Selector(**selectors["listing_summary"])
                if selectors.get("listing_summary")
                else None,
            ),
        )


class MongoArticleRepository(ArticleRepository):
    """MongoDB implementation of :class:`ArticleRepository`."""

    def __init__(self, collection: Collection) -> None:
        self._collection = collection
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


class MongoArticleReadRepository(ArticleReadRepository):
    """Read-only repository for articles stored in MongoDB."""

    def __init__(self, collection: Collection) -> None:
        self._collection = collection

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
