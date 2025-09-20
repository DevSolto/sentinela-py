from datetime import datetime

import pytest

from sentinela.domain.entities import Portal, PortalSelectors, Selector


def _build_portal(listing_template: str) -> Portal:
    selectors = PortalSelectors(
        listing_article=Selector(query="article"),
        listing_title=Selector(query="h2"),
        listing_url=Selector(query="a", attribute="href"),
        article_content=Selector(query="div.content"),
        article_date=Selector(query="time", attribute="datetime"),
    )
    return Portal(
        name="example",
        base_url="https://example.com",
        listing_path_template=listing_template,
        selectors=selectors,
    )


def test_listing_url_requires_date_placeholder() -> None:
    portal = _build_portal("/noticias?page={page}")

    with pytest.raises(ValueError) as excinfo:
        portal.listing_url_for(datetime(2024, 1, 1))

    message = str(excinfo.value)
    assert "collect-all" in message
    assert "{date}" in message
