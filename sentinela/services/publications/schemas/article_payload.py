"""Modelos Pydantic para representar artigos recebidos por integrações externas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from sentinela.services.publications.domain import Article, CityMention


class CityMentionPayload(BaseModel):
    """Representa uma cidade associada ao artigo em requisições externas."""

    identifier: str | None = None
    city_id: str | None = None
    label: str | None = None
    uf: str | None = None
    occurrences: int | None = None
    sources: list[str] | None = None

    def to_domain(self) -> CityMention:
        identifier = self.identifier or self.city_id or self.label
        if not identifier:
            raise ValueError("city payload requires at least identifier, city_id or label")
        occurrences = self.occurrences or 1
        if occurrences <= 0:
            occurrences = 1
        sources_tuple = tuple(
            str(item) for item in (self.sources or ()) if str(item)
        )
        return CityMention(
            identifier=str(identifier),
            city_id=str(self.city_id) if self.city_id is not None else None,
            label=self.label,
            uf=self.uf,
            occurrences=occurrences,
            sources=sources_tuple,
        )


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
    #: Classificação atribuída ao artigo pela integração ou enriquecimento.
    classification: str | None = None
    #: Lista de cidades associadas ao artigo fornecidas pela integração.
    cities: list[CityMentionPayload | str] = Field(default_factory=list)
    #: Metadados gerados por pipelines de extração de cidades.
    cities_extraction: dict[str, object] | None = None

    def to_domain(self) -> Article:
        """Converte os dados validados em uma entidade de domínio ``Article``."""

        mentions: list[CityMention] = []
        for item in self.cities:
            if isinstance(item, CityMentionPayload):
                try:
                    mentions.append(item.to_domain())
                except ValueError:
                    continue
            else:
                try:
                    mentions.append(CityMention.from_raw(item))
                except ValueError:
                    continue
        return Article(
            portal_name=self.portal,
            title=self.title,
            url=self.url,
            content=self.content,
            summary=self.summary,
            classification=self.classification,
            published_at=self.published_at,
            cities=tuple(mentions),
            cities_extraction=self.cities_extraction,
        )


__all__ = ["ArticlePayload", "CityMentionPayload"]
