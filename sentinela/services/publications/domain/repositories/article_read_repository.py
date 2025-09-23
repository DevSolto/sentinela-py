"""Interfaces de leitura de artigos para o serviço de publicações."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable

from ..entities import Article


class ArticleReadRepository(ABC):
    """Fornece operações somente leitura sobre artigos publicados."""

    @abstractmethod
    def list_by_period(
        self, portal_name: str, start: datetime, end: datetime
    ) -> Iterable[Article]:
        """Lista artigos de um portal que pertencem ao intervalo informado."""


__all__ = ["ArticleReadRepository"]
