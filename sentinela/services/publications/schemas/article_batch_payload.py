"""Coleções de artigos enviados em lote para armazenamento."""
from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, Field

from sentinela.services.publications.domain import Article

from .article_payload import ArticlePayload


class ArticleBatchPayload(BaseModel):
    """Agrupamento de artigos recebidos em uma única requisição."""

    #: Conjunto validado de artigos a serem transformados em domínio.
    articles: list[ArticlePayload] = Field(default_factory=list)

    def to_domain(self) -> Iterable[Article]:
        """Gera entidades ``Article`` correspondentes a cada payload informado."""

        for payload in self.articles:
            yield payload.to_domain()


__all__ = ["ArticleBatchPayload"]
