"""Contratos de persistência específicos do serviço de publicações."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable

from ..entities import Article


class ArticleRepository(ABC):
    """Define operações de escrita para o contexto de publicações."""

    @abstractmethod
    def save_many(self, articles: Iterable[Article]) -> None:
        """Persiste um conjunto de artigos no armazenamento definitivo."""

    @abstractmethod
    def exists(self, portal_name: str, url: str) -> bool:
        """Verifica se já existe um artigo cadastrado para a combinação informada."""

    @abstractmethod
    def list_by_period(
        self, portal_name: str, start: datetime, end: datetime
    ) -> Iterable[Article]:
        """Recupera artigos de um portal dentro do intervalo especificado."""


__all__ = ["ArticleRepository"]
