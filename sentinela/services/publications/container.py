"""Dependency container for publications queries."""
from __future__ import annotations

from dataclasses import dataclass

from sentinela.application.services import ArticleQueryService
from sentinela.infrastructure.database import MongoClientFactory
from sentinela.infrastructure.repositories import MongoArticleReadRepository


@dataclass
class PublicationsContainer:
    """Container exposing publication query dependencies."""

    article_repository: MongoArticleReadRepository
    query_service: ArticleQueryService


def build_publications_container(
    factory: MongoClientFactory | None = None,
) -> PublicationsContainer:
    """Build the publications service container."""

    factory = factory or MongoClientFactory()
    database = factory.get_database()

    article_repository = MongoArticleReadRepository(database["articles"])
    query_service = ArticleQueryService(article_repository)

    return PublicationsContainer(
        article_repository=article_repository,
        query_service=query_service,
    )
