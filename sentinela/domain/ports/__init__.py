"""Portas que conectam o domínio com outros serviços e adaptadores."""
from .article_sink import ArticleSink
from .portal_gateway import PortalGateway

__all__ = ["PortalGateway", "ArticleSink"]
