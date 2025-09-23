"""Fila em memória responsável por coordenar notícias pendentes."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import MutableMapping

from sentinela.extraction import NewsDocument


@dataclass
class PendingNewsQueue:
    """Coordena a troca de notícias pendentes entre API e worker."""

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    """Garante exclusão mútua durante operações de fila."""

    _queue: list[NewsDocument] = field(default_factory=list, init=False, repr=False)
    """Itens aguardando processamento."""

    _inflight: MutableMapping[str, NewsDocument] = field(
        default_factory=dict, init=False, repr=False
    )
    """Documentos entregues ao worker e ainda não confirmados."""

    def enqueue(self, document: NewsDocument) -> None:
        """Adiciona uma notícia à fila, evitando duplicatas em processamento."""

        with self._lock:
            if document.url in self._inflight:
                return
            self._queue.append(document)

    def pull(self, batch_size: int) -> list[NewsDocument]:
        """Remove até ``batch_size`` itens da fila marcando-os como em progresso."""

        batch: list[NewsDocument] = []
        with self._lock:
            while self._queue and len(batch) < batch_size:
                document = self._queue.pop(0)
                self._inflight[document.url] = document
                batch.append(document)
        return batch

    def ack(self, url: str) -> None:
        """Confirma o processamento da notícia identificada pela URL."""

        with self._lock:
            self._inflight.pop(url, None)

    def retry(self, url: str) -> None:
        """Devolve uma notícia para a fila quando ocorre erro de processamento."""

        with self._lock:
            document = self._inflight.pop(url, None)
            if document:
                self._queue.append(document)

    def queued_count(self) -> int:
        """Quantidade de itens aguardando processamento."""

        with self._lock:
            return len(self._queue)

    def inflight_count(self) -> int:
        """Quantidade de itens atualmente em processamento."""

        with self._lock:
            return len(self._inflight)

    def __len__(self) -> int:  # pragma: no cover - método auxiliar trivial
        with self._lock:
            return len(self._queue) + len(self._inflight)


__all__ = ["PendingNewsQueue"]
