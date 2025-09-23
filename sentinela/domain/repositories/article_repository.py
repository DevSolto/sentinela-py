"""Contrato de escrita para persistência de artigos."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable

from sentinela.domain.entities import Article


class ArticleRepository(ABC):
    """Define as operações de gravação relacionadas a artigos coletados."""

    @abstractmethod
    def save_many(self, articles: Iterable[Article]) -> None:
        """Persistir um conjunto de artigos no armazenamento definitivo."""

    @abstractmethod
    def exists(self, portal_name: str, url: str) -> bool:
        """Verificar se um artigo de determinado portal e URL já está salvo."""

    @abstractmethod
    def list_by_period(
        self, portal_name: str, start: datetime, end: datetime
    ) -> Iterable[Article]:
        """Listar artigos de um portal dentro do intervalo informado."""
