"""FastAPI/worker application for the entity extraction microservice."""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import import_module
from typing import Any, Iterable

import uvicorn
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sentinela.domain import Article
from sentinela.extraction import CityGazetteer, CityRecord, EntityExtractionService, NewsDocument
from sentinela.extraction.ner import NEREngine
from sentinela.extraction.models import ExtractionResultWriter, NewsRepository

from .adapters import (
    EnrichedArticleResult,
    ExtractionResultStore,
    ExtractionResultStoreWriter,
    PendingNewsQueue,
    QueueNewsRepository,
)


_DEFAULT_QUEUE: PendingNewsQueue | None = None
_DEFAULT_RESULT_STORE: ExtractionResultStore | None = None


@dataclass
class ExtractionConfig:
    """Configuration required to bootstrap the extraction service."""

    ner_version: str
    gazetteer_version: str
    batch_size: int = 500
    ner_engine_factory: str | None = None
    ner_engine_settings: dict[str, Any] = field(default_factory=dict)
    gazetteer_path: str | None = None
    news_backend: str = "queue"
    publications_api_url: str | None = None
    result_backend: str = "memory"
    ner_engine: NEREngine | None = None
    gazetteer: CityGazetteer | None = None
    news_repository: NewsRepository | None = None
    result_writer: ExtractionResultWriter | None = None
    queue: PendingNewsQueue | None = None
    result_store: ExtractionResultStore | None = None

    @classmethod
    def from_env(cls) -> "ExtractionConfig":
        """Build a configuration instance from environment variables."""

        def _json_env(name: str) -> dict[str, Any]:
            raw = os.getenv(name)
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise RuntimeError(f"Invalid JSON in environment variable {name!r}: {raw}") from exc

        return cls(
            ner_version=os.getenv("NER_VERSION", "dev"),
            gazetteer_version=os.getenv("GAZETTEER_VERSION", "dev"),
            batch_size=int(os.getenv("EXTRACTION_BATCH_SIZE", "500")),
            ner_engine_factory=os.getenv(
                "EXTRACTION_NER_FACTORY",
                "sentinela.services.extraction.app:create_default_ner_engine",
            ),
            ner_engine_settings=_json_env("EXTRACTION_NER_SETTINGS"),
            gazetteer_path=os.getenv("EXTRACTION_GAZETTEER_PATH"),
            news_backend=os.getenv("EXTRACTION_NEWS_BACKEND", "queue"),
            publications_api_url=os.getenv("PUBLICATIONS_API_URL"),
            result_backend=os.getenv("EXTRACTION_RESULT_BACKEND", "memory"),
        )


@dataclass
class ExtractionContainer:
    """Resolved dependencies for the extraction service."""

    config: ExtractionConfig
    service: EntityExtractionService
    news_repository: NewsRepository
    result_writer: ExtractionResultWriter
    ner_engine: NEREngine
    gazetteer: CityGazetteer
    queue: PendingNewsQueue | None
    result_store: ExtractionResultStore


def get_default_pending_queue() -> PendingNewsQueue:
    """Return a shared in-memory queue instance."""

    global _DEFAULT_QUEUE
    if _DEFAULT_QUEUE is None:
        _DEFAULT_QUEUE = PendingNewsQueue()
    return _DEFAULT_QUEUE


def set_default_pending_queue(queue: PendingNewsQueue) -> None:
    global _DEFAULT_QUEUE
    _DEFAULT_QUEUE = queue


def get_default_result_store() -> ExtractionResultStore:
    """Return the global extraction result store."""

    global _DEFAULT_RESULT_STORE
    if _DEFAULT_RESULT_STORE is None:
        _DEFAULT_RESULT_STORE = ExtractionResultStore()
    return _DEFAULT_RESULT_STORE


def set_default_result_store(store: ExtractionResultStore) -> None:
    global _DEFAULT_RESULT_STORE
    _DEFAULT_RESULT_STORE = store


def build_extraction_container(config: ExtractionConfig) -> ExtractionContainer:
    """Instantiate all dependencies required by the extraction service."""

    ner_engine = config.ner_engine or _load_ner_engine(
        config.ner_engine_factory, config.ner_engine_settings
    )
    gazetteer = config.gazetteer or _load_gazetteer(config.gazetteer_path)

    if config.news_repository is not None:
        news_repository = config.news_repository
        queue = config.queue
    elif config.news_backend == "queue":
        queue = config.queue if config.queue is not None else get_default_pending_queue()
        news_repository = QueueNewsRepository(queue)
    else:
        raise ValueError(
            "Unsupported news backend: {backend}".format(backend=config.news_backend)
        )

    if config.result_writer is not None:
        result_writer = config.result_writer
        store = config.result_store or get_default_result_store()
    elif config.result_backend == "memory":
        store = config.result_store if config.result_store is not None else get_default_result_store()
        result_writer = ExtractionResultStoreWriter(
            store,
            ner_version=config.ner_version,
            gazetteer_version=config.gazetteer_version,
        )
    else:
        raise ValueError(
            "Unsupported result backend: {backend}".format(backend=config.result_backend)
        )

    config.queue = queue
    config.result_store = store

    set_default_pending_queue(queue)
    set_default_result_store(store)

    service = EntityExtractionService(
        news_repository=news_repository,
        result_writer=result_writer,
        ner_engine=ner_engine,
        gazetteer=gazetteer,
        ner_version=config.ner_version,
        gazetteer_version=config.gazetteer_version,
        batch_size=config.batch_size,
    )

    return ExtractionContainer(
        config=config,
        service=service,
        news_repository=news_repository,
        result_writer=result_writer,
        ner_engine=ner_engine,
        gazetteer=gazetteer,
        queue=queue,
        result_store=store,
    )


