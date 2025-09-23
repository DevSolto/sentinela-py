"""Cliente HTTP responsável por consultar portais disponíveis."""
from __future__ import annotations

from typing import Optional

import httpx

from sentinela.domain import Portal, PortalSelectors, Selector
from sentinela.domain.ports import PortalGateway


class PortalServiceClient(PortalGateway):
    """Obtém dados de portais através da API do serviço de portais."""

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        timeout: float | None = None,
    ) -> None:
        """Cria o cliente configurando a URL base e o cliente HTTP interno.

        Parameters
        ----------
        base_url:
            URL raiz do serviço de portais.
        client:
            Instância de :class:`httpx.Client` reutilizável. Quando omitida, o
            cliente cria e gerencia uma instância própria.
        timeout:
            Tempo máximo de espera para requisições quando o cliente interno é
            criado automaticamente.
        """

        self._base_url = base_url.rstrip("/")
        """URL base normalizada sem barra ao final."""

        managed_client = client or httpx.Client(
            base_url=self._base_url, timeout=timeout
        )
        owns_client = client is None

        self._client: httpx.Client = managed_client
        """Cliente HTTP usado para efetuar chamadas à API."""

        self._owns_client: bool = owns_client
        """Indica se o cliente HTTP é gerenciado internamente."""

    def get_portal(self, name: str) -> Optional[Portal]:
        """Busca um portal pelo nome percorrendo a lista fornecida pela API."""

        response = self._client.get("/portals")
        response.raise_for_status()
        for payload in response.json():
            if payload.get("name") == name:
                return self._portal_from_payload(payload)
        return None

    def close(self) -> None:
        """Fecha o cliente HTTP quando a instância é de responsabilidade local."""

        if self._owns_client:
            self._client.close()

    @staticmethod
    def _selector_from_payload(payload: dict) -> Selector:
        """Converte um dicionário de seletor recebido da API em ``Selector``."""

        return Selector(query=payload["query"], attribute=payload.get("attribute"))

    @classmethod
    def _portal_from_payload(cls, payload: dict) -> Portal:
        """Reconstrói uma entidade ``Portal`` a partir do JSON retornado."""

        selectors = payload["selectors"]
        return Portal(
            name=payload["name"],
            base_url=payload["base_url"],
            listing_path_template=payload["listing_path_template"],
            selectors=PortalSelectors(
                listing_article=cls._selector_from_payload(
                    selectors["listing_article"]
                ),
                listing_title=cls._selector_from_payload(selectors["listing_title"]),
                listing_url=cls._selector_from_payload(selectors["listing_url"]),
                article_content=cls._selector_from_payload(
                    selectors["article_content"]
                ),
                article_date=cls._selector_from_payload(selectors["article_date"]),
                listing_summary=(
                    cls._selector_from_payload(selectors["listing_summary"])
                    if selectors.get("listing_summary")
                    else None
                ),
            ),
            headers=payload.get("headers", {}),
            date_format=payload.get("date_format", "%Y-%m-%d"),
        )


__all__ = ["PortalServiceClient"]
