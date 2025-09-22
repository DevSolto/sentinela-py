"""Domain public API for Sentinela.

This package exposes the main domain entities and repository interfaces so
consumers can import from ``sentinela.domain`` directly, e.g.::

    from sentinela.domain import Portal, Article, PortalRepository
"""

from .entities import (
    Article,
    Portal,
    PortalSelectors,
    Selector,
)
from .ports import ArticleSink, PortalGateway
from .repositories import ArticleRepository, PortalRepository

__all__ = [
    "Selector",
    "PortalSelectors",
    "Portal",
    "Article",
    "PortalRepository",
    "ArticleRepository",
    "PortalGateway",
    "ArticleSink",
]
