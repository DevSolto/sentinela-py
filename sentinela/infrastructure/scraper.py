"""Implementation of the scraping engine."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import date, datetime, timezone
import logging
import re
import string
from pathlib import Path
from typing import List
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from soupsieve import SelectorSyntaxError

from sentinela.domain import Article, Portal, Selector


_COLLAPSE_WHITESPACE_RE = re.compile(r"\s+", re.UNICODE)


class Scraper(ABC):
    """Defines the contract for collecting articles from a portal."""

    @abstractmethod
    def collect_for_date(self, portal: Portal, target_date: date) -> List[Article]:
        """Collect all articles from the portal on the given date."""

    # Optional extended contract for portals paginated by page number
    def collect_all(
        self,
        portal: Portal,
        start_page: int = 1,
        max_pages: int | None = None,
        first_page_html_path: Path | None = None,
    ) -> List[Article]:
        raise NotImplementedError


_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"  # padrão navegador
        "image/avif,image/webp,image/apng,*/*;q=0.8,"  # imagens comuns
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}


class RequestsSoupScraper(Scraper):
    """Scraper implementation based on requests and BeautifulSoup."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._log = logging.getLogger("sentinela.scraper")
        self._prepared_portals: set[str] = set()

    def collect_for_date(self, portal: Portal, target_date: date) -> List[Article]:
        self._prepare_portal_session(portal)
        listing_url = portal.listing_url_for(datetime.combine(target_date, datetime.min.time()))
        self._log.info("GET %s", listing_url)
        response = self._session.get(
            listing_url, headers=self._build_headers(portal, {"Referer": portal.base_url})
        )
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
                article_response = self._session.get(
                    url,
                    headers=self._build_headers(
                        portal, {"Referer": listing_url}
                    ),
                )
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
                    cities=tuple(),
                    raw=raw_map,
                )
            )

        return articles

    def collect_all(
        self,
        portal: Portal,
        start_page: int = 1,
        max_pages: int | None = None,
        first_page_html_path: Path | None = None,
    ) -> List[Article]:
        """Collect articles across paginated listing using {page} in template.

        Stops when a page yields no articles or when ``max_pages`` is reached.
        Requires ``portal.listing_has_full_articles=True`` to avoid per-article
        fetch. Quando ``first_page_html_path`` é informado, o HTML bruto da
        primeira página é persistido para auditoria.
        """
        if "{page}" not in portal.listing_path_template:
            raise ValueError("listing_path_template must contain '{page}' for collect_all")

        articles: List[Article] = []
        page = max(1, start_page)
        pages_processed = 0

        first_page_html_saved = False

        while True:
            if max_pages is not None and pages_processed >= max_pages:
                break

            self._prepare_portal_session(portal)
            listing_url = self._build_listing_url(portal, page)
            self._log.info("page %d: GET %s", page, listing_url)
            soup, response = self._fetch_listing_soup(
                portal, listing_url, referer=portal.base_url
            )
            if first_page_html_path and not first_page_html_saved:
                first_page_html_saved = self._dump_first_page_html(
                    first_page_html_path, response.text
                )
            if response.status_code == 404:
                self._log.info("page %d: 404, encerrando paginação", page)
                break
            elements = soup.select(portal.selectors.listing_article.query)
            if not elements and page == 1:
                fallback = self._try_first_page_fallback(portal, listing_url)
                if fallback is not None:
                    listing_url, html_text, soup, elements = fallback
                    if first_page_html_path and not first_page_html_saved:
                        first_page_html_saved = self._dump_first_page_html(
                            first_page_html_path, html_text
                        )
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
                    article_response = self._session.get(
                        url,
                        headers=self._build_headers(
                            portal,
                            {"Referer": listing_url},
                        ),
                    )
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
                        cities=tuple(),
                        raw=raw_map,
                    )
                )

            page += 1
            pages_processed += 1

        return articles

    def _build_listing_url(self, portal: Portal, page: int) -> str:
        path = portal.listing_path_template.format(page=page)
        base = portal.base_url.rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    def _build_headers(
        self, portal: Portal, extra: dict[str, str] | None = None
    ) -> dict[str, str]:
        """Combina cabeçalhos padrão com os específicos do portal.

        Os portais podem exigir cabeçalhos semelhantes aos de navegadores reais
        para liberar o conteúdo completo. Esta função garante que sempre
        enviamos um conjunto robusto de cabeçalhos, permitindo que valores
        fornecidos pelo portal prevaleçam quando necessário.
        """

        headers: dict[str, str] = dict(_DEFAULT_HEADERS)
        if portal.headers:
            headers.update(portal.headers)
        if extra:
            headers.update({k: v for k, v in extra.items() if v})
        return headers

    def _prepare_portal_session(self, portal: Portal) -> None:
        """Realiza uma requisição inicial ao portal para obter cookies/sessão."""

        if portal.name in self._prepared_portals:
            return

        try:
            self._log.debug("warmup GET %s", portal.base_url)
            response = self._session.get(
                portal.base_url,
                headers=self._build_headers(portal, {"Referer": portal.base_url}),
                timeout=15,
            )
            # Mesmo em caso de 403, manteremos o fluxo; apenas registramos.
            if response.status_code >= 400:
                self._log.debug(
                    "warmup %s retornou %s", portal.base_url, response.status_code
                )
        except Exception as exc:  # pragma: no cover - depende do portal
            self._log.debug("warmup falhou para %s: %s", portal.base_url, exc)
        finally:
            self._prepared_portals.add(portal.name)

    def _fetch_listing_soup(
        self, portal: Portal, url: str, *, referer: str
    ) -> tuple[BeautifulSoup, requests.Response]:
        response = self._session.get(
            url,
            headers=self._build_headers(portal, {"Referer": referer}),
        )
        if response.status_code != 404:
            response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser"), response

    def _try_first_page_fallback(
        self, portal: Portal, original_url: str
    ) -> tuple[str, str, BeautifulSoup, list] | None:
        """Tenta alternativas para a primeira página quando ela vem vazia."""

        candidates = self._first_page_fallback_urls(portal, original_url)
        for candidate in candidates:
            try:
                soup, response = self._fetch_listing_soup(
                    portal, candidate, referer=portal.base_url
                )
            except requests.HTTPError as exc:
                self._log.debug(
                    "fallback primeira página falhou em %s: %s", candidate, exc
                )
                continue
            elements = soup.select(portal.selectors.listing_article.query)
            if elements:
                self._log.info(
                    "page 1: fallback encontrou %d itens em %s",
                    len(elements),
                    response.url,
                )
                return response.url, response.text, soup, elements
        return None

    def _dump_first_page_html(self, path: Path, html: str) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
            self._log.info("Primeira página salva em %s", path)
            return True
        except OSError as exc:
            self._log.warning(
                "Falha ao salvar HTML da primeira página em %s: %s", path, exc
            )
            return False

    def _first_page_fallback_urls(
        self, portal: Portal, original_url: str
    ) -> list[str]:
        """Gera URLs candidatas para a primeira página sem sufixo de paginação."""

        split_url = urlsplit(original_url)
        candidates: list[str] = []

        # Remove parâmetros comuns de paginação na query string.
        if split_url.query:
            params = split_url.query.split("&")
            pagination_keys = {"page", "paged", "pagina", "pag", "p"}
            filtered = [
                item
                for item in params
                if item.split("=", 1)[0] not in pagination_keys
            ]
            if filtered != params:
                new_query = "&".join(p for p in filtered if p)
                candidates.append(
                    urlunsplit(
                        (
                            split_url.scheme,
                            split_url.netloc,
                            split_url.path,
                            new_query,
                            split_url.fragment,
                        )
                    )
                )
                if not new_query:
                    candidates.append(
                        urlunsplit(
                            (
                                split_url.scheme,
                                split_url.netloc,
                                split_url.path,
                                "",
                                split_url.fragment,
                            )
                        )
                    )

        path = split_url.path
        suffixes = [
            ("/1", ""),
            ("-1", ""),
            ("_1", ""),
        ]
        trailing_segments = ["/page", "/pagina", "/pag", "/p"]
        for suffix, replacement in suffixes:
            if path.endswith(suffix):
                trimmed = path[: -len(suffix)] + replacement
                candidates.append(
                    urlunsplit(
                        (
                            split_url.scheme,
                            split_url.netloc,
                            trimmed or "/",
                            split_url.query,
                            split_url.fragment,
                        )
                    )
                )
                for segment in trailing_segments:
                    if trimmed.endswith(segment):
                        alt_path = trimmed[: -len(segment)] or "/"
                        candidates.append(
                            urlunsplit(
                                (
                                    split_url.scheme,
                                    split_url.netloc,
                                    alt_path,
                                    split_url.query,
                                    split_url.fragment,
                                )
                            )
                        )

        # Sempre considerar a URL base como último recurso.
        candidates.append(portal.base_url)

        normalized_original = original_url.rstrip("/")
        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            candidate = candidate or portal.base_url
            normalized = candidate.rstrip("/")
            if not normalized or normalized == normalized_original:
                continue
            if normalized not in seen:
                seen.add(normalized)
                unique.append(candidate)

        return unique

    def _extract_url(self, element, portal: Portal) -> str:
        raw_url = self._extract_value(element, portal.selectors.listing_url)
        return urljoin(portal.base_url, raw_url)

    def _extract_value(self, element, selector: Selector) -> str:
        """Extract text or attribute by CSS selector, tolerant to minor changes.

        Instead of raising immediately when the selector is not found, try a
        couple of common fallbacks and only then raise. This reduces hard
        failures when a portal slightly changes its HTML structure.
        """
        query = selector.query
        # Primary attempt
        try:
            target = element.select_one(query)
        except SelectorSyntaxError as exc:
            normalized_query = self._normalize_selector_query(query)
            if normalized_query != query:
                self._log.debug(
                    "ajustando seletor malformado '%s' para '%s'", query, normalized_query
                )
                query = normalized_query
                try:
                    target = element.select_one(query)
                except SelectorSyntaxError as exc2:  # pragma: no cover - raríssimo
                    raise ValueError(
                        f"Selector '{selector.query}' inválido: {exc2}"
                    ) from exc2
            else:
                raise ValueError(
                    f"Selector '{selector.query}' inválido: {exc}"
                ) from exc

        # Fallback 1: if query ends with ' > *:first-child', try parent
        if not target and query.endswith(":first-child"):
            simplified = query.replace(" > *:first-child", "").replace(":first-child", "")
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

    def _normalize_selector_query(self, query: str) -> str:
        """Corrige seletores com colchetes e aspas ausentes."""

        result: list[str] = []
        bracket_balance = 0
        quote_char: str | None = None

        for char in query:
            if char in ("'", '"'):
                if quote_char is None:
                    quote_char = char
                elif quote_char == char:
                    quote_char = None

            if char == "[" and quote_char is None:
                bracket_balance += 1
            elif char == "]":
                if quote_char is not None:
                    # Fecha aspas antes de fechar o colchete.
                    result.append(quote_char)
                    quote_char = None
                if bracket_balance > 0:
                    bracket_balance -= 1

            result.append(char)

        if quote_char is not None:
            result.append(quote_char)

        if bracket_balance > 0:
            result.extend("]" * bracket_balance)

        return "".join(result)

    def _parse_datetime(self, value: str, date_format: str) -> datetime:
        normalized_value = self._normalize_datetime_value(value)

        iso_candidate = self._try_parse_isoformat(normalized_value)
        if iso_candidate is not None:
            return iso_candidate

        regex_error: ValueError | None = None
        if self._looks_like_regex(date_format):
            try:
                return self._parse_datetime_with_regex(
                    normalized_value, date_format
                )
            except ValueError as exc:
                regex_error = exc

        br_candidate = self._try_parse_br_datetime(normalized_value)
        if br_candidate is not None:
            return br_candidate

        if regex_error is not None:
            raise regex_error

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
            normalized_value = normalized_value.lower()
            for name, num in months.items():
                if name in normalized_value:
                    normalized_value = normalized_value.replace(name, num)
                    break
            # Replace %B with %m in the format to match the numeric month we just injected
            numeric_format = date_format.replace("%B", "%m")
            normalized_format = self._normalize_format_literals(numeric_format)
            return datetime.strptime(normalized_value, normalized_format)
        return datetime.strptime(normalized_value, date_format)

    def _parse_datetime_with_regex(self, value: str, date_format: str) -> datetime:
        try:
            pattern = re.compile(date_format)
        except re.error as exc:  # pragma: no cover - depende de configuração externa
            raise ValueError(
                "padrão de data inválido: {}. "
                "Se estiver utilizando sequências com barra, lembre-se de duplicá-las, "
                "por exemplo, '\\d{{2}}' em JSON ou formulários."
                .format(exc)
            ) from exc
        match = pattern.search(value)
        if not match:
            raise ValueError(
                f"valor '{value}' não corresponde ao padrão de data '{date_format}'"
            )
        groups: list[str] = []
        group_dict = match.groupdict()
        for key in ("published", "date", "datetime"):
            extracted = group_dict.get(key)
            if extracted:
                groups.append(extracted)
        for extracted in group_dict.values():
            if extracted:
                groups.append(extracted)
        groups.extend(group for group in match.groups() if group)
        for candidate in groups:
            normalized_candidate = self._normalize_datetime_value(candidate)
            parsed = self._try_parse_isoformat(normalized_candidate)
            if parsed is not None:
                return parsed
            parsed = self._try_parse_br_datetime(normalized_candidate)
            if parsed is not None:
                return parsed
        raise ValueError(
            f"não foi possível interpretar data '{value}' usando o padrão '{date_format}'"
        )

    def _try_parse_isoformat(self, value: str) -> datetime | None:
        candidate = value
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    def _try_parse_br_datetime(self, value: str) -> datetime | None:
        date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
        if not date_match:
            return None
        day, month, year = map(int, date_match.groups())

        time_match = re.search(r"(\d{1,2})[:h](\d{2})(?:[:h](\d{2}))?", value)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            second = int(time_match.group(3) or 0)
        else:
            hour = minute = second = 0

        try:
            return datetime(year, month, day, hour, minute, second)
        except ValueError:
            return None

    def _looks_like_regex(self, date_format: str) -> bool:
        return bool(
            date_format
            and "%" not in date_format
            and (
                "(?" in date_format
                or "\\d" in date_format
                or "[" in date_format
                or ")" in date_format
            )
        )

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

    def _normalize_datetime_value(self, value: str) -> str:
        sanitized = value.replace("\xa0", " ").replace("\u202f", " ")
        sanitized = _COLLAPSE_WHITESPACE_RE.sub(" ", sanitized)
        return sanitized.strip()
