"""Implementation of the scraping engine."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import date, datetime
import logging
import string
from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from sentinela.domain import Article, Portal, Selector


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
            try:
                title = self._extract_value(element, portal.selectors.listing_title)
                url = self._extract_url(element, portal)
            except Exception as exc:
                self._log.warning("item %d: falha ao obter título/URL: %s", idx, exc)
                continue
            self._log.debug("item %d: %s -> %s", idx, title, url)
            summary = None
            if portal.selectors.listing_summary:
                try:
                    summary = self._extract_value(
                        element, portal.selectors.listing_summary
                    )
                except Exception as exc:
                    self._log.debug(
                        "item %d: resumo ausente, seguindo sem resumo: %s", idx, exc
                    )
            self._log.debug("GET artigo %s", url)
            try:
                article_response = self._session.get(url, headers=portal.headers)
                article_response.raise_for_status()
                article_soup = BeautifulSoup(article_response.text, "html.parser")
            except Exception as exc:
                self._log.warning("falha ao abrir artigo %s: %s", url, exc)
                continue

            raw_map = {"listing_url": listing_url, "selectors": asdict(portal.selectors)}
            try:
                content = self._extract_value(article_soup, portal.selectors.article_content)
            except Exception as exc:
                self._log.warning("conteúdo ausente em %s: %s", url, exc)
                content = ""
                raw_map["content_missing"] = True
            try:
                published_at_raw = self._extract_value(article_soup, portal.selectors.article_date)
                published_at = self._parse_datetime(published_at_raw, portal.date_format)
            except Exception as exc:
                self._log.warning("data ausente/ inválida em %s: %s", url, exc)
                published_at = datetime.utcnow()
                raw_map["date_missing"] = True

            articles.append(
                Article(
                    portal_name=portal.name,
                    title=title,
                    url=url,
                    content=content,
                    published_at=published_at,
                    summary=summary,
                    raw=raw_map,
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
                try:
                    title = self._extract_value(element, portal.selectors.listing_title)
                    url = self._extract_url(element, portal)
                except Exception as exc:
                    self._log.warning("page %d item %d: falha título/URL: %s", page, i, exc)
                    continue
                self._log.debug("page %d item %d: %s -> %s", page, i, title, url)
                summary = None
                if portal.selectors.listing_summary:
                    try:
                        summary = self._extract_value(
                            element, portal.selectors.listing_summary
                        )
                    except Exception as exc:
                        self._log.debug(
                            "page %d item %d: resumo ausente, seguindo sem resumo: %s",
                            page,
                            i,
                            exc,
                        )
                self._log.debug("GET artigo %s", url)
                try:
                    article_response = self._session.get(url, headers=portal.headers)
                    article_response.raise_for_status()
                    article_soup = BeautifulSoup(article_response.text, "html.parser")
                except Exception as exc:
                    self._log.warning("falha ao abrir artigo %s: %s", url, exc)
                    continue
                raw_map = {"listing_url": listing_url}
                try:
                    content = self._extract_value(article_soup, portal.selectors.article_content)
                except Exception as exc:
                    self._log.warning("conteúdo ausente em %s: %s", url, exc)
                    content = ""
                    raw_map["content_missing"] = True
                try:
                    published_at_raw = self._extract_value(
                        article_soup, portal.selectors.article_date
                    )
                    # Clean possible prefix like 'em 17 de ...'
                    published_at_raw = published_at_raw.strip()
                    if published_at_raw.lower().startswith("em "):
                        published_at_raw = published_at_raw[3:].strip()
                    published_at = self._parse_datetime(published_at_raw, portal.date_format)
                except Exception as exc:
                    self._log.warning("data ausente/ inválida em %s: %s", url, exc)
                    published_at = datetime.utcnow()
                    raw_map["date_missing"] = True
                articles.append(
                    Article(
                        portal_name=portal.name,
                        title=title,
                        url=url,
                        content=content,
                        published_at=published_at,
                        summary=summary,
                        raw=raw_map,
                    )
                )

            page += 1
            pages_processed += 1

        return articles

    def _extract_url(self, element, portal: Portal) -> str:
        raw_url = self._extract_value(element, portal.selectors.listing_url)
        return urljoin(portal.base_url, raw_url)

    def _extract_value(self, element, selector: Selector) -> str:
        """Extract text or attribute by CSS selector, tolerant to minor changes.

        Instead of raising immediately when the selector is not found, try a
        couple of common fallbacks and only then raise. This reduces hard
        failures when a portal slightly changes its HTML structure.
        """
        # Primary attempt
        target = element.select_one(selector.query)

        # Fallback 1: if query ends with ' > *:first-child', try parent
        if not target and selector.query.endswith(":first-child"):
            simplified = selector.query.replace(" > *:first-child", "").replace(
                ":first-child", ""
            )
            target = element.select_one(simplified)

        # If still not found, raise with a clear message
        if not target:
            raise ValueError(f"Selector '{selector.query}' not found")

        if selector.attribute:
            if selector.attribute not in target.attrs:
                raise ValueError(
                    f"Attribute '{selector.attribute}' not found for selector '{selector.query}'"
                )
            return str(target.attrs[selector.attribute]).strip()

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
            normalized_value = value.strip().lower()
            for name, num in months.items():
                if name in normalized_value:
                    normalized_value = normalized_value.replace(name, num)
                    break
            # Replace %B with %m in the format to match the numeric month we just injected
            numeric_format = date_format.replace("%B", "%m")
            normalized_format = self._normalize_format_literals(numeric_format)
            return datetime.strptime(normalized_value, normalized_format)
        return datetime.strptime(value, date_format)

    def _normalize_format_literals(self, format_str: str) -> str:
        """Lowercase literal fragments of a strptime format string."""

        result: list[str] = []
        i = 0
        while i < len(format_str):
            char = format_str[i]
            if char == "%":
                start = i
                i += 1
                if i < len(format_str) and format_str[i] == "%":
                    # Escaped percent, keep as-is
                    i += 1
                    result.append("%%")
                    continue
                # Consume optional modifiers until we reach the directive char
                while i < len(format_str) and format_str[i] not in string.ascii_letters:
                    i += 1
                if i < len(format_str):
                    i += 1
                result.append(format_str[start:i])
            else:
                start = i
                while i < len(format_str) and format_str[i] != "%":
                    i += 1
                result.append(format_str[start:i].lower())
        return "".join(result)
