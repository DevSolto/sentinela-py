"""API pública do domínio da aplicação Sentinela.

O módulo centraliza as entidades, portas e repositórios mais utilizados
para que possam ser importados diretamente de ``sentinela.domain``.
"""

from .entities import Article, Portal, PortalSelectors, Selector
from .ports import ArticleSink, PortalGateway
from .repositories import ArticleReadRepository, ArticleRepository, PortalRepository

__all__ = [
    "Selector",
    "PortalSelectors",
    "Portal",
    "Article",
    "PortalRepository",
    "ArticleRepository",
    "ArticleReadRepository",
    "PortalGateway",
    "ArticleSink",
]
