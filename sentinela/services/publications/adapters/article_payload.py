"""Modelos de entrada de artigos recebidos por integrações externas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from sentinela.domain import Article


class ArticlePayload(BaseModel):
    """Representa um artigo recebido via API antes da conversão para domínio."""

    portal: str
    title: str
    url: str
    content: str
    published_at: datetime
    summary: str | None = None

    def to_domain(self) -> Article:
        """Cria uma instância de ``Article`` a partir dos dados validados."""

        return Article(
            portal_name=self.portal,
            title=self.title,
            url=self.url,
            content=self.content,
            summary=self.summary,
            published_at=self.published_at,
        )


__all__ = ["ArticlePayload"]
