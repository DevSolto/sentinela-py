"""REST API entrypoint for Sentinela."""
from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Any, Dict, Iterable

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from sentinela.container import build_container
from sentinela.domain.entities import Article, Portal, PortalSelectors, Selector


class SelectorPayload(BaseModel):
    """Payload representation of a selector configuration."""

    query: str
    attribute: str | None = None

    def to_domain(self) -> Selector:
        return Selector(query=self.query, attribute=self.attribute)


class PortalSelectorsPayload(BaseModel):
    """Payload representation of selectors for a portal."""

    listing_article: SelectorPayload
    listing_title: SelectorPayload
    listing_url: SelectorPayload
    article_content: SelectorPayload
    article_date: SelectorPayload
    listing_summary: SelectorPayload | None = None

    def to_domain(self) -> PortalSelectors:
        return PortalSelectors(
            listing_article=self.listing_article.to_domain(),
            listing_title=self.listing_title.to_domain(),
            listing_url=self.listing_url.to_domain(),
            article_content=self.article_content.to_domain(),
            article_date=self.article_date.to_domain(),
            listing_summary=self.listing_summary.to_domain()
            if self.listing_summary
            else None,
        )


class PortalPayload(BaseModel):
    """Payload representation of a portal registration request."""

    name: str
    base_url: str
    listing_path_template: str
    selectors: PortalSelectorsPayload
    headers: Dict[str, str] = Field(default_factory=dict)
    date_format: str = "%Y-%m-%d"

    def to_domain(self) -> Portal:
        return Portal(
            name=self.name,
            base_url=self.base_url,
            listing_path_template=self.listing_path_template,
            selectors=self.selectors.to_domain(),
            headers=self.headers,
            date_format=self.date_format,
        )


class PortalResponse(BaseModel):
    """Representation of a portal returned by the API."""

    name: str
    base_url: str
    listing_path_template: str
    selectors: Dict[str, Any]
    headers: Dict[str, str]
    date_format: str


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


def create_app() -> FastAPI:
    """Create the FastAPI application with all routes configured."""

    container = build_container()
    app = FastAPI(title="Sentinela API", version="1.0.0")

    def map_portal_response(portal: Portal) -> PortalResponse:
        selectors = portal.selectors
        selectors_payload: Dict[str, Any] = {
            "listing_article": selector_to_dict(selectors.listing_article),
            "listing_title": selector_to_dict(selectors.listing_title),
            "listing_url": selector_to_dict(selectors.listing_url),
            "article_content": selector_to_dict(selectors.article_content),
            "article_date": selector_to_dict(selectors.article_date),
        }
        if selectors.listing_summary:
            selectors_payload["listing_summary"] = selector_to_dict(
                selectors.listing_summary
            )
        return PortalResponse(
            name=portal.name,
            base_url=portal.base_url,
            listing_path_template=portal.listing_path_template,
            selectors=selectors_payload,
            headers=portal.headers,
            date_format=portal.date_format,
        )

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

    @app.post("/portals", response_model=PortalResponse, status_code=201)
    def register_portal(payload: PortalPayload) -> PortalResponse:
        try:
            portal = payload.to_domain()
            container.portal_service.register(portal)
        except ValueError as exc:  # Portal already exists
            raise handle_value_error(exc)
        return map_portal_response(portal)

    @app.get("/portals", response_model=list[PortalResponse])
    def list_portals() -> Iterable[PortalResponse]:
        return [map_portal_response(portal) for portal in container.portal_service.list_portals()]

    @app.post("/collect", response_model=CollectResponse)
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

    @app.post("/collect/stream")
    async def collect_articles_stream(
        request: Request, payload: CollectRequest
    ) -> EventSourceResponse:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()

        def push(event: str, data: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, {"event": event, "data": data})

        def finish() -> None:
            loop.call_soon_threadsafe(queue.put_nowait, None)

        def status_callback(message: str) -> None:
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
                        status_callback=status_callback,
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
            except Exception:
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

    @app.get("/articles", response_model=list[ArticleResponse])
    def list_articles(portal: str, start_date: date, end_date: date) -> Iterable[ArticleResponse]:
        articles = container.collector_service.list_articles(portal, start_date, end_date)
        return [map_article_response(article) for article in articles]

    return app


def selector_to_dict(selector: Selector) -> Dict[str, Any]:
    return {"query": selector.query, "attribute": selector.attribute}


def run() -> None:
    """Run the API using Uvicorn."""
    load_dotenv()
    uvicorn.run("sentinela.api:create_app", host="0.0.0.0", port=8000, factory=True)


__all__ = ["create_app", "run"]
