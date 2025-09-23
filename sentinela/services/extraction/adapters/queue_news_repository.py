"""Repositório que entrega notícias a partir da fila em memória."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sentinela.extraction import NewsDocument, NewsRepository

from .pending_news_queue import PendingNewsQueue


class QueueNewsRepository(NewsRepository):
    """Implementa ``NewsRepository`` usando :class:`PendingNewsQueue`."""

    def __init__(self, queue: PendingNewsQueue) -> None:
        """Guarda a fila utilizada como backend do repositório."""

        self._queue = queue
        """Fila compartilhada entre API e worker de extração."""

    def fetch_pending(
        self, batch_size: int, ner_version: str, gazetteer_version: str
    ) -> Iterable[NewsDocument]:
        """Entrega os próximos documentos disponíveis na fila."""

        return self._queue.pull(batch_size)

    def mark_processed(
        self, url: str, ner_version: str, gazetteer_version: str, processed_at: datetime
    ) -> None:
        """Confirma o processamento da URL informada removendo-a dos inflight."""

        self._queue.ack(url)

    def mark_error(self, url: str, message: str) -> None:
        """Retorna a notícia para a fila para futura tentativa."""

        self._queue.retry(url)


__all__ = ["QueueNewsRepository"]
