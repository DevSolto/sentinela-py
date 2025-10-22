"""Adapter responsible for synchronizing article cities in MongoDB."""
from __future__ import annotations

from pymongo.collection import Collection

from typing import Mapping

from sentinela.domain.entities.article import CityMention
from sentinela.extraction.models import ArticleCitiesWriter


class MongoArticleCitiesWriter(ArticleCitiesWriter):
    """Updates the list of cities associated with an article document."""

    def __init__(self, collection: Collection) -> None:
        self._collection = collection

    def update_article_cities(
        self,
        url: str,
        cities: tuple[CityMention, ...],
        *,
        portal: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        criteria = {"url": url}
        if portal:
            criteria["portal_name"] = portal
        filtered_cities = tuple(mention for mention in cities if mention.city_id)
        serialized_cities = [mention.to_mapping() for mention in filtered_cities]
        update: dict[str, object] = {"$set": {"cities": serialized_cities}}
        if metadata is not None:
            update["$set"]["cities_extraction"] = dict(metadata)
        else:
            update.setdefault("$unset", {})["cities_extraction"] = ""
        self._collection.update_many(
            criteria,
            update,
        )


__all__ = ["MongoArticleCitiesWriter"]