def notify_news_ready(articles: Iterable[Article]) -> int:
    """Publish newly collected articles to the extraction queue."""

    queue = get_default_pending_queue()
    total = 0
    for article in articles:
        published_at = article.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        queue.enqueue(
            NewsDocument(
                url=article.url,
                title=article.title,
                body=article.content,
                published_at=published_at,
                source=article.portal_name,
            )
        )
        total += 1
    return total


class NewsPayload(BaseModel):
    """Incoming representation of a pending news document."""

    url: str
    title: str | None = None
    body: str | None = None
    content: str | None = None
    published_at: datetime | None = None
    source: str | None = None

    def to_document(self) -> NewsDocument:
        body = self.body if self.body is not None else (self.content or "")
        published_at = self.published_at or datetime.now(timezone.utc)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        return NewsDocument(
            url=self.url,
            title=self.title or "",
            body=body,
            published_at=published_at,
            source=self.source,
        )


class BatchProcessRequest(BaseModel):
    """Optional overrides for batch processing."""

    batch_size: int | None = Field(default=None, ge=1, le=5000)


class BatchProcessResponse(BaseModel):
    processed: int
    skipped_empty: int
    errors: list[dict[str, str]]


class CandidateResponse(BaseModel):
    city_id: str
    name: str
    uf: str
    score: float


class PersonOccurrenceResponse(BaseModel):
    person_id: str
    canonical_name: str
    surface: str
    start: int
    end: int
    sentence: str
    method: str
    confidence: float

    @classmethod
    def from_dataclass(cls, occurrence) -> "PersonOccurrenceResponse":
        return cls(
            person_id=occurrence.person_id,
            canonical_name=occurrence.canonical_name,
            surface=occurrence.surface,
            start=occurrence.start,
            end=occurrence.end,
            sentence=occurrence.sentence,
            method=occurrence.method,
            confidence=occurrence.confidence,
        )


class CityOccurrenceResponse(BaseModel):
    city_id: str | None
    surface: str
    start: int
    end: int
    sentence: str
    status: str
    uf_surface: str | None
    method: str
    confidence: float
    candidates: list[CandidateResponse]

    @classmethod
    def from_dataclass(cls, occurrence) -> "CityOccurrenceResponse":
        return cls(
            city_id=occurrence.city_id,
            surface=occurrence.surface,
            start=occurrence.start,
            end=occurrence.end,
            sentence=occurrence.sentence,
            status=occurrence.status,
            uf_surface=occurrence.uf_surface,
            method=occurrence.method,
            confidence=occurrence.confidence,
            candidates=[
                CandidateResponse(
                    city_id=candidate.city_id,
                    name=candidate.name,
                    uf=candidate.uf,
                    score=candidate.score,
                )
                for candidate in occurrence.candidates
            ],
        )


class EnrichedArticleResponse(BaseModel):
    url: str
    ner_version: str
    gazetteer_version: str
    updated_at: datetime
    people: list[PersonOccurrenceResponse]
    cities: list[CityOccurrenceResponse]

    @classmethod
    def from_store(cls, result: EnrichedArticleResult) -> "EnrichedArticleResponse":
        return cls(
            url=result.url,
            ner_version=result.ner_version,
            gazetteer_version=result.gazetteer_version,
            updated_at=result.updated_at,
            people=[PersonOccurrenceResponse.from_dataclass(item) for item in result.people],
            cities=[CityOccurrenceResponse.from_dataclass(item) for item in result.cities],
        )


