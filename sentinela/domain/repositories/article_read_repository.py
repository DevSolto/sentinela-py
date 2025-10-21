"""Contrato de leitura dedicado à consulta de artigos."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable

from sentinela.domain.entities import Article


class ArticleReadRepository(ABC):
    """Define operações de leitura sobre artigos já armazenados."""

    @abstractmethod
    def list_by_period(
        self,
        portal_name: str,
        start: datetime,
        end: datetime,
        *,
        city: str | None = None,
    ) -> Iterable[Article]:
        """Listar artigos de um portal dentro do intervalo informado."""
