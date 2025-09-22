"""Entidades de domínio utilizadas na coleta de notícias."""
from .article import Article
from .portal import Portal
from .portal_selectors import PortalSelectors
from .selector import Selector

__all__ = ["Selector", "PortalSelectors", "Portal", "Article"]
