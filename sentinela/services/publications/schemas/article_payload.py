"""Modelos Pydantic para representar artigos recebidos por integrações externas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from sentinela.domain import Article


class ArticlePayload(BaseModel):
    """Estrutura intermediária para validar artigos recebidos na API."""

    #: Identificador do portal que originou o artigo recebido.
    portal: str
    #: Título do artigo exatamente como enviado pela integração.
    title: str
    #: URL pública que referencia o conteúdo completo do artigo.
    url: str
    #: Corpo integral do artigo em texto puro para indexação.
    content: str
    #: Momento de publicação informado pelo portal na requisição.
    published_at: datetime
    #: Resumo opcional do conteúdo para visualização rápida.
    summary: str | None = None

    def to_domain(self) -> Article:
        """Converte os dados validados em uma entidade de domínio ``Article``."""

        return Article(
            portal_name=self.portal,
            title=self.title,
            url=self.url,
            content=self.content,
            summary=self.summary,
            published_at=self.published_at,
        )


__all__ = ["ArticlePayload"]
