"""Repository interfaces for the domain layer."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable, Optional

from .entities import Article, Portal


class PortalRepository(ABC):
    """Access to portal configurations."""

    @abstractmethod
    def add(self, portal: Portal) -> None:
        """Persist a new portal."""

    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Portal]:
        """Retrieve a portal by its unique name."""

    @abstractmethod
    def list_all(self) -> Iterable[Portal]:
        """Return all registered portals."""


class ArticleRepository(ABC):
    """Persistence operations for collected articles."""

    @abstractmethod
    def save_many(self, articles: Iterable[Article]) -> None:
        """Persist a batch of articles."""

    @abstractmethod
    def exists(self, portal_name: str, url: str) -> bool:
        """Check whether the article from the portal already exists."""

    @abstractmethod
    def list_by_period(
        self, portal_name: str, start: datetime, end: datetime
    ) -> Iterable[Article]:
        """List the articles that match the given period."""


class ArticleReadRepository(ABC):
    """Read-only access to persisted articles."""

    @abstractmethod
    def list_by_period(
        self, portal_name: str, start: datetime, end: datetime
    ) -> Iterable[Article]:
        """List the articles that match the given period."""
