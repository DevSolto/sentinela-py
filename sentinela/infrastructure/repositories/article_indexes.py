"""Utilitários para criação de índices da coleção de artigos."""
from __future__ import annotations

from pymongo.collection import Collection


def ensure_article_indexes(collection: Collection) -> None:
    """Garante que todos os índices necessários para artigos existam."""

    definitions: tuple[tuple[list[tuple[str, int]], dict[str, object]], ...] = (
        (
            [("portal_name", 1), ("url", 1)],
            {"name": "portal_url_unique", "unique": True, "background": True},
        ),
        (
            [("portal_name", 1), ("published_at", 1)],
            {"name": "portal_published_at", "background": True},
        ),
        (
            [("cities", 1), ("published_at", 1)],
            {"name": "cities_published_at", "background": True},
        ),
        (
            [("cities.identifier", 1), ("published_at", 1)],
            {"name": "city_identifier_published_at", "background": True},
        ),
        (
            [("cities.ibge_id", 1)],
            {"name": "city_ibge_id", "background": True},
        ),
        (
            [("cities.name", 1)],
            {"name": "city_name", "background": True},
        ),
        (
            [("cities.uf", 1)],
            {"name": "city_uf", "background": True},
        ),
        (
            [("cities_extraction.version", 1)],
            {
                "name": "cities_extraction_version",
                "background": True,
                "partialFilterExpression": {
                    "cities_extraction.version": {"$exists": True}
                },
            },
        ),
    )

    for keys, options in definitions:
        collection.create_index(keys, **options)


__all__ = ["ensure_article_indexes"]
