"""Implementações de armazenamento para o catálogo de cidades."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Mapping

from pymongo.collection import Collection

from .catalog import CityCatalogStorage

log = logging.getLogger(__name__)


class MongoCityCatalogStorage(CityCatalogStorage):
    """Persiste o catálogo completo de cidades em uma coleção MongoDB."""

    def __init__(self, collection: Collection) -> None:
        self._collection = collection

    def load(self, version: str) -> Mapping[str, Any] | None:
        document = self._collection.find_one({"_id": version})
        if not document:
            return None

        payload: dict[str, Any] = {
            key: deepcopy(value) for key, value in document.items() if key != "_id"
        }

        return payload

    def save(self, version: str, payload: Mapping[str, Any]) -> None:
        document = {"_id": version}
        for key in ("metadata", "data"):
            if key in payload:
                document[key] = deepcopy(payload[key])

        if not document.get("data"):
            log.debug(
                "Ignorando persistência do catálogo de cidades por estar vazio: versão %s",
                version,
            )
            return

        self._collection.replace_one({"_id": version}, document, upsert=True)


__all__ = ["MongoCityCatalogStorage"]
