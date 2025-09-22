"""REST API entrypoint aggregating Sentinela services."""
from __future__ import annotations

import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

from sentinela.services.news import build_news_container
from sentinela.services.news.api import include_routes as include_news_routes
from sentinela.services.portals import build_portals_container
from sentinela.services.portals.api import (
    configure_cors as configure_default_cors,
    include_routes as include_portals_routes,
)
from sentinela.services.publications import build_publications_container
from sentinela.services.publications.api import include_routes as include_publications_routes


def create_app() -> FastAPI:
    """Create the FastAPI application with all service routes configured."""

    portals_container = build_portals_container()
    news_container = build_news_container()
    publications_container = build_publications_container()

    app = FastAPI(
        title="Sentinela API",
        version="1.0.0",
        description=(
            "Agrega as operações de cadastro de portais, coleta de notícias e "
            "consulta de publicações em uma única aplicação."
        ),
    )
    configure_default_cors(app)
    include_portals_routes(app, portals_container)
    include_news_routes(app, news_container)
    include_publications_routes(app, publications_container)
    return app


def run() -> None:
    """Run the aggregated API using Uvicorn."""

    load_dotenv()
    uvicorn.run(
        "sentinela.api:create_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        factory=True,
    )


__all__ = ["create_app", "run"]