def include_routes(app: FastAPI, container: ExtractionContainer, *, prefix: str = "") -> None:
    """Register FastAPI routes exposing the extraction capabilities."""

    router = APIRouter(prefix=prefix, tags=["Extraction"])

    @router.get("/healthz")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/enqueue")
    def enqueue_news(payload: list[NewsPayload] | NewsPayload) -> dict[str, Any]:
        if container.queue is None:
            raise HTTPException(
                status_code=400,
                detail="Queue backend not configured on this instance.",
            )
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            container.queue.enqueue(item.to_document())
        return {"queued": len(items)}

    @router.post("/process", response_model=BatchProcessResponse)
    def trigger_processing(payload: BatchProcessRequest | None = None) -> BatchProcessResponse:
        if payload and payload.batch_size and payload.batch_size != container.config.batch_size:
            container.config.batch_size = payload.batch_size
            container.service = EntityExtractionService(
                news_repository=container.news_repository,
                result_writer=container.result_writer,
                ner_engine=container.ner_engine,
                gazetteer=container.gazetteer,
                ner_version=container.config.ner_version,
                gazetteer_version=container.config.gazetteer_version,
                batch_size=payload.batch_size,
            )
        result = container.service.process_next_batch()
        return BatchProcessResponse(
            processed=result.processed,
            skipped_empty=result.skipped_empty,
            errors=[{"url": url, "message": message} for url, message in result.errors],
        )

    @router.get("/results", response_model=list[EnrichedArticleResponse])
    def list_results() -> list[EnrichedArticleResponse]:
        return [EnrichedArticleResponse.from_store(result) for result in container.result_store.list()]

    @router.get("/results/{url:path}", response_model=EnrichedArticleResponse)
    def get_result(url: str) -> EnrichedArticleResponse:
        result = container.result_store.get(url)
        if not result:
            raise HTTPException(status_code=404, detail="Resultado não encontrado")
        return EnrichedArticleResponse.from_store(result)

    if container.queue is not None:
        @router.get("/queue", response_model=dict)
        def queue_stats() -> dict[str, int]:
            return {
                "queued": container.queue.queued_count(),
                "inflight": container.queue.inflight_count(),
            }

    app.include_router(router)


def create_app(config: ExtractionConfig | None = None) -> FastAPI:
    """Create a FastAPI application exposing extraction endpoints."""

    config = config or ExtractionConfig.from_env()
    container = build_extraction_container(config)

    app = FastAPI(
        title="Sentinela Extraction API",
        version="1.0.0",
        description="Processamento de entidades (pessoas e cidades) em notícias coletadas.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    include_routes(app, container)
    app.state.container = container
    return app


def create_default_ner_engine(**_: Any) -> NEREngine:
    """Fallback NER engine that does not yield any entities."""

    class NoOpNER(NEREngine):
        def analyze(self, text: str) -> Iterable[Any]:  # pragma: no cover - simple default
            return []

    return NoOpNER()


def run_api() -> None:
    """Run the extraction API with uvicorn."""

    load_dotenv()
    uvicorn.run(
        "sentinela.services.extraction.app:create_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8002")),
        factory=True,
    )


def run_worker() -> None:
    """Continuously process pending batches using the configured backend."""

    load_dotenv()
    log = logging.getLogger("sentinela.extraction.worker")
    interval = int(os.getenv("EXTRACTION_WORKER_INTERVAL", "60"))
    config = ExtractionConfig.from_env()
    container = build_extraction_container(config)

    log.info(
        "Iniciando worker de extração (batch_size=%s, ner_version=%s, gazetteer_version=%s)",
        config.batch_size,
        config.ner_version,
        config.gazetteer_version,
    )

    try:
        while True:
            result = container.service.process_next_batch()
            log.info(
                "Lote processado: %s notícias, %s vazias, %s erros",
                result.processed,
                result.skipped_empty,
                len(result.errors),
            )
            if result.errors:
                for url, message in result.errors:
                    log.error("Falha ao processar %s: %s", url, message)
            if interval <= 0:
                break
            time.sleep(interval)
    except KeyboardInterrupt:  # pragma: no cover - manual interruption
        log.info("Worker interrompido pelo usuário")


def _load_ner_engine(
    factory_path: str | None, settings: dict[str, Any]
) -> NEREngine:
    if factory_path is None:
        return create_default_ner_engine()
    module_name, _, attribute = factory_path.partition(":")
    if not attribute:
        raise ValueError(
            "EXTRACTION_NER_FACTORY deve seguir o formato 'modulo:atributo'"
        )
    module = import_module(module_name)
    factory = getattr(module, attribute)
    if callable(factory):
        return factory(**settings)
    return factory


def _load_gazetteer(path: str | None) -> CityGazetteer:
    if not path:
        return CityGazetteer([])
    with open(path, "r", encoding="utf-8") as stream:
        payload = json.load(stream)
    records: list[CityRecord] = []
    for item in payload:
        records.append(
            CityRecord(
                id=str(item["id"]),
                name=item["name"],
                uf=item.get("uf", ""),
                alt_names=tuple(item.get("alt_names", [])),
                latitude=item.get("latitude"),
                longitude=item.get("longitude"),
                country=item.get("country", "BR"),
            )
        )
    return CityGazetteer(records)


__all__ = [
    "BatchProcessRequest",
    "BatchProcessResponse",
    "ExtractionConfig",
    "ExtractionContainer",
    "EnrichedArticleResponse",
    "NewsPayload",
    "build_extraction_container",
    "create_app",
    "create_default_ner_engine",
    "get_default_pending_queue",
    "get_default_result_store",
    "include_routes",
    "notify_news_ready",
    "run_api",
    "run_worker",
]
