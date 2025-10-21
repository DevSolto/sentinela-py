from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sentinela.domain import Article, CityMention
from sentinela.extraction import CityGazetteer, CityRecord, NewsDocument
from sentinela.extraction.models import EntitySpan
from sentinela.services.extraction import (
    ExtractionConfig,
    build_extraction_container,
    create_app,
    notify_news_ready,
)
from sentinela.services.extraction.adapters import ExtractionResultStore, PendingNewsQueue
from sentinela.services.publications import PublicationsContainer
from sentinela.services.publications.api import include_routes
from sentinela.services.publications.application import ArticleQueryService
from sentinela.services.publications.domain import Article as PublicationsArticle
from sentinela.services.publications.infrastructure import (
    MongoArticleCitiesWriter,
    MongoArticleReadRepository,
    MongoArticleRepository,
)


_SAMPLE_TEXT = "Maria Silva esteve em Florianópolis-SC acompanhada da comitiva."


class FakeNER:
    def __init__(self, spans: list[EntitySpan]):
        self._spans = spans

    def analyze(self, text: str):
        for span in self._spans:
            yield span


class FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]):
        self._documents = documents

    def sort(self, key: str, direction: int):
        reverse = direction < 0
        self._documents.sort(key=lambda doc: doc.get(key), reverse=reverse)
        return self

    def __iter__(self):
        return iter(self._documents)


class FakeCollection:
    def __init__(self):
        self._documents: list[dict[str, Any]] = []

    @property
    def documents(self) -> list[dict[str, Any]]:
        return self._documents

    def create_index(self, *args, **kwargs) -> None:
        return None

    def insert_many(self, documents: list[dict[str, Any]], ordered: bool = False):
        for document in documents:
            self._documents.append(document.copy())

    def count_documents(self, criteria: dict[str, Any], limit: int = 0) -> int:
        count = sum(1 for doc in self._documents if _matches(doc, criteria))
        if limit == 1:
            return 1 if count else 0
        return count

    def find(self, criteria: dict[str, Any]):
        matched = [doc.copy() for doc in self._documents if _matches(doc, criteria)]
        return FakeCursor(matched)

    def update_many(self, criteria: dict[str, Any], update: dict[str, Any]):
        modified = 0
        for document in self._documents:
            if _matches(document, criteria):
                for key, value in update.get("$set", {}).items():
                    document[key] = value
                modified += 1
        return SimpleNamespace(modified_count=modified)


def _align_datetime(reference: datetime | None, value: datetime | None) -> tuple[datetime | None, datetime | None]:
    if reference is None or value is None:
        return reference, value
    if reference.tzinfo and value.tzinfo is None:
        value = value.replace(tzinfo=reference.tzinfo)
    elif value.tzinfo and reference.tzinfo is None:
        reference = reference.replace(tzinfo=value.tzinfo)
    return reference, value


def _matches(document: dict[str, Any], criteria: dict[str, Any]) -> bool:
    if not criteria:
        return True
    for key, expected in criteria.items():
        if key == "$and":
            clauses = expected if isinstance(expected, list) else [expected]
            if not all(_matches(document, clause) for clause in clauses):
                return False
            continue
        if key == "$or":
            clauses = expected if isinstance(expected, list) else [expected]
            if not any(_matches(document, clause) for clause in clauses):
                return False
            continue
        if key == "published_at" and isinstance(expected, dict):
            value = document.get("published_at")
            lower = expected.get("$gte")
            upper = expected.get("$lte")
            if isinstance(lower, datetime) and isinstance(value, datetime):
                lower, value = _align_datetime(lower, value)
            if lower and value < lower:
                return False
            if isinstance(upper, datetime) and isinstance(value, datetime):
                upper, value = _align_datetime(upper, value)
            if upper and value > upper:
                return False
            continue
        if key == "cities":
            if not _match_cities(document.get("cities"), expected):
                return False
            continue
        if "." in key:
            if not _match_dotted(document, key.split("."), expected):
                return False
            continue
        value = document.get(key)
        if isinstance(expected, dict):
            if not isinstance(value, dict) or not _matches(value, expected):
                return False
            continue
        if value != expected:
            return False
    return True


