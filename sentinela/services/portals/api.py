"""FastAPI application exposing portal management endpoints."""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable

import uvicorn
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sentinela.domain import Portal, PortalSelectors, Selector
from sentinela.services.portals import PortalsContainer, build_portals_container


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
    app: FastAPI, container: PortalsContainer, *, prefix: str = ""
) -> None:
    """Register portal routes on a FastAPI application."""

    router = APIRouter(prefix=prefix, tags=["Portais"])

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

    def handle_value_error(exc: ValueError) -> HTTPException:
        detail = str(exc)
        status = 404 if "not found" in detail.lower() else 400
        return HTTPException(status_code=status, detail=detail)

    @router.post("/portals", response_model=PortalResponse, status_code=201)
    def register_portal(payload: PortalPayload) -> PortalResponse:
        try:
            portal = payload.to_domain()
            container.portal_service.register(portal)
        except ValueError as exc:  # Portal already exists
            raise handle_value_error(exc)
        return map_portal_response(portal)

    @router.get("/portals", response_model=list[PortalResponse])
    def list_portals() -> Iterable[PortalResponse]:
        return [
            map_portal_response(portal)
            for portal in container.portal_service.list_portals()
        ]

    app.include_router(router)


def create_app() -> FastAPI:
    """Create the FastAPI application with portal routes configured."""

    container = build_portals_container()
    app = FastAPI(
        title="Sentinela Portals API",
        version="1.0.0",
        description="Cadastro e consulta de portais monitorados.",
    )
    configure_cors(app)
    include_routes(app, container)
    return app


def selector_to_dict(selector: Selector) -> Dict[str, Any]:
    """Serialize a selector to a dictionary representation."""

    return {"query": selector.query, "attribute": selector.attribute}


def run() -> None:
    """Run the portals API using Uvicorn."""

    load_dotenv()
    uvicorn.run(
        "sentinela.services.portals.api:create_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        factory=True,
    )


__all__ = [
    "create_app",
    "configure_cors",
    "include_routes",
    "PortalPayload",
    "PortalResponse",
    "run",
]
