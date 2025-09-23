"""Interfaces de repositório utilizadas pela camada de domínio."""
from .article_read_repository import ArticleReadRepository
from .article_repository import ArticleRepository
from .portal_repository import PortalRepository

__all__ = ["PortalRepository", "ArticleRepository", "ArticleReadRepository"]
