"""Ponto de entrada REST que agrega os serviços do Sentinela."""
from __future__ import annotations

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
from sentinela.settings import get_api_bind_host, get_api_port


def create_app() -> FastAPI:
    """Cria a aplicação FastAPI com todas as rotas de serviços configuradas."""

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
    """Executa a API agregada utilizando o Uvicorn."""

    load_dotenv()
    uvicorn.run(
        "sentinela.api:create_app",
        host=get_api_bind_host(),
        port=get_api_port(),
        factory=True,
    )


__all__ = ["create_app", "run"]
