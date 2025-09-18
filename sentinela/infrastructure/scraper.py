"""Implementation of the scraping engine."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import date, datetime
from typing import List
from urllib.parse import urljoin

import requests
import logging
from bs4 import BeautifulSoup

from sentinela.domain.entities import Article, Portal, Selector


class Scraper(ABC):
    """Defines the contract for collecting articles from a portal."""

    @abstractmethod
    def collect_for_date(self, portal: Portal, target_date: date) -> List[Article]:
        """Collect all articles from the portal on the given date."""

    # Optional extended contract for portals paginated by page number
    def collect_all(self, portal: Portal, start_page: int = 1, max_pages: int | None = None) -> List[Article]:
        raise NotImplementedError


class RequestsSoupScraper(Scraper):
    """Scraper implementation based on requests and BeautifulSoup."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._log = logging.getLogger("sentinela.scraper")

    def collect_for_date(self, portal: Portal, target_date: date) -> List[Article]:
        listing_url = portal.listing_url_for(datetime.combine(target_date, datetime.min.time()))
        self._log.info("GET %s", listing_url)
        response = self._session.get(listing_url, headers=portal.headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        article_elements = soup.select(portal.selectors.listing_article.query)

        articles: List[Article] = []
        self._log.info("%d itens na listagem", len(article_elements))
        for idx, element in enumerate(article_elements, start=1):
            title = self._extract_value(element, portal.selectors.listing_title)
            url = self._extract_url(element, portal)
            self._log.debug("item %d: %s -> %s", idx, title, url)
            summary = (
                self._extract_value(element, portal.selectors.listing_summary)
                if portal.selectors.listing_summary
                else None
            )
            self._log.debug("GET artigo %s", url)
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

    def collect_all(
        self, portal: Portal, start_page: int = 1, max_pages: int | None = None
    ) -> List[Article]:
        """Collect articles across paginated listing using {page} in template.

        Stops when a page yields no articles or when max_pages is reached.
        Requires portal.listing_has_full_articles=True to avoid per-article fetch.
        """
        if "{page}" not in portal.listing_path_template:
            raise ValueError("listing_path_template must contain '{page}' for collect_all")

        articles: List[Article] = []
        page = max(1, start_page)
        pages_processed = 0

        while True:
            if max_pages is not None and pages_processed >= max_pages:
                break

            path = portal.listing_path_template.format(page=page)
            listing_url = f"{portal.base_url.rstrip('/')}/{path.lstrip('/')}"
            self._log.info("page %d: GET %s", page, listing_url)
            response = self._session.get(listing_url, headers=portal.headers)
            if response.status_code == 404:
                self._log.info("page %d: 404, encerrando paginação", page)
                break
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            elements = soup.select(portal.selectors.listing_article.query)
            if not elements:
                self._log.info("page %d: 0 itens, encerrando paginação", page)
                break

            self._log.info("page %d: %d itens", page, len(elements))
            for i, element in enumerate(elements, start=1):
                title = self._extract_value(element, portal.selectors.listing_title)
                url = self._extract_url(element, portal)
                self._log.debug("page %d item %d: %s -> %s", page, i, title, url)
                summary = (
                    self._extract_value(element, portal.selectors.listing_summary)
                    if portal.selectors.listing_summary
                    else None
                )
                self._log.debug("GET artigo %s", url)
                article_response = self._session.get(url, headers=portal.headers)
                article_response.raise_for_status()
                article_soup = BeautifulSoup(article_response.text, "html.parser")
                content = self._extract_value(article_soup, portal.selectors.article_content)
                published_at_raw = self._extract_value(
                    article_soup, portal.selectors.article_date
                )
                # Clean possible prefix like 'em 17 de ...'
                published_at_raw = published_at_raw.strip()
                if published_at_raw.lower().startswith("em "):
                    published_at_raw = published_at_raw[3:].strip()
                published_at = self._parse_datetime(published_at_raw, portal.date_format)

                articles.append(
                    Article(
                        portal_name=portal.name,
                        title=title,
                        url=url,
                        content=content,
                        published_at=published_at,
                        summary=summary,
                        raw={"listing_url": listing_url},
                    )
                )

            page += 1
            pages_processed += 1

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
        # Handle month names in Portuguese when using %B without relying on OS locale
        if "%B" in date_format:
            months = {
                "janeiro": "01",
                "fevereiro": "02",
                "março": "03",
                "marco": "03",
                "abril": "04",
                "maio": "05",
                "junho": "06",
                "julho": "07",
                "agosto": "08",
                "setembro": "09",
                "outubro": "10",
                "novembro": "11",
                "dezembro": "12",
            }
            lowered = value.strip().lower()
            for name, num in months.items():
                if name in lowered:
                    lowered = lowered.replace(name, num)
                    break
            # Replace %B with %m in the format to match the numeric month we just injected
            numeric_format = date_format.replace("%B", "%m")
            return datetime.strptime(lowered, numeric_format)
        return datetime.strptime(value, date_format)
