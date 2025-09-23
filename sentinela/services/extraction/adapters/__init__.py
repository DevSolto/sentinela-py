"""Adaptadores utilizados pelo serviço de extração de entidades."""

from .enriched_article_result import EnrichedArticleResult
from .extraction_result_store import ExtractionResultStore
from .extraction_result_store_writer import ExtractionResultStoreWriter
from .pending_news_queue import PendingNewsQueue
from .publications_api_repository import PublicationsAPIRepository
from .queue_news_repository import QueueNewsRepository

__all__ = [
    "EnrichedArticleResult",
    "ExtractionResultStore",
    "ExtractionResultStoreWriter",
    "PendingNewsQueue",
    "PublicationsAPIRepository",
    "QueueNewsRepository",
]
