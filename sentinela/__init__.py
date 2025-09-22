"""Sentinela - coletor modular de notícias."""
from .application.services import NewsCollectorService, PortalRegistrationService
from .container import build_container
from .services.news import build_news_container
from .services.portals import build_portals_container
from .domain import Article, Portal, PortalSelectors, Selector

__all__ = [
    "Article",
    "Portal",
    "PortalSelectors",
    "Selector",
    "NewsCollectorService",
    "PortalRegistrationService",
    "build_container",
    "build_news_container",
    "build_portals_container",
]
