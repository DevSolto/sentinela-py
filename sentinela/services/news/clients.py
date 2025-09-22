"""Clients used by the news service to integrate with remote microservices."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import requests

from sentinela.domain.entities import Article, Portal, PortalSelectors, Selector
from sentinela.domain.ports import ArticleSink, PortalGateway


def _join_url(base: str, path: str) -> str:
    base = base.rstrip("/")
    path = path.lstrip("/")
    return f"{base}/{path}" if path else base


def _build_selector(data: dict[str, str | None]) -> Selector:
    return Selector(query=data["query"], attribute=data.get("attribute"))


def _build_portal(data: dict) -> Portal:
    selectors = data["selectors"]
    return Portal(
        name=data["name"],
        base_url=data["base_url"],
        listing_path_template=data["listing_path_template"],
        headers=data.get("headers", {}),
        date_format=data.get("date_format", "%Y-%m-%d"),
        selectors=PortalSelectors(
            listing_article=_build_selector(selectors["listing_article"]),
            listing_title=_build_selector(selectors["listing_title"]),
            listing_url=_build_selector(selectors["listing_url"]),
            article_content=_build_selector(selectors["article_content"]),
            article_date=_build_selector(selectors["article_date"]),
            listing_summary=_build_selector(selectors["listing_summary"])
            if selectors.get("listing_summary")
            else None,
        ),
    )


def _build_article(data: dict) -> Article:
    return Article(
        portal_name=data["portal"],
        title=data["title"],
        url=data["url"],
        content=data["content"],
        summary=data.get("summary"),
        published_at=datetime.fromisoformat(data["published_at"]),
        raw=data.get("raw", {}),
    )


def _serialize_article(article: Article) -> dict:
    return {
        "portal": article.portal_name,
        "title": article.title,
        "url": article.url,
        "content": article.content,
        "summary": article.summary,
        "published_at": article.published_at.isoformat(),
        "raw": article.raw,
    }


@dataclass
class PortalServiceClient(PortalGateway):
    """HTTP client that retrieves portal configurations from the portal service."""

    base_url: str
    session: requests.Session | None = None
    timeout: float = 10.0

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()

    def get_portal(self, name: str) -> Portal | None:
        url = _join_url(self.base_url, f"portals/{name}")
        response = self.session.get(url, timeout=self.timeout)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        return _build_portal(data)


@dataclass
class PublicationServiceClient(ArticleSink):
    """HTTP client that publishes collected articles to the publications service."""

    base_url: str
    session: requests.Session | None = None
    timeout: float = 10.0

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()

    def persist(self, articles: Iterable[Article]) -> list[Article]:
        articles = list(articles)
        if not articles:
            return []
        payload = {"articles": [_serialize_article(article) for article in articles]}
        url = _join_url(self.base_url, "articles")
        response = self.session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return [_build_article(item) for item in data]

