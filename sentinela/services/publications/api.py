"""FastAPI application exposing publication read endpoints."""
from __future__ import annotations

import os
from datetime import date
from typing import Iterable

import uvicorn
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sentinela.domain.entities import Article
from sentinela.services.publications import (
    PublicationsContainer,
    build_publications_container,
)


class ArticleResponse(BaseModel):
    """Representation of an article returned by the API."""

    portal: str
    title: str
    url: str
    content: str
    published_at: str
    summary: str | None = None


def configure_cors(app: FastAPI) -> None:
    """Apply the default CORS configuration used by the services."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def include_routes(
    app: FastAPI, container: PublicationsContainer, *, prefix: str = ""
) -> None:
    """Register publication routes on a FastAPI application."""

    router = APIRouter(prefix=prefix, tags=["Publicações"])

    def map_article_response(article: Article) -> ArticleResponse:
        return ArticleResponse(
            portal=article.portal_name,
            title=article.title,
            url=article.url,
            content=article.content,
            published_at=article.published_at.isoformat(),
            summary=article.summary,
        )

    @router.get("/articles", response_model=list[ArticleResponse])
    def list_articles(portal: str, start_date: date, end_date: date) -> Iterable[ArticleResponse]:
        if start_date > end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date deve ser anterior ou igual a end_date",
            )
        articles = container.query_service.list_articles(portal, start_date, end_date)
        return [map_article_response(article) for article in articles]

    app.include_router(router)


def create_app() -> FastAPI:
    """Create the FastAPI application with publication routes configured."""

    container = build_publications_container()
    app = FastAPI(
        title="Sentinela Publications API",
        version="1.0.0",
        description="Consulta de artigos coletados pelos serviços do Sentinela.",
    )
    configure_cors(app)
    include_routes(app, container)
    return app


def run() -> None:
    """Run the publications API using Uvicorn."""

    load_dotenv()
    uvicorn.run(
        "sentinela.services.publications.api:create_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        factory=True,
    )


__all__ = [
    "ArticleResponse",
    "create_app",
    "configure_cors",
    "include_routes",
    "run",
]
