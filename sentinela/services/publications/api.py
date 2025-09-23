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

from sentinela.domain import Article
from sentinela.services.publications import (
    PublicationsContainer,
    build_publications_container,
)
from sentinela.services.publications.adapters import create_ingestion_router


class EnrichedCandidateResponse(BaseModel):
    """Representation of a candidate city resolution."""

    city_id: str
    name: str
    uf: str
    score: float


class EnrichedCityResponse(BaseModel):
    """City occurrence enriched by the extraction pipeline."""

    city_id: str | None
    surface: str
    start: int
    end: int
    sentence: str
    status: str
    uf_surface: str | None
    method: str
    confidence: float
    candidates: list[EnrichedCandidateResponse]


class EnrichedPersonResponse(BaseModel):
    """Person occurrence enriched by the extraction pipeline."""

    person_id: str
    canonical_name: str
    surface: str
    start: int
    end: int
    sentence: str
    method: str
    confidence: float


class EnrichedArticleResponse(BaseModel):
    """Collection of entities associated with a news article."""

    url: str
    ner_version: str
    gazetteer_version: str
    updated_at: str
    people: list[EnrichedPersonResponse]
    cities: list[EnrichedCityResponse]


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

    def map_enriched(result) -> EnrichedArticleResponse:
        return EnrichedArticleResponse(
            url=result.url,
            ner_version=result.ner_version,
            gazetteer_version=result.gazetteer_version,
            updated_at=result.updated_at.isoformat(),
            people=[
                EnrichedPersonResponse(
                    person_id=occ.person_id,
                    canonical_name=occ.canonical_name,
                    surface=occ.surface,
                    start=occ.start,
                    end=occ.end,
                    sentence=occ.sentence,
                    method=occ.method,
                    confidence=occ.confidence,
                )
                for occ in result.people
            ],
            cities=[
                EnrichedCityResponse(
                    city_id=occ.city_id,
                    surface=occ.surface,
                    start=occ.start,
                    end=occ.end,
                    sentence=occ.sentence,
                    status=occ.status,
                    uf_surface=occ.uf_surface,
                    method=occ.method,
                    confidence=occ.confidence,
                    candidates=[
                        EnrichedCandidateResponse(
                            city_id=candidate.city_id,
                            name=candidate.name,
                            uf=candidate.uf,
                            score=candidate.score,
                        )
                        for candidate in occ.candidates
                    ],
                )
                for occ in result.cities
            ],
        )

    @router.get("/enriched/articles", response_model=list[EnrichedArticleResponse])
    def list_enriched_articles() -> list[EnrichedArticleResponse]:
        return [map_enriched(result) for result in container.extraction_store.list()]

    @router.get("/enriched/articles/{url:path}", response_model=EnrichedArticleResponse)
    def get_enriched_article(url: str) -> EnrichedArticleResponse:
        result = container.extraction_store.get(url)
        if not result:
            raise HTTPException(status_code=404, detail="Resultado não encontrado")
        return map_enriched(result)

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
    ingestion_router = create_ingestion_router(container.article_repository)
    app.include_router(ingestion_router, prefix=prefix)


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
    "EnrichedArticleResponse",
    "EnrichedCandidateResponse",
    "EnrichedCityResponse",
    "EnrichedPersonResponse",
    "create_app",
    "configure_cors",
    "include_routes",
    "run",
]