def _match_dotted(document: Any, parts: list[str], expected: Any) -> bool:
    if not parts:
        return _compare_value(document, expected)
    head, *tail = parts
    if isinstance(document, list):
        return any(_match_dotted(item, parts, expected) for item in document)
    if isinstance(document, dict):
        if head == "cities":
            return _match_city_path(document.get("cities"), tail, expected)
        return _match_dotted(document.get(head), tail, expected)
    return False


def _match_city_path(value: Any, parts: list[str], expected: Any) -> bool:
    if not parts:
        return _compare_value(value, expected)
    if isinstance(value, list):
        return any(_match_city_path(item, parts, expected) for item in value)
    if not isinstance(value, dict):
        return False
    head, *tail = parts
    if head == "identifier":
        candidates = [
            value.get("identifier"),
            value.get("city_id"),
            value.get("label"),
            value.get("name"),
        ]
        if not tail:
            return any(_compare_value(candidate, expected) for candidate in candidates)
        return any(
            _match_city_path(candidate, tail, expected) for candidate in candidates if candidate
        )
    return _match_city_path(value.get(head), tail, expected)


def _match_cities(value: Any, expected: Any) -> bool:
    if not value:
        return False
    if isinstance(value, list):
        return any(_match_cities(item, expected) for item in value)
    if isinstance(value, dict):
        candidates = [
            value.get("identifier"),
            value.get("city_id"),
            value.get("label"),
            value.get("name"),
        ]
        return any(_compare_value(candidate, expected) for candidate in candidates)
    return _compare_value(value, expected)


