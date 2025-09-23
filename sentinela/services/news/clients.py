"""HTTP clients used by the news service to communicate with other services."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

import httpx

from sentinela.domain import Article, Portal, PortalSelectors, Selector
from sentinela.domain.ports import ArticleSink, PortalGateway


def _selector_from_payload(payload: dict) -> Selector:
    return Selector(query=payload["query"], attribute=payload.get("attribute"))


def _portal_from_payload(payload: dict) -> Portal:
    selectors = payload["selectors"]
    return Portal(
        name=payload["name"],
        base_url=payload["base_url"],
        listing_path_template=payload["listing_path_template"],
        selectors=PortalSelectors(
            listing_article=_selector_from_payload(selectors["listing_article"]),
            listing_title=_selector_from_payload(selectors["listing_title"]),
            listing_url=_selector_from_payload(selectors["listing_url"]),
            article_content=_selector_from_payload(selectors["article_content"]),
            article_date=_selector_from_payload(selectors["article_date"]),
            listing_summary=
                _selector_from_payload(selectors["listing_summary"])
                if selectors.get("listing_summary")
                else None,
        ),
        headers=payload.get("headers", {}),
        date_format=payload.get("date_format", "%Y-%m-%d"),
    )


def _article_to_payload(article: Article) -> dict:
    return {
        "portal": article.portal_name,
        "title": article.title,
        "url": article.url,
        "content": article.content,
        "summary": article.summary,
        "published_at": article.published_at.isoformat(),
    }


def _article_from_payload(payload: dict) -> Article:
    return Article(
        portal_name=payload["portal"],
        title=payload["title"],
        url=payload["url"],
        content=payload["content"],
        summary=payload.get("summary"),
        published_at=datetime.fromisoformat(payload["published_at"]),
        raw=payload.get("raw", {}),
    )


class PortalServiceClient(PortalGateway):
    """HTTP implementation of :class:`PortalGateway`."""

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        timeout: float | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if client is None:
            self._client = httpx.Client(base_url=self._base_url, timeout=timeout)
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False

    def get_portal(self, name: str) -> Optional[Portal]:
        response = self._client.get("/portals")
        response.raise_for_status()
        for payload in response.json():
            if payload.get("name") == name:
                return _portal_from_payload(payload)
        return None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class PublicationsAPISink(ArticleSink):
    """HTTP adapter that forwards new articles to the publications service."""

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        timeout: float | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if client is None:
            self._client = httpx.Client(base_url=self._base_url, timeout=timeout)
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False

    def publish_many(self, articles: Iterable[Article]) -> Iterable[Article]:
        payload = [_article_to_payload(article) for article in articles]
        if not payload:
            return []
        response = self._client.post("/articles/batch", json={"articles": payload})
        response.raise_for_status()
        body = response.json()
        stored = body.get("stored", [])
        return [_article_from_payload(item) for item in stored]

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


__all__ = ["PortalServiceClient", "PublicationsAPISink"]
