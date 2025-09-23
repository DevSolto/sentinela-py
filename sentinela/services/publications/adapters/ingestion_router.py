"""Fábricas de rotas responsáveis por ingestão de artigos."""
from __future__ import annotations

from fastapi import APIRouter

from sentinela.domain import Article
from sentinela.domain.repositories import ArticleRepository

from .article_batch_payload import ArticleBatchPayload


def create_ingestion_router(repository: ArticleRepository) -> APIRouter:
    """Cria rotas de ingestão em lote usando o repositório informado.

    Parameters
    ----------
    repository:
        Implementação de :class:`ArticleRepository` utilizada para armazenar os
        artigos recebidos.
    """

    router = APIRouter(prefix="/articles", tags=["Ingestão"])

    def serialize(article: Article) -> dict:
        """Converte ``Article`` em resposta JSON documentando campos expostos."""

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
        """Recebe um lote de artigos, ignora duplicados e retorna os armazenados."""

        articles = list(payload.to_domain())
        new_articles: list[Article] = []
        for article in articles:
            if not repository.exists(article.portal_name, article.url):
                new_articles.append(article)
        if new_articles:
            repository.save_many(new_articles)
        return {"stored": [serialize(article) for article in new_articles]}

    return router


__all__ = ["create_ingestion_router"]
