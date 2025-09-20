"""Tests for infrastructure components supporting the extraction service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sentinela.extraction.models import CityCandidate, CityOccurrence, PersonOccurrence
from sentinela.infrastructure.extraction import (
    MongoNewsRepository,
    PostgresExtractionResultWriter,
)


class FakeCursor:
    def __init__(self, fetch_results: list[Any] | None = None) -> None:
        self.fetch_results = list(fetch_results or [])
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self.executed_many: list[tuple[str, list[tuple[Any, ...]]]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> None:  # pragma: no cover - no cleanup required
        return None

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.executed.append((" ".join(query.split()), params))

    def executemany(
        self, query: str, params_seq: list[tuple[Any, ...]]
    ) -> None:
        self.executed_many.append((" ".join(query.split()), list(params_seq)))

    def fetchone(self) -> Any:
        if not self.fetch_results:
            return None
        return self.fetch_results.pop(0)


class FakeConnection:
    def __init__(self, fetch_results: list[Any] | None = None) -> None:
        self.cursor_instance = FakeCursor(fetch_results)
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1


class FakeMongoCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._documents = documents

    def sort(self, key: str, direction: int) -> "FakeMongoCursor":
        reverse = direction < 0
        self._documents.sort(key=lambda doc: doc.get(key), reverse=reverse)
        return self

    def limit(self, size: int) -> "FakeMongoCursor":
        self._documents = self._documents[:size]
        return self

    def __iter__(self):
        return iter(self._documents)


class FakeMongoCollection:
    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}

    def create_index(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def insert_many(self, documents: list[dict[str, Any]]) -> None:
        for document in documents:
            self._documents[str(document["_id"])] = dict(document)

    def find(self, query: dict[str, Any]) -> FakeMongoCursor:
        results = [
            dict(doc)
            for doc in self._documents.values()
            if _matches_query(query, doc)
        ]
        return FakeMongoCursor(results)

    def update_one(
        self,
        filter_doc: dict[str, Any],
        update: dict[str, Any],
        upsert: bool | None = None,
    ) -> None:
        key = str(filter_doc.get("_id"))
        doc = self._documents.get(key)
        if doc is None:
            if not upsert:
                return
            doc = {"_id": key}
            self._documents[key] = doc
        if "$set" in update:
            doc.update(update["$set"])
        if "$unset" in update:
            for field in update["$unset"].keys():
                doc.pop(field, None)
        if "$push" in update:
            for field, value in update["$push"].items():
                doc.setdefault(field, [])
                if isinstance(value, dict) and "$each" in value:
                    doc[field].extend(value["$each"])
                else:
                    doc[field].append(value)


def _matches_query(query: dict[str, Any], document: dict[str, Any]) -> bool:
    for key, condition in query.items():
        if key == "$or":
            if not any(_matches_query(sub, document) for sub in condition):
                return False
            continue
        value = document.get(key)
        if isinstance(condition, dict):
            for operator, expected in condition.items():
                if operator == "$exists":
                    exists = key in document
                    if bool(expected) != exists:
                        return False
                elif operator == "$ne":
                    if value == expected:
                        return False
                else:  # pragma: no cover - unused branch for now
                    raise NotImplementedError(f"Unsupported operator {operator}")
        else:
            if value != condition:
                return False
    return True


def test_mongo_news_repository_fetches_documents_by_versions() -> None:
    collection = FakeMongoCollection()
    collection.insert_many(
        [
            {
                "_id": "https://example.com/a",
                "titulo": "Um título",
                "corpo": "Corpo A",
                "data_publicacao": "2024-01-01T12:00:00",
                "ner_done": False,
            },
            {
                "_id": "https://example.com/b",
                "titulo": "Outro",
                "corpo": "Corpo B",
                "data_publicacao": datetime(2024, 1, 2, tzinfo=timezone.utc),
                "ner_done": True,
                "ner_version": "v0",
                "gazetteer_version": "g0",
            },
            {
                "_id": "https://example.com/c",
                "titulo": "Ignorado",
                "corpo": "Corpo C",
                "data_publicacao": datetime(2024, 1, 3, tzinfo=timezone.utc),
                "ner_done": True,
                "ner_version": "ner-v1",
                "gazetteer_version": "gaz-v1",
            },
        ]
    )

    repo = MongoNewsRepository(collection)
    pending = list(repo.fetch_pending(10, "ner-v1", "gaz-v1"))

    assert [doc.url for doc in pending] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    assert pending[0].title == "Um título"
    assert pending[0].body == "Corpo A"
    assert pending[0].published_at.tzinfo is not None


def test_mongo_news_repository_marks_processed_and_errors() -> None:
    collection = FakeMongoCollection()
    collection.insert_many(
        [
            {
                "_id": "https://example.com/a",
                "titulo": "Um título",
                "corpo": "Corpo A",
                "data_publicacao": "2024-01-01",
            }
        ]
    )
    repo = MongoNewsRepository(collection)
    now = datetime(2024, 1, 5, tzinfo=timezone.utc)

    repo.mark_processed("https://example.com/a", "ner-v1", "gaz-v1", now)
    stored = collection._documents["https://example.com/a"]
    assert stored["ner_done"] is True
    assert stored["ner_version"] == "ner-v1"
    assert stored["gazetteer_version"] == "gaz-v1"
    assert stored["processed_at"] == now
    assert "errors" not in stored

    repo.mark_error("https://example.com/a", "boom")
    stored = collection._documents["https://example.com/a"]
    assert stored["ner_done"] is False
    assert stored["last_error"] == "boom"
    assert stored["errors"][0]["message"] == "boom"


def test_postgres_writer_persists_person_and_occurrence() -> None:
    connection = FakeConnection(fetch_results=[("123",)])
    writer = PostgresExtractionResultWriter(connection)

    person_id = writer.ensure_person("João da Silva", {"Joao Silva"})
    assert person_id == "123"
    assert connection.cursor_instance.executed[0][0].startswith("INSERT INTO \"pessoas\"")
    assert connection.cursor_instance.executed_many[0][1] == [("123", "Joao Silva")]
    assert connection.commits == 1

    occurrence = PersonOccurrence(
        person_id=person_id,
        canonical_name="João da Silva",
        surface="João",
        start=10,
        end=14,
        sentence="João falou com Maria.",
        method="ner",
        confidence=0.92,
    )
    writer.record_person_occurrence("https://example.com/a", occurrence)
    assert connection.cursor_instance.executed[-1][0].startswith(
        "INSERT INTO \"noticias_pessoas\""
    )
    assert connection.commits == 2


def test_postgres_writer_records_city_occurrence_payload() -> None:
    connection = FakeConnection(fetch_results=[("1",)])
    writer = PostgresExtractionResultWriter(connection)
    occurrence = CityOccurrence(
        city_id="3550308",
        surface="São Paulo - SP",
        start=30,
        end=42,
        sentence="Prefeitura de São Paulo anunciou...",
        status="resolved",
        uf_surface="SP",
        method="ner",
        confidence=0.88,
        candidates=(
            CityCandidate(city_id="3550308", name="São Paulo", uf="SP", score=0.99),
        ),
    )

    writer.record_city_occurrence("https://example.com/a", occurrence)

    query, params = connection.cursor_instance.executed[-1]
    assert query.startswith("INSERT INTO \"noticias_cidades\"")
    assert "São Paulo" in params[2]
    payload = params[-1]
    assert "São Paulo" in payload
    assert "3550308" in payload
    assert connection.commits == 1

