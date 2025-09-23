"""Adaptadores HTTP responsáveis pela ingestão de artigos."""

from .ingestion_router import create_ingestion_router
from ..schemas import ArticleBatchPayload, ArticlePayload

__all__ = ["ArticlePayload", "ArticleBatchPayload", "create_ingestion_router"]
