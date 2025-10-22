from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Iterable

import pytest

from sentinela.services.publications.city_matching import CityMatcher
from sentinela.services.publications.jobs.city_extraction_job import CityExtractionJob
from sentinela.services.publications.infrastructure import MongoArticleCitiesWriter


@dataclass
class _FakeCursor:
    _documents: list[dict[str, Any]]

    def sort(self, key: str, direction: int) -> "_FakeCursor":
        reverse = direction < 0
        self._documents.sort(key=lambda item: item.get(key), reverse=reverse)
        return self

    def limit(self, size: int) -> "_FakeCursor":
        if size and size > 0:
            self._documents = self._documents[:size]
        return self

    def __iter__(self) -> Iterable[dict[str, Any]]:
        return iter(self._documents)


class FakeCollection:
    def __init__(self, documents: list[dict[str, Any]] | None = None):
        self._documents = [doc.copy() for doc in documents or []]

    @property
    def documents(self) -> list[dict[str, Any]]:
        return self._documents

    def find(self, criteria: dict[str, Any]):
        matched: list[dict[str, Any]] = []
        for document in self._documents:
            if _matches(document, criteria):
                matched.append(document.copy())
        return _FakeCursor(matched)

    def update_many(self, criteria: dict[str, Any], update: dict[str, Any]):
        modified = 0
        for document in self._documents:
            if _matches(document, criteria):
                for field, value in update.get("$set", {}).items():
                    document[field] = _deepcopy(value)
                modified += 1
        return SimpleNamespace(modified_count=modified)


def _matches(document: dict[str, Any], criteria: dict[str, Any]) -> bool:
    if not criteria:
        return True
    for key, expected in criteria.items():
        if key == "_id" and isinstance(expected, dict):
            greater = expected.get("$gt")
            if greater is not None and not document.get("_id") > greater:
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
def matcher() -> CityMatcher:
    catalog = [
        {"ibge_id": "2504009", "name": "Campina Grande", "uf": "PB"},
        {"ibge_id": "3550308", "name": "São Paulo", "uf": "SP"},
        {"ibge_id": "3304557", "name": "Rio de Janeiro", "uf": "RJ"},
    ]
    return CityMatcher(catalog)


@pytest.fixture
def fake_collection() -> FakeCollection:
    return FakeCollection(
        [
            {
                "_id": 1,
                "portal_name": "Diário",
                "url": "https://example.com/a",
                "title": "Campina Grande firma acordo",
                "content": "Campina Grande receberá apoio de São Paulo e Rio de Janeiro.",
            },
            {
                "_id": 2,
                "portal_name": "Diário",
                "url": "https://example.com/b",
                "title": "Visita a Campina Grande",
                "content": "Delegação chega a Campina Grande vindo de São Paulo.",
            },
        ]
    )


def _build_job(collection: FakeCollection, matcher: CityMatcher) -> CityExtractionJob:
    writer = MongoArticleCitiesWriter(collection)  # type: ignore[arg-type]
    return CityExtractionJob(collection, writer, matcher)


def test_job_updates_articles_and_persists_metadata(fake_collection: FakeCollection, matcher: CityMatcher) -> None:
    job = _build_job(fake_collection, matcher)

    result = job.run(batch_size=1)

    assert result.scanned == 2
    assert result.processed == 2
    assert result.updated == 2
    assert result.skipped == 0
    assert result.ambiguous == 0
    assert result.elapsed_ms_total >= 0
    assert result.errors == ()

    first = next(doc for doc in fake_collection.documents if doc["url"] == "https://example.com/a")
    cities = first["cities"]
    assert {city["ibge_id"] for city in cities} == {"2504009", "3550308", "3304557"}
    campina = next(city for city in cities if city["ibge_id"] == "2504009")
    assert campina["name"] == "Campina Grande"
    assert campina["nome"] == "Campina Grande"
    assert campina["occurrences"] == 2
    assert set(campina["sources"]) == {"automaton"}

    metadata = first["cities_extraction"]
    assert metadata["matches_count"] == len(metadata["payload"]["matches"])
    assert metadata["payload"]["matches"]
    assert "hash" in metadata


