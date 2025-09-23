"""Coleções de artigos enviadas em uma única requisição."""
from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, Field

from sentinela.domain import Article

from .article_payload import ArticlePayload


class ArticleBatchPayload(BaseModel):
    """Agrupa diversos artigos recebidos em lote pela API."""

    articles: list[ArticlePayload] = Field(default_factory=list)

    def to_domain(self) -> Iterable[Article]:
        """Gera instâncias de ``Article`` para cada item do lote."""

        for payload in self.articles:
            yield payload.to_domain()


__all__ = ["ArticleBatchPayload"]
