from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sentinela.domain.entities import Article
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


_SAMPLE_TEXT = "Maria Silva esteve em Florianópolis-SC acompanhada da comitiva."


class FakeNER:
    def __init__(self, spans: list[EntitySpan]):
        self._spans = spans

    def analyze(self, text: str):
        for span in self._spans:
            yield span


def _build_container() -> tuple:
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
    )
    notify_news_ready([article])
    assert queue.queued_count() >= 1

    publications_app = FastAPI()
    dummy_container = PublicationsContainer(
        article_repository=SimpleNamespace(),
        query_service=SimpleNamespace(list_articles=lambda *args, **kwargs: []),
        extraction_store=store,
    )
    include_routes(publications_app, dummy_container)
    publications_client = TestClient(publications_app)
    enriched_response = publications_client.get("/enriched/articles")
    assert enriched_response.status_code == 200
    enriched_body = enriched_response.json()
    assert enriched_body and enriched_body[0]["url"] == payload["url"]

    enriched_detail = publications_client.get(f"/enriched/articles/{encoded_url}")
    assert enriched_detail.status_code == 200
