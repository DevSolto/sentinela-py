"""Adapter responsible for synchronizing article cities in MongoDB."""
from __future__ import annotations

from pymongo.collection import Collection

from sentinela.extraction.models import ArticleCitiesWriter


class MongoArticleCitiesWriter(ArticleCitiesWriter):
    """Updates the list of cities associated with an article document."""

    def __init__(self, collection: Collection) -> None:
        self._collection = collection

    def update_article_cities(
        self, url: str, cities: tuple[str, ...], *, portal: str | None = None
    ) -> None:
        criteria = {"url": url}
        if portal:
            criteria["portal_name"] = portal
        self._collection.update_many(
            criteria,
            {"$set": {"cities": list(cities)}},
        )


__all__ = ["MongoArticleCitiesWriter"]