def _compare_value(value: Any, expected: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return any(_compare_value(item, expected) for item in value)
    return str(value) == str(expected)


def _build_container(article_cities_writer=None) -> tuple:
    queue = PendingNewsQueue()
    store = ExtractionResultStore()
    city = CityRecord(id="4205407", name="Florianópolis", uf="SC", alt_names=("Floripa",))
    gazetteer = CityGazetteer([city])
    spans = [
        EntitySpan(label="PERSON", text="Maria Silva", start=0, end=11, score=0.9, method="test"),
        EntitySpan(
            label="LOC",
            text="Florianópolis",
            start=_SAMPLE_TEXT.index("Florianópolis"),
            end=_SAMPLE_TEXT.index("Florianópolis") + len("Florianópolis"),
            score=0.8,
            method="test",
        ),
    ]
    config = ExtractionConfig(
        ner_version="ner-1",
        gazetteer_version="gaz-1",
        batch_size=5,
        ner_engine=FakeNER(spans),
        gazetteer=gazetteer,
        queue=queue,
        result_store=store,
    )
    config.article_cities_writer = article_cities_writer
    container = build_extraction_container(config)
    return container, queue, store


def _sample_document() -> NewsDocument:
    return NewsDocument(
        url="https://example.com/news/1",
        title="Maria Silva visitou Florianópolis",
        body=_SAMPLE_TEXT,
        published_at=datetime(2024, 5, 12, tzinfo=timezone.utc),
        source="Diário", 
    )


def test_queue_processing_records_results():
    container, queue, store = _build_container()
    document = _sample_document()
    queue.enqueue(document)

    result = container.service.process_next_batch()

    assert result.processed == 1
    enriched = store.get(document.url)
    assert enriched is not None
    assert enriched.ner_version == "ner-1"
    assert enriched.people and enriched.people[0].canonical_name == "Maria Silva"
    assert enriched.cities and enriched.cities[0].city_id == "4205407"


def test_extraction_api_flow_and_publications_endpoint():
    container, queue, store = _build_container()
    config = container.config
    config.queue = queue
    config.result_store = store
    config.ner_engine = container.ner_engine
    config.gazetteer = container.gazetteer

    app = create_app(config)
    client = TestClient(app)

    payload = {
        "url": "https://example.com/news/1",
        "title": "Maria Silva visitou Florianópolis",
        "content": _SAMPLE_TEXT,
        "published_at": "2024-05-12T00:00:00+00:00",
        "source": "Diário",
    }
    enqueue_response = client.post("/enqueue", json=payload)
    assert enqueue_response.status_code == 200
    assert enqueue_response.json() == {"queued": 1}

    process_response = client.post("/process")
    assert process_response.status_code == 200
    body = process_response.json()
    assert body["processed"] == 1
    assert body["errors"] == []

    encoded_url = quote(payload["url"], safe="")
    result_response = client.get(f"/results/{encoded_url}")
    assert result_response.status_code == 200
    data = result_response.json()
    assert data["people"][0]["canonical_name"] == "Maria Silva"
    assert data["cities"][0]["city_id"] == "4205407"

    article = Article(
        portal_name="Diário",
        title=payload["title"],
        url=payload["url"],
        content=payload["content"],
        summary=None,
        published_at=datetime(2024, 5, 12, tzinfo=timezone.utc),
        cities=tuple(),
    )
    notify_news_ready([article])
    assert queue.queued_count() >= 1

    publications_app = FastAPI()
    dummy_container = PublicationsContainer(
        article_repository=SimpleNamespace(),
        query_service=SimpleNamespace(list_articles=lambda *args, **kwargs: []),
        extraction_store=store,
        article_cities_writer=SimpleNamespace(
            update_article_cities=lambda *args, **kwargs: None
        ),
    )
    include_routes(publications_app, dummy_container)
    publications_client = TestClient(publications_app)
    enriched_response = publications_client.get("/enriched/articles")
    assert enriched_response.status_code == 200
    enriched_body = enriched_response.json()
    assert enriched_body and enriched_body[0]["url"] == payload["url"]

    enriched_detail = publications_client.get(f"/enriched/articles/{encoded_url}")
    assert enriched_detail.status_code == 200


def test_entity_extraction_updates_article_cities_in_mongo_collection():
    collection = FakeCollection()
    repository = MongoArticleRepository(collection)
    writer = MongoArticleCitiesWriter(collection)

    article = PublicationsArticle(
        portal_name="Diário",
        title="Maria Silva visitou Florianópolis",
        url="https://example.com/news/1",
        content=_SAMPLE_TEXT,
        published_at=datetime(2024, 5, 12, tzinfo=timezone.utc),
        cities=(),
    )
    repository.save_many([article])

    container, queue, _ = _build_container(article_cities_writer=writer)
    document = _sample_document()
    queue.enqueue(document)

    result = container.service.process_next_batch()

    assert result.processed == 1
    stored = collection.documents[0]
    assert stored["url"] == article.url
    assert any(city.get("identifier") == "4205407" for city in stored["cities"])


def test_publications_api_filters_articles_by_city_after_extraction():
    collection = FakeCollection()
    repository = MongoArticleRepository(collection)
    writer = MongoArticleCitiesWriter(collection)
    reader = MongoArticleReadRepository(collection)
    query_service = ArticleQueryService(reader)

    base_published_at = datetime(2024, 5, 12, tzinfo=timezone.utc)
    tracked_article = PublicationsArticle(
        portal_name="Diário",
        title="Maria Silva visitou Florianópolis",
        url="https://example.com/news/1",
        content=_SAMPLE_TEXT,
        published_at=base_published_at,
        cities=(),
    )
    other_article = PublicationsArticle(
        portal_name="Diário",
        title="Outra notícia",
        url="https://example.com/news/2",
        content="Conteúdo diverso",
        published_at=base_published_at.replace(day=13),
        cities=(CityMention(identifier="3550308", city_id="3550308"),),
    )
    repository.save_many([tracked_article, other_article])

    container, queue, store = _build_container(article_cities_writer=writer)
    queue.enqueue(_sample_document())
    container.service.process_next_batch()

    publications_app = FastAPI()
    container_deps = PublicationsContainer(
        article_repository=repository,
        query_service=query_service,
        extraction_store=store,
        article_cities_writer=writer,
        article_reader=reader,
    )
    include_routes(publications_app, container_deps)
    client = TestClient(publications_app)

    response_filtered = client.get(
        "/articles",
        params={
            "portal": "Diário",
            "start_date": "2024-05-10",
            "end_date": "2024-05-20",
            "city": "4205407",
        },
    )
    assert response_filtered.status_code == 200
    filtered_body = response_filtered.json()
    assert [article["url"] for article in filtered_body] == [tracked_article.url]
    assert any(
        city["identifier"] == "4205407" for city in filtered_body[0]["cities"]
    )

    response_all = client.get(
        "/articles",
        params={
            "portal": "Diário",
            "start_date": "2024-05-10",
            "end_date": "2024-05-20",
        },
    )
    assert response_all.status_code == 200
    all_urls = {article["url"] for article in response_all.json()}
    assert all_urls == {tracked_article.url, other_article.url}
