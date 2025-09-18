"""Domain entities for the Sentinela news collector."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Selector:
    """Configuration for extracting a value from a HTML element.

    Attributes:
        query: CSS selector that will be used to locate the element.
        attribute: Optional attribute that should be read from the element. If not
            provided the text content of the element is returned.
    """

    query: str
    attribute: Optional[str] = None


@dataclass(frozen=True)
class PortalSelectors:
    """Selectors required to scrape a portal."""

    listing_article: Selector
    listing_title: Selector
    listing_url: Selector
    article_content: Selector
    article_date: Selector
    listing_summary: Optional[Selector] = None


@dataclass(frozen=True)
class Portal:
    """Represents a portal configuration registered by the user."""

    name: str
    base_url: str
    listing_path_template: str
    selectors: PortalSelectors
    headers: Dict[str, str] = field(default_factory=dict)
    date_format: str = "%Y-%m-%d"

    def listing_url_for(self, target_date: datetime) -> str:
        """Build the URL used to fetch the listing for a given date."""

        formatted_date = target_date.strftime(self.date_format)
        path = self.listing_path_template.format(date=formatted_date)
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"


@dataclass(frozen=True)
class Article:
    """Represents a collected article."""

    portal_name: str
    title: str
    url: str
    content: str
    published_at: datetime
    summary: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
