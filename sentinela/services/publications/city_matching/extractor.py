"""Rotinas para extrair cidades de um artigo individual."""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping

from sentinela.extraction.normalization import normalize_text_with_offsets

from .config import CITY_CACHE_VERSION
from .matcher import CityMatcher
from .signals import enrich_matches_with_signals


def _get_field_text(article_doc: Any, field: str) -> str | None:
    """Retorna o valor textual associado a ``field`` no documento."""

    value: Any = None
    if isinstance(article_doc, Mapping):
        value = article_doc.get(field)
    else:
        value = getattr(article_doc, field, None)

    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def extract_cities_from_article(article_doc: Any, matcher: CityMatcher) -> dict[str, Any]:
    """Gera um payload estruturado com as cidades mencionadas no artigo.

    O resultado contém os textos normalizados dos campos analisados, o mapeamento
    de offsets para o texto original e todas as ocorrências encontradas pelo
    ``CityMatcher`` com suas respectivas posições dentro de cada campo.
    """

    notes: list[str] = []
    fields_payload: dict[str, dict[str, Any]] = {}
    matches_payload: list[dict[str, Any]] = []

    title_text = _get_field_text(article_doc, "title")
    body_text = _get_field_text(article_doc, "body")
    content_text = _get_field_text(article_doc, "content") if body_text is None else None

    fields_to_process: list[tuple[str, str]] = []
    if title_text:
        fields_to_process.append(("title", title_text))
    if body_text:
        fields_to_process.append(("body", body_text))
    elif content_text:
        fields_to_process.append(("content", content_text))
        notes.append("used_content_field")
    else:
        notes.append("missing_body_and_content")

    for field_name, text in fields_to_process:
        normalised_text, offsets = normalize_text_with_offsets(text)
        fields_payload[field_name] = {
            "text": text,
            "normalized_text": normalised_text,
            "offsets": offsets,
        }

        for match in matcher.find_matches(text):
            matches_payload.append(
                {
                    "field": field_name,
                    "city_id": match.city_id,
                    "name": match.name,
                    "uf": match.uf,
                    "surface": match.surface,
                    "start": match.start,
                    "end": match.end,
                    "method": match.method,
                    "score": match.score,
                }
            )

    matches_payload = enrich_matches_with_signals(matches_payload, fields_payload)
    matches_payload.sort(key=lambda item: (item["field"], item["start"], item["end"]))

    metadata = {
        "version": CITY_CACHE_VERSION,
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "notes": notes,
    }

    return {
        "fields": fields_payload,
        "matches": matches_payload,
        "cities_extraction": metadata,
    }


__all__ = ["extract_cities_from_article"]
