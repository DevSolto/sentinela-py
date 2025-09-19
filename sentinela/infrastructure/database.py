"""Mongo database utilities."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from pymongo import MongoClient


def get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Environment variable '{name}' is not set")
    return value


@dataclass
class MongoSettings:
    uri: str
    database: str

    @classmethod
    def from_env(cls) -> "MongoSettings":
        # Prefer MONGO_URI if provided; fallback to local docker-compose defaults
        uri = os.getenv(
            "MONGO_URI",
            # Default aligned with docker-compose (admin/secret on localhost)
            "mongodb://admin:secret@localhost:27017/?authSource=admin",
        )
        database = get_env("MONGO_DATABASE", "sentinela")
        return cls(uri=uri, database=database)


class MongoClientFactory:
    """Creates Mongo clients following the dependency inversion principle."""

    def __init__(self, settings: MongoSettings | None = None) -> None:
        self._settings = settings or MongoSettings.from_env()
        self._client: MongoClient | None = None

    def create_client(self) -> MongoClient:
        if not self._client:
            self._client = MongoClient(self._settings.uri)
        return self._client

    def get_database(self) -> Any:
        client = self.create_client()
        return client[self._settings.database]
