from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Iterable, Mapping

import pytest

from sentinela.services.publications.city_matching import CityMatcher
from sentinela.services.publications.jobs.geo_enrichment_job import (
    GeoEnrichmentJob,
    build_geo_enrichment_job,
)


@dataclass
class _FakeCursor:
    _documents: list[dict[str, Any]]

    def sort(self, key: str, direction: int) -> "_FakeCursor":
        reverse = direction < 0
        self._documents.sort(key=lambda item: item.get(key), reverse=reverse)
        return self

    def batch_size(self, _size: int) -> "_FakeCursor":
        return self

    def __iter__(self) -> Iterable[dict[str, Any]]:
        return iter(self._documents)

    def close(self) -> None:  # pragma: no cover - compatibilidade com pymongo
        return None


class FakeCollection:
    def __init__(self, documents: list[dict[str, Any]] | None = None) -> None:
        self._documents = [doc.copy() for doc in documents or []]

    @property
    def documents(self) -> list[dict[str, Any]]:
        return self._documents

    def find(self, criteria: dict[str, Any]) -> _FakeCursor:
        matched = [doc.copy() for doc in self._documents if _matches(doc, criteria)]
        return _FakeCursor(matched)

    def update_one(self, criteria: dict[str, Any], update: dict[str, Any]):
        modified = 0
        for document in self._documents:
            if _matches(document, criteria):
                for field, value in update.get("$set", {}).items():
                    document[field] = _deepcopy(value)
                modified = 1
                break
        return SimpleNamespace(modified_count=modified)


def _matches(document: dict[str, Any], criteria: dict[str, Any]) -> bool:
    if not criteria:
        return True
    for key, expected in criteria.items():
        if key == "$or":
            if not any(_matches(document, branch) for branch in expected):
                return False
            continue
        if isinstance(expected, dict):
            if "$exists" in expected:
                exists = key in document
                expected_flag = bool(expected["$exists"])
                if expected_flag and not exists:
                    return False
                if not expected_flag and exists:
                    return False
                continue
            if "$gt" in expected:
                if not (document.get(key) is not None and document.get(key) > expected["$gt"]):
                    return False
                continue
        if document.get(key) != expected:
            return False
    return True


def _deepcopy(value: Any) -> Any:
    if isinstance(value, list):
        return [_deepcopy(item) for item in value]
    if isinstance(value, dict):
        return {key: _deepcopy(item) for key, item in value.items()}
    return value


@pytest.fixture
def catalog_payload() -> dict[str, Any]:
    return {
        "metadata": {"version": "test"},
        "data": [
            {"ibge_id": "2504009", "name": "Campina Grande", "uf": "PB"},
            {"ibge_id": "3550308", "name": "São Paulo", "uf": "SP"},
        ],
    }


@pytest.fixture
def matcher(catalog_payload: dict[str, Any]) -> CityMatcher:
    return CityMatcher(catalog_payload)


def test_job_updates_pending_articles(matcher: CityMatcher, catalog_payload: dict[str, Any]) -> None:
    collection = FakeCollection(
        [
            {
                "_id": 1,
                "portal_name": "Portal A",
                "url": "https://example.com/a",
                "title": "Campina Grande firma acordo",
                "content": "Campina Grande firmou parceria com São Paulo.",
            },
            {
                "_id": 2,
                "portal_name": "Portal B",
                "url": "https://example.com/b",
                "title": "São Paulo recebe missão",
                "content": "Delegação visita Campina Grande.",
                "geo-enriquecido": False,
            },
        ]
    )
    job = GeoEnrichmentJob(collection, matcher, catalog_payload)

    result = job.run(batch_size=10)

    assert result.scanned == 2
    assert result.processed == 2
    assert result.enriched == 2
    assert result.skipped == 0
    assert result.errors == ()

    for document in collection.documents:
        assert document["geo-enriquecido"] is True
        assert document["geo_enriquecido"] is True
        enrichment = document["geo_enrichment"]
        assert enrichment["mentioned_cities"]


def test_job_respects_dry_run(matcher: CityMatcher, catalog_payload: dict[str, Any]) -> None:
    collection = FakeCollection(
        [
            {
                "_id": 5,
                "portal_name": "Portal A",
                "url": "https://example.com/a",
                "title": "Campina Grande firma acordo",
                "content": "Campina Grande firmou parceria com São Paulo.",
            }
        ]
    )
    job = GeoEnrichmentJob(collection, matcher, catalog_payload)

    original = [_deepcopy(doc) for doc in collection.documents]
    result = job.run(batch_size=5, dry_run=True)

    assert result.dry_run is True
    assert collection.documents == original


