"""Repositório que integra com a API HTTP de publicações."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import requests

from sentinela.extraction import NewsDocument, NewsRepository


class PublicationsAPIRepository(NewsRepository):
    """Obtém notícias pendentes diretamente do serviço de publicações."""

    def __init__(
        self,
        base_url: str,
        *,
        session: requests.Session | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Configura o cliente HTTP utilizado nas chamadas para a API."""

        self._base_url = base_url.rstrip("/")
        """URL base normalizada do serviço de publicações."""

        self._session: requests.Session = session or requests.Session()
        """Sessão HTTP compartilhada para reaproveitar conexões persistentes."""

        self._timeout: float = timeout
        """Tempo limite aplicado a todas as chamadas HTTP realizadas."""

    def fetch_pending(
        self, batch_size: int, ner_version: str, gazetteer_version: str
    ) -> Iterable[NewsDocument]:
        """Busca notícias aguardando processamento na API remota."""

        response = self._session.get(
            f"{self._base_url}/extraction/pending",
            params={
                "limit": batch_size,
                "ner_version": ner_version,
                "gazetteer_version": gazetteer_version,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items", [])
        return [self._deserialize(item) for item in items]

    def mark_processed(
        self, url: str, ner_version: str, gazetteer_version: str, processed_at: datetime
    ) -> None:
        """Informa à API que a notícia foi processada com sucesso."""

        self._session.post(
            f"{self._base_url}/extraction/processed",
            json={
                "url": url,
                "ner_version": ner_version,
                "gazetteer_version": gazetteer_version,
                "processed_at": processed_at.isoformat(),
            },
            timeout=self._timeout,
        ).raise_for_status()

    def mark_error(self, url: str, message: str) -> None:
        """Registra uma falha durante o processamento da notícia."""

        self._session.post(
            f"{self._base_url}/extraction/error",
            json={"url": url, "message": message},
            timeout=self._timeout,
        ).raise_for_status()

    @classmethod
    def _deserialize(cls, data: dict) -> NewsDocument:
        """Converte o JSON da API no modelo ``NewsDocument`` usado internamente."""

        published_raw = data.get("published_at")
        published_at = cls._parse_datetime(published_raw)
        return NewsDocument(
            url=str(data["url"]),
            title=str(data.get("title") or ""),
            body=str(data.get("body") or data.get("content") or ""),
            published_at=published_at,
            source=data.get("source"),
        )

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        """Tenta interpretar valores retornados pela API como datas válidas."""

        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(value, fmt)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed
                except ValueError:
                    continue
        return datetime.fromtimestamp(0, timezone.utc)


__all__ = ["PublicationsAPIRepository"]
