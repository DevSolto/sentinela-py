"""Migrations de bootstrap para o serviço de publicações."""
from __future__ import annotations

from collections.abc import Callable

from pymongo.database import Database

from sentinela.infrastructure.database import MongoClientFactory
from sentinela.infrastructure.repositories.article_indexes import ensure_article_indexes

Migration = Callable[[Database], None]


def _ensure_article_indexes(database: Database) -> None:
    """Cria os índices necessários na coleção de artigos."""

    ensure_article_indexes(database["articles"])


_MIGRATIONS: tuple[Migration, ...] = (_ensure_article_indexes,)


def run(factory: MongoClientFactory | None = None) -> None:
    """Executa as migrations de bootstrap contra o banco configurado."""

    factory = factory or MongoClientFactory()
    database = factory.get_database()

    for migration in _MIGRATIONS:
        migration(database)


__all__ = ["run"]
