"""FastAPI application exposing article collection endpoints."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import date

import uvicorn
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from sentinela.application.services import StatusPublisher
from sentinela.domain.entities import Article
from sentinela.services.news import NewsContainer, build_news_container


class CollectRequest(BaseModel):
    """Parameters to trigger article collection."""

    portal: str
    start_date: date
    end_date: date | None = None


class ArticleResponse(BaseModel):
    """Representation of an article returned by the API."""

    portal: str
    title: str
    url: str
    content: str
    published_at: str
    summary: str | None = None


class CollectResponse(BaseModel):
    """Response returned after collecting articles."""

    portal: str
    collected: int
    articles: list[ArticleResponse]


def configure_cors(app: FastAPI) -> None:
    """Apply the default CORS configuration used by the services."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def include_routes(app: FastAPI, container: NewsContainer, *, prefix: str = "") -> None:
    """Register news collection routes on a FastAPI application."""

    router = APIRouter(prefix=prefix, tags=["Coleta de Notícias"])

    def map_article_response(article: Article) -> ArticleResponse:
        return ArticleResponse(
            portal=article.portal_name,
            title=article.title,
            url=article.url,
            content=article.content,
            published_at=article.published_at.isoformat(),
            summary=article.summary,
        )

    def handle_value_error(exc: ValueError) -> HTTPException:
        detail = str(exc)
        status = 404 if "not found" in detail.lower() else 400
        return HTTPException(status_code=status, detail=detail)

    @router.post("/collect", response_model=CollectResponse)
    def collect_articles(request: CollectRequest) -> CollectResponse:
        try:
            end_date = request.end_date or request.start_date
            articles = container.collector_service.collect(
                request.portal, request.start_date, end_date
            )
        except ValueError as exc:
            raise handle_value_error(exc)

        return CollectResponse(
            portal=request.portal,
            collected=len(articles),
            articles=[map_article_response(article) for article in articles],
        )

    @router.post("/collect/stream")
    async def collect_articles_stream(
        request: Request, payload: CollectRequest
    ) -> EventSourceResponse:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()

        def push(event: str, data: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, {"event": event, "data": data})

        def finish() -> None:
            loop.call_soon_threadsafe(queue.put_nowait, None)

        class QueueStatusPublisher(StatusPublisher):
            def publish(self, message: str) -> None:  # noqa: D401 - simple adapter
                push("log", message)

        async def run_collection() -> None:
            try:
                end_date = payload.end_date or payload.start_date
                articles = await loop.run_in_executor(
                    None,
                    lambda: container.collector_service.collect(
                        payload.portal,
                        payload.start_date,
                        end_date,
                        status_publisher=QueueStatusPublisher(),
                    ),
                )
                response = CollectResponse(
                    portal=payload.portal,
                    collected=len(articles),
                    articles=[map_article_response(article) for article in articles],
                )
                push("summary", json.dumps(response.model_dump()))
            except ValueError as exc:
                push("error", str(exc))
            except Exception:  # pragma: no cover - defensive path
                push(
                    "error",
                    "Erro inesperado durante a coleta de artigos. Verifique os logs do servidor.",
                )
            finally:
                finish()

        task = asyncio.create_task(run_collection())

        async def event_generator():
            try:
                while True:
                    if await request.is_disconnected():
                        task.cancel()
                        break
                    event = await queue.get()
                    if event is None:
                        break
                    yield event
            finally:
                if not task.done():
                    task.cancel()

        return EventSourceResponse(event_generator())

    app.include_router(router)


def create_app() -> FastAPI:
    """Create the FastAPI application with news collection routes."""

    container = build_news_container()
    app = FastAPI(
        title="Sentinela News API",
        version="1.0.0",
        description="Coleta e monitoramento de notícias em portais cadastrados.",
    )
    configure_cors(app)
    include_routes(app, container)
    return app


def run() -> None:
    """Run the news API using Uvicorn."""

    load_dotenv()
    uvicorn.run(
        "sentinela.services.news.api:create_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        factory=True,
    )


__all__ = [
    "ArticleResponse",
    "CollectRequest",
    "CollectResponse",
    "create_app",
    "configure_cors",
    "include_routes",
    "run",
]
