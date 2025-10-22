"""Rotinas de bootstrap para o serviço de publicações."""
from __future__ import annotations

from sentinela.infrastructure.database import MongoClientFactory

from .migrations import run as run_migrations

__all__ = ["run_migrations", "MongoClientFactory"]
