"""Dependency container for publications queries."""
from __future__ import annotations

from dataclasses import dataclass

from sentinela.application.services import ArticleQueryService
from sentinela.infrastructure.database import MongoClientFactory
from sentinela.infrastructure.repositories import (
    MongoArticleReadRepository,
    MongoArticleRepository,
)
from .adapters import ArticleIngestionAdapter


@dataclass
class PublicationsContainer:
    """Container exposing publication query dependencies."""

    article_repository: MongoArticleRepository
    article_read_repository: MongoArticleReadRepository
    query_service: ArticleQueryService
    ingestion_adapter: ArticleIngestionAdapter


def build_publications_container(
    factory: MongoClientFactory | None = None,
) -> PublicationsContainer:
    """Build the publications service container."""

    factory = factory or MongoClientFactory()
    database = factory.get_database()

    article_collection = database["articles"]
    article_repository = MongoArticleRepository(article_collection)
    article_read_repository = MongoArticleReadRepository(article_collection)
    ingestion_adapter = ArticleIngestionAdapter(article_repository)
    query_service = ArticleQueryService(article_read_repository)

    return PublicationsContainer(
        article_repository=article_repository,
        article_read_repository=article_read_repository,
        query_service=query_service,
        ingestion_adapter=ingestion_adapter,
    )
