"""Adapters used by the publications service to receive new articles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from sentinela.domain.entities import Article
from sentinela.domain.repositories import ArticleRepository


@dataclass
class ArticleIngestionAdapter:
    """Filters and persists new articles into the publications datastore."""

    repository: ArticleRepository

    def ingest(self, articles: Iterable[Article]) -> List[Article]:
        """Persist ``articles`` and return only the ones stored for the first time."""

        unique: dict[tuple[str, str], Article] = {}
        for article in articles:
            key = (article.portal_name, article.url)
            if key not in unique:
                unique[key] = article

        new_articles = [
            article
            for key, article in unique.items()
            if not self.repository.exists(key[0], key[1])
        ]

        if new_articles:
            self.repository.save_many(new_articles)

        return new_articles

