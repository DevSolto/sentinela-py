"""Porta de saída responsável por publicar artigos coletados."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from sentinela.domain.entities import Article


class ArticleSink(ABC):
    """Define como os artigos coletados são entregues a sistemas externos."""

    @abstractmethod
    def publish_many(self, articles: Iterable[Article]) -> Iterable[Article]:
        """Publicar uma coleção de artigos e retornar os que foram aceitos."""
