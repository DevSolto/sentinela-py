"""Testes para garantir fallback da primeira página na paginação."""
from __future__ import annotations

from datetime import datetime
from typing import Dict

import pytest

from sentinela.domain.entities.portal import Portal
from sentinela.domain.entities.portal_selectors import PortalSelectors
from sentinela.domain.entities.selector import Selector
from sentinela.infrastructure.scraper import RequestsSoupScraper


class _DummyResponse:
    def __init__(self, url: str, text: str, status_code: int = 200) -> None:
        self.url = url
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code} para {self.url}")


class _DummySession:
    def __init__(self, responses: Dict[str, _DummyResponse]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def get(self, url: str, headers: dict | None = None, timeout: int | None = None):
        normalized = url.rstrip("/") or url
        self.calls.append(normalized)
        if normalized not in self._responses:
            raise AssertionError(f"URL inesperada requisitada: {url}")
        return self._responses[normalized]


@pytest.fixture
def portal() -> Portal:
    selectors = PortalSelectors(
        listing_article=Selector(query="div.post.type-post"),
        listing_title=Selector(query="h2.post-title"),
        listing_url=Selector(query="h2.post-title a", attribute="href"),
        listing_summary=None,
        article_content=Selector(query="div.entry"),
        article_date=Selector(query="span.meta-date"),
    )
    return Portal(
        name="BlogTeste",
        base_url="https://example.com",
        listing_path_template="/page/{page}",
        selectors=selectors,
        date_format="%d/%m/%Y",
    )


def _build_html_listing(with_items: bool) -> str:
    if not with_items:
        return "<html><body><section class='empty'>Sem posts</section></body></html>"

    return """
    <html>
      <body>
        <div class="post type-post">
          <h2 class="post-title"><a href="/post-1">Título 1</a></h2>
          <span class="meta-date">01/06/2024</span>
        </div>
      </body>
    </html>
    """


def _build_html_article() -> str:
    return """
    <html>
      <body>
        <div class="entry">
          <p>Conteúdo do post</p>
        </div>
        <span class="meta-date">01/06/2024</span>
      </body>
    </html>
    """


def test_collect_all_uses_first_page_fallback(portal: Portal) -> None:
    listing_empty = _DummyResponse(
        "https://example.com/page/1", _build_html_listing(with_items=False)
    )
    page_stub = _DummyResponse(
        "https://example.com/page", _build_html_listing(with_items=False), status_code=404
    )
    base_listing = _DummyResponse(
        "https://example.com", _build_html_listing(with_items=True)
    )
    article_response = _DummyResponse("https://example.com/post-1", _build_html_article())

    session = _DummySession(
        {
            "https://example.com": base_listing,
            "https://example.com/page/1": listing_empty,
            "https://example.com/page": page_stub,
            "https://example.com/post-1": article_response,
        }
    )

    scraper = RequestsSoupScraper(session=session)
    articles = scraper.collect_all(portal, max_pages=1)

    assert len(articles) == 1
    assert articles[0].title == "Título 1"
    assert articles[0].url == "https://example.com/post-1"
    assert articles[0].content.strip().startswith("Conteúdo")
    assert articles[0].published_at.date() == datetime(2024, 6, 1).date()

