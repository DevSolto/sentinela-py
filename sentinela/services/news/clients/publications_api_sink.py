"""Cliente HTTP responsável por publicar artigos na API de publicações."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

import httpx

from sentinela.domain import Article, CityMention
from sentinela.domain.ports import ArticleSink


class PublicationsAPISink(ArticleSink):
    """Encaminha artigos coletados para o serviço de publicações via HTTP."""

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        timeout: float | None = None,
    ) -> None:
        """Configura o cliente HTTP utilizado para publicar os artigos.

        Parameters
        ----------
        base_url:
            URL raiz da API de publicações.
        client:
            Cliente HTTP opcional reutilizado por outros componentes.
        timeout:
            Tempo limite aplicado às requisições quando o cliente interno é criado.
        """

        self._base_url = base_url.rstrip("/")
        """URL base normalizada sem barra final."""

        managed_client = client or httpx.Client(
            base_url=self._base_url, timeout=timeout
        )
        owns_client = client is None

        self._client: httpx.Client = managed_client
        """Cliente HTTP responsável por enviar os lotes de artigos."""

        self._owns_client: bool = owns_client
        """Indica se o cliente HTTP deve ser fechado por esta classe."""

    def publish_many(self, articles: Iterable[Article]) -> Iterable[Article]:
        """Publica um conjunto de artigos e retorna apenas os aceitos pela API."""

        payload = [self._article_to_payload(article) for article in articles]
        if not payload:
            return []
        response = self._client.post("/articles/batch", json={"articles": payload})
        response.raise_for_status()
        body = response.json()
        stored = body.get("stored", [])
        return [self._article_from_payload(item) for item in stored]

    def close(self) -> None:
        """Fecha o cliente HTTP caso esta instância seja a proprietária dele."""

        if self._owns_client:
            self._client.close()

    @staticmethod
    def _article_to_payload(article: Article) -> dict:
        """Serializa um ``Article`` para o formato aceito pela API HTTP."""

        return {
            "portal": article.portal_name,
            "title": article.title,
            "url": article.url,
            "content": article.content,
            "summary": article.summary,
            "published_at": article.published_at.isoformat(),
            "cities": [mention.to_mapping() for mention in article.cities],
            "cities_extraction": article.cities_extraction,
        }

    @staticmethod
    def _article_from_payload(payload: dict) -> Article:
        """Reconstrói um ``Article`` a partir da resposta do serviço."""

        return Article(
            portal_name=payload["portal"],
            title=payload["title"],
            url=payload["url"],
            content=payload["content"],
            summary=payload.get("summary"),
            published_at=datetime.fromisoformat(payload["published_at"]),
            cities=CityMention.parse_many(payload.get("cities") or ()),
            cities_extraction=payload.get("cities_extraction"),
            raw=payload.get("raw", {}),
        )


__all__ = ["PublicationsAPISink"]
