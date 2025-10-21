"""Dependency container for the publications service."""
from __future__ import annotations

from dataclasses import dataclass

from sentinela.infrastructure.database import MongoClientFactory
from sentinela.services.extraction import ExtractionResultStore, get_default_result_store

from .application import ArticleQueryService
from .infrastructure import (
    MongoArticleCitiesWriter,
    MongoArticleReadRepository,
    MongoArticleRepository,
)


@dataclass
class PublicationsContainer:
    """Container exposing the service dependencies for publications."""

    article_repository: MongoArticleRepository
    query_service: ArticleQueryService
    extraction_store: ExtractionResultStore
    article_cities_writer: MongoArticleCitiesWriter
    article_reader: MongoArticleReadRepository | None = None


def build_publications_container(
    factory: MongoClientFactory | None = None,
) -> PublicationsContainer:
    """Build the publications service container."""

    factory = factory or MongoClientFactory()
    database = factory.get_database()

    collection = database["articles"]
    article_repository = MongoArticleRepository(collection)
    article_reader = MongoArticleReadRepository(collection)
    article_cities_writer = MongoArticleCitiesWriter(collection)
    query_service = ArticleQueryService(article_reader)

    return PublicationsContainer(
        article_repository=article_repository,
        query_service=query_service,
        extraction_store=get_default_result_store(),
        article_cities_writer=article_cities_writer,
        article_reader=article_reader,
    )
