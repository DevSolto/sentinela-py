"""Adapters for ingesting new articles into the publications service."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from fastapi import APIRouter
from pydantic import BaseModel, Field

from sentinela.domain.entities import Article
from sentinela.domain.repositories import ArticleRepository


class ArticlePayload(BaseModel):
    """Payload representing an article received from another service."""

    portal: str
    title: str
    url: str
    content: str
    published_at: datetime
    summary: str | None = None

    def to_domain(self) -> Article:
        return Article(
            portal_name=self.portal,
            title=self.title,
            url=self.url,
            content=self.content,
            summary=self.summary,
            published_at=self.published_at,
        )


class ArticleBatchPayload(BaseModel):
    """Collection of articles ingested in a single request."""

    articles: list[ArticlePayload] = Field(default_factory=list)

    def to_domain(self) -> Iterable[Article]:
        for payload in self.articles:
            yield payload.to_domain()


def create_ingestion_router(repository: ArticleRepository) -> APIRouter:
    """Create a router exposing endpoints for ingesting new articles."""

    router = APIRouter(prefix="/articles", tags=["Ingestão"])

    def serialize(article: Article) -> dict:
        return {
            "portal": article.portal_name,
            "title": article.title,
            "url": article.url,
            "content": article.content,
            "summary": article.summary,
            "published_at": article.published_at.isoformat(),
        }

    @router.post("/batch")
    def ingest_articles(payload: ArticleBatchPayload) -> dict:
        articles = list(payload.to_domain())
        new_articles: list[Article] = []
        for article in articles:
            if not repository.exists(article.portal_name, article.url):
                new_articles.append(article)
        if new_articles:
            repository.save_many(new_articles)
        return {"stored": [serialize(article) for article in new_articles]}

    return router


__all__ = ["create_ingestion_router", "ArticlePayload", "ArticleBatchPayload"]
