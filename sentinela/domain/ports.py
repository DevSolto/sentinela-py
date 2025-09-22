"""Domain service ports for inter-service communication."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from .entities import Article, Portal


class PortalGateway(ABC):
    """Access point to retrieve portal configurations from remote services."""

    @abstractmethod
    def get_portal(self, name: str) -> Optional[Portal]:
        """Fetch a portal configuration by name."""


class ArticleSink(ABC):
    """Port describing how new articles are persisted externally."""

    @abstractmethod
    def publish_many(self, articles: Iterable[Article]) -> Iterable[Article]:
        """Persist a batch of articles and return the ones effectively stored."""
