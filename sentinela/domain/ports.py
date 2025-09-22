"""Domain ports exposed for external integrations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from .entities import Article, Portal


class PortalGateway(ABC):
    """Defines how portal configurations are retrieved from external services."""

    @abstractmethod
    def get_portal(self, name: str) -> Portal | None:
        """Return the portal identified by ``name`` or ``None`` if unavailable."""


class ArticleSink(ABC):
    """Abstraction responsible for persisting collected articles."""

    @abstractmethod
    def persist(self, articles: Iterable[Article]) -> list[Article]:
        """Persist ``articles`` and return only the newly stored instances."""

