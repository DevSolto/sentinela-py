from __future__ import annotations

from copy import deepcopy

from sentinela.services.publications.city_matching.storage import MongoCityCatalogStorage


class _FakeCollection:
    def __init__(self) -> None:
        self._documents: dict[str, dict] = {}

    def find_one(self, criteria: dict[str, str]):
        key = criteria.get("_id")
        if key is None:
            return None
        document = self._documents.get(key)
        if document is None:
            return None
        return deepcopy(document)

    def replace_one(self, criteria: dict[str, str], document: dict, upsert: bool = False):
        if not upsert and criteria.get("_id") not in self._documents:
            return
        self._documents[criteria.get("_id")] = deepcopy(document)


def test_mongo_storage_persists_and_loads_payload() -> None:
    collection = _FakeCollection()
    storage = MongoCityCatalogStorage(collection)  # type: ignore[arg-type]

    payload = {
        "metadata": {"record_count": 2, "version": "test"},
        "data": [
            {"ibge_id": "5300108", "name": "Brasília", "uf": "DF"},
            {"ibge_id": "3550308", "name": "São Paulo", "uf": "SP"},
        ],
    }

    storage.save("test", payload)
    loaded = storage.load("test")

    assert loaded == payload


def test_mongo_storage_ignores_empty_payload() -> None:
    collection = _FakeCollection()
    storage = MongoCityCatalogStorage(collection)  # type: ignore[arg-type]

    storage.save("test", {"metadata": {"record_count": 0}})

    assert storage.load("test") is None