def test_job_allows_filtering_by_portal(
    matcher: CityMatcher, catalog_payload: dict[str, Any]
) -> None:
    collection = FakeCollection(
        [
            {
                "_id": 1,
                "portal_name": "Portal A",
                "url": "https://example.com/a",
                "title": "Campina Grande firma acordo",
                "content": "Campina Grande firmou parceria com São Paulo.",
            },
            {
                "_id": 2,
                "portal_name": "Portal B",
                "url": "https://example.com/b",
                "title": "São Paulo recebe missão",
                "content": "Delegação visita Campina Grande.",
            },
        ]
    )
    job = GeoEnrichmentJob(collection, matcher, catalog_payload)

    result = job.run(batch_size=5, portal="Portal B")

    assert result.scanned == 1
    assert result.enriched == 1

    portal_a = next(doc for doc in collection.documents if doc["portal_name"] == "Portal A")
    portal_b = next(doc for doc in collection.documents if doc["portal_name"] == "Portal B")

    assert "geo_enrichment" not in portal_a
    assert portal_b["geo-enriquecido"] is True


def test_job_skips_already_enriched_articles_by_default(
    matcher: CityMatcher, catalog_payload: dict[str, Any]
) -> None:
    collection = FakeCollection(
        [
            {
                "_id": 7,
                "portal_name": "Portal A",
                "url": "https://example.com/a",
                "title": "Campina Grande firma acordo",
                "content": "Campina Grande firmou parceria com São Paulo.",
                "geo-enriquecido": True,
                "geo_enriquecido": True,
                "geo_enrichment": {"mentioned_cities": ["old"]},
            }
        ]
    )
    job = GeoEnrichmentJob(collection, matcher, catalog_payload)

    result = job.run(batch_size=5)

    assert result.scanned == 0
    assert result.enriched == 0
    document = collection.documents[0]
    assert document["geo_enrichment"]["mentioned_cities"] == ["old"]


def test_job_can_reprocess_existing_articles(
    matcher: CityMatcher, catalog_payload: dict[str, Any]
) -> None:
    collection = FakeCollection(
        [
            {
                "_id": 10,
                "portal_name": "Portal A",
                "url": "https://example.com/a",
                "title": "Campina Grande firma acordo",
                "content": "Campina Grande firmou parceria com São Paulo.",
                "geo-enriquecido": True,
                "geo_enriquecido": True,
                "geo_enrichment": {"mentioned_cities": []},
            }
        ]
    )
    job = GeoEnrichmentJob(collection, matcher, catalog_payload)

    result = job.run(batch_size=5, reprocess_existing=True)

    assert result.scanned == 1
    assert result.enriched == 1
    document = collection.documents[0]
    assert document["geo_enrichment"]["mentioned_cities"]


def test_build_job_uses_catalog_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded_args: dict[str, Any] = {}

    class FakeCollection:
        pass

    class FakeCatalogCollection:
        def find_one(self, _criteria: dict[str, Any]) -> None:  # pragma: no cover
            return None

        def replace_one(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
            return None

    class FakeDatabase(dict):
        def __getitem__(self, name: str) -> Any:  # pragma: no cover - simples
            if name == "articles":
                return FakeCollection()
            if name == "city_catalog":
                return FakeCatalogCollection()
            raise KeyError(name)

    class FakeFactory:
        def get_database(self) -> FakeDatabase:
            return FakeDatabase()

    class FakeMatcher:
        def __init__(self, payload: Mapping[str, Any]) -> None:
            loaded_args["matcher_payload"] = payload

        def match(self, *_args: Any, **_kwargs: Any) -> list[Any]:  # pragma: no cover
            return []

    def fake_load_catalog(**kwargs: Any) -> Mapping[str, Any]:
        loaded_args.update(kwargs)
        return {"metadata": {"version": "test"}, "data": [{"name": "Cidade"}]}

    monkeypatch.setattr(
        "sentinela.services.publications.jobs.geo_enrichment_job.MongoClientFactory",
        FakeFactory,
    )
    monkeypatch.setattr(
        "sentinela.services.publications.jobs.geo_enrichment_job.CityMatcher",
        FakeMatcher,
    )
    monkeypatch.setattr(
        "sentinela.services.publications.jobs.geo_enrichment_job.load_city_catalog",
        fake_load_catalog,
    )

    job = build_geo_enrichment_job()

    assert "storage" in loaded_args
    assert loaded_args["storage"].__class__.__name__ == "MongoCityCatalogStorage"
    assert job._catalog_payload["metadata"]["version"] == "test"
