"""Testes para correções automáticas em seletores CSS utilizados pelo scraper."""

from bs4 import BeautifulSoup

from sentinela.domain import Selector
from sentinela.infrastructure.scraper import RequestsSoupScraper


def test_extract_value_repairs_missing_attribute_bracket() -> None:
    scraper = RequestsSoupScraper()
    html = """
    <html>
      <head>
        <meta property="article:published_time" content="2025-10-23T17:38:00-03:00" />
      </head>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    selector = Selector(
        query="meta[property='article:published_time'", attribute="content"
    )

    value = scraper._extract_value(soup, selector)

    assert value == "2025-10-23T17:38:00-03:00"


def test_extract_value_repairs_missing_quote_and_bracket() -> None:
    scraper = RequestsSoupScraper()
    html = """
    <html>
      <head>
        <meta property="article:published_time" content="2025-10-23T17:38:00-03:00" />
      </head>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    selector = Selector(
        query="meta[property='article:published_time", attribute="content"
    )

    value = scraper._extract_value(soup, selector)

    assert value == "2025-10-23T17:38:00-03:00"


def test_extract_value_repairs_missing_quote_only() -> None:
    scraper = RequestsSoupScraper()
    html = """
    <html>
      <head>
        <meta property="article:published_time" content="2025-10-23T17:38:00-03:00" />
      </head>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    selector = Selector(
        query="meta[property='article:published_time]", attribute="content"
    )

    value = scraper._extract_value(soup, selector)

    assert value == "2025-10-23T17:38:00-03:00"


def test_normalize_selector_keeps_valid_query() -> None:
    scraper = RequestsSoupScraper()

    assert (
        scraper._normalize_selector_query("meta[property='article:published_time']")
        == "meta[property='article:published_time']"
    )