def test_job_is_idempotent_when_payload_hash_matches(fake_collection: FakeCollection, matcher: CityMatcher) -> None:
    job = _build_job(fake_collection, matcher)
    job.run(batch_size=10)

    result = job.run(batch_size=10)

    assert result.scanned == 2
    assert result.processed == 2
    assert result.updated == 0
    assert result.skipped == 2
    assert result.ambiguous == 0
    assert result.errors == ()


def test_job_force_flag_updates_even_with_same_hash(fake_collection: FakeCollection, matcher: CityMatcher) -> None:
    job = _build_job(fake_collection, matcher)
    job.run(batch_size=10)

    first_metadata = next(doc for doc in fake_collection.documents if doc["_id"] == 1)["cities_extraction"]["ts"]

    result = job.run(batch_size=10, force=True)

    assert result.updated == 2
    assert result.ambiguous == 0
    updated_metadata = next(doc for doc in fake_collection.documents if doc["_id"] == 1)["cities_extraction"]["ts"]
    assert updated_metadata != first_metadata


def test_job_only_missing_skips_documents_with_hash(fake_collection: FakeCollection, matcher: CityMatcher) -> None:
    job = _build_job(fake_collection, matcher)
    job.run(batch_size=10)

    # Documento já possui hash, então deve ser ignorado quando only_missing=True
    result = job.run(batch_size=10, only_missing=True)

    assert result.processed == 0
    assert result.scanned == 2
    assert result.updated == 0
    assert result.skipped == 2
    assert result.ambiguous == 0


def test_job_dry_run_does_not_modify_documents(fake_collection: FakeCollection, matcher: CityMatcher) -> None:
    job = _build_job(fake_collection, matcher)

    result = job.run(batch_size=10, dry_run=True)

    assert result.updated == 2
    assert result.ambiguous == 0
    for document in fake_collection.documents:
        assert "cities" not in document
        assert "cities_extraction" not in document

    assert result.dry_run is True


def test_job_summary_format_includes_required_fields(matcher: CityMatcher) -> None:
    collection = FakeCollection(
        [
            {
                "_id": 10,
                "portal_name": "Especial",
                "url": "https://example.com/special",
                "title": "Evento em Cidade Fantasia",
                "content": "Cidade Fantasia recebe delegação de São Paulo.",
            }
        ]
    )
    job = _build_job(collection, matcher)

    result = job.run(batch_size=5)

    summary = result.to_summary()

    assert summary == {
        "processed": result.processed,
        "updated": result.updated,
        "skipped": result.skipped,
        "ambiguous": result.ambiguous,
        "elapsed_ms_total": result.elapsed_ms_total,
    }
    assert result.ambiguous == 0


def test_job_force_and_only_missing_flags_with_fake_collection(
    fake_collection: FakeCollection, matcher: CityMatcher
) -> None:
    job = _build_job(fake_collection, matcher)
    job.run(batch_size=5)

    # Mesmo com force=True, only_missing deve manter os documentos com hash existentes ignorados.
    result = job.run(batch_size=5, force=True, only_missing=True)

    assert result.scanned == 2
    assert result.processed == 0
    assert result.updated == 0
    assert result.skipped == 2
    assert result.ambiguous == 0


def test_job_allows_filtering_by_portal(matcher: CityMatcher) -> None:
    collection = FakeCollection(
        [
            {
                "_id": 1,
                "portal_name": "Portal A",
                "url": "https://example.com/a",
                "title": "Evento em São Paulo",
                "content": "São Paulo recebe delegação.",
            },
            {
                "_id": 2,
                "portal_name": "Portal B",
                "url": "https://example.com/b",
                "title": "Campina Grande anuncia projeto",
                "content": "Campina Grande firma acordo.",
            },
        ]
    )
    job = _build_job(collection, matcher)

    result = job.run(batch_size=5, portal="Portal B")

    assert result.scanned == 1
    assert result.updated == 1
    portal_a = next(doc for doc in collection.documents if doc["portal_name"] == "Portal A")
    portal_b = next(doc for doc in collection.documents if doc["portal_name"] == "Portal B")

    assert "cities" not in portal_a
    assert portal_b.get("cities")
