"""Implementation of the scraping engine."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import date, datetime
from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from sentinela.domain.entities import Article, Portal, Selector


class Scraper(ABC):
    """Defines the contract for collecting articles from a portal."""

    @abstractmethod
    def collect_for_date(self, portal: Portal, target_date: date) -> List[Article]:
        """Collect all articles from the portal on the given date."""


class RequestsSoupScraper(Scraper):
    """Scraper implementation based on requests and BeautifulSoup."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def collect_for_date(self, portal: Portal, target_date: date) -> List[Article]:
        listing_url = portal.listing_url_for(datetime.combine(target_date, datetime.min.time()))
        response = self._session.get(listing_url, headers=portal.headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        article_elements = soup.select(portal.selectors.listing_article.query)

        articles: List[Article] = []
        for element in article_elements:
            title = self._extract_value(element, portal.selectors.listing_title)
            url = self._extract_url(element, portal)
            summary = (
                self._extract_value(element, portal.selectors.listing_summary)
                if portal.selectors.listing_summary
                else None
            )

            article_response = self._session.get(url, headers=portal.headers)
            article_response.raise_for_status()
            article_soup = BeautifulSoup(article_response.text, "html.parser")

            content = self._extract_value(article_soup, portal.selectors.article_content)
            published_at_raw = self._extract_value(article_soup, portal.selectors.article_date)
            published_at = self._parse_datetime(published_at_raw, portal.date_format)

            articles.append(
                Article(
                    portal_name=portal.name,
                    title=title,
                    url=url,
                    content=content,
                    published_at=published_at,
                    summary=summary,
                    raw={
                        "listing_url": listing_url,
                        "selectors": asdict(portal.selectors),
                    },
                )
            )

        return articles

    def _extract_url(self, element, portal: Portal) -> str:
        raw_url = self._extract_value(element, portal.selectors.listing_url)
        return urljoin(portal.base_url, raw_url)

    def _extract_value(self, element, selector: Selector) -> str:
        if selector.attribute:
            target = element.select_one(selector.query)
            if not target or selector.attribute not in target.attrs:
                raise ValueError(
                    f"Attribute '{selector.attribute}' not found for selector '{selector.query}'"
                )
            return target.attrs[selector.attribute].strip()

        target = element.select_one(selector.query)
        if not target:
            raise ValueError(f"Selector '{selector.query}' not found")
        return target.get_text(strip=True)

    def _parse_datetime(self, value: str, date_format: str) -> datetime:
        return datetime.strptime(value, date_format)
