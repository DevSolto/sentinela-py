"""Entity extraction microservice components."""
from .models import (
    CityCandidate,
    CityOccurrence,
    CityResolution,
    EntitySpan,
    NewsDocument,
    NormalizedPersonName,
    PersonOccurrence,
    ProcessedBatchResult,
    ExtractionResultWriter,
    NewsRepository,
)
from .gazetteer import CityGazetteer, CityRecord
from .normalization import (
    extract_state_mentions,
    find_sentence_containing,
    normalize_article_text,
    normalize_person_name,
)
from .service import EntityExtractionService
from .ner import NEREngine

__all__ = [
    "CityCandidate",
    "CityGazetteer",
    "CityOccurrence",
    "CityRecord",
    "CityResolution",
    "EntityExtractionService",
    "EntitySpan",
    "NEREngine",
    "NewsDocument",
    "NormalizedPersonName",
    "PersonOccurrence",
    "ProcessedBatchResult",
    "ExtractionResultWriter",
    "NewsRepository",
    "extract_state_mentions",
    "find_sentence_containing",
    "normalize_article_text",
    "normalize_person_name",
]
