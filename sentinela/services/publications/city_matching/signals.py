"""Cálculo de sinais adicionais para ocorrências de cidades.

O módulo é responsável por derivar sinais contextuais a partir dos campos
normalizados retornados pelo extrator de cidades. Esses sinais são utilizados
posteriormente durante a agregação para ajustar a confiança atribuída a cada
menção identificada.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from typing import Any, Mapping, MutableMapping, Sequence

from sentinela.extraction.normalization import (
    extract_state_mentions,
    find_sentence_containing,
)

# Pesos aplicados aos sinais reconhecidos. Os valores foram calibrados para
# favorecer menções em posições de maior destaque (como o título) e para dar um
# peso significativo a marcadores administrativos comuns em notícias.
TITLE_BOOST_WEIGHT = 0.4
ADMIN_MARKER_WEIGHT = 0.6

_ADMIN_KEYWORDS = {
    "prefeito",
    "prefeita",
    "governador",
    "governadora",
    "vereador",
    "vereadora",
    "secretario",
    "secretaria",
}


def _resolve_field_info(
    fields: Mapping[str, Mapping[str, Any]], field_name: str
) -> Mapping[str, Any] | None:
    field = fields.get(field_name)
    if not isinstance(field, Mapping):
        return None
    text = field.get("text")
    normalized_text = field.get("normalized_text")
    offsets = field.get("offsets")
    if not isinstance(text, str) or not isinstance(normalized_text, str):
        return None
    if not isinstance(offsets, Sequence):
        return None
    return field


def _get_normalized_span(
    offsets: Sequence[int], start: int, end: int
) -> tuple[int, int]:
    """Retorna o intervalo equivalente na versão normalizada do texto."""

    if not offsets:
        return 0, 0
    norm_start = bisect_left(offsets, max(start, 0))
    norm_end = bisect_right(offsets, max(end - 1, 0))
    return norm_start, norm_end


def _detect_admin_marker(normalized_text: str, start: int, end: int) -> bool:
    window_start = max(0, start - 48)
    window_end = min(len(normalized_text), end + 48)
    window = normalized_text[window_start:window_end]
    return any(keyword in window for keyword in _ADMIN_KEYWORDS)


def _extract_context_uf(text: str, start: int, end: int) -> str | None:
    sentence = find_sentence_containing(text, start, end)
    mentions = extract_state_mentions(sentence)
    if not mentions:
        return None
    # Define uma ordem determinística para que os testes possam prever o
    # resultado. Quando mais de um estado é detectado dentro da mesma
    # sentença, escolhemos o primeiro em ordem alfabética.
    return sorted(mentions)[0]


def _compute_signals_for_match(
    match: Mapping[str, Any], fields: Mapping[str, Mapping[str, Any]]
) -> tuple[dict[str, Any], float]:
    field_name = match.get("field")
    field_info = _resolve_field_info(fields, str(field_name)) if field_name else None

    title_boost = TITLE_BOOST_WEIGHT if field_name == "title" else 0.0
    admin_marker = False
    context_uf = None

    if field_info is not None:
        normalized_text = field_info["normalized_text"]
        offsets: Sequence[int] = field_info["offsets"]  # type: ignore[assignment]
        start = int(match.get("start", 0))
        end = int(match.get("end", start))
        norm_start, norm_end = _get_normalized_span(offsets, start, end)
        admin_marker = _detect_admin_marker(normalized_text, norm_start, norm_end)
        context_uf = _extract_context_uf(field_info["text"], start, end)

    signals = {
        "title_boost": title_boost,
        "admin_marker": admin_marker,
        "context_uf": context_uf,
    }

    base_score = float(match.get("score") or 0.0)
    confidence = base_score + title_boost + (ADMIN_MARKER_WEIGHT if admin_marker else 0.0)
    return signals, confidence


def enrich_matches_with_signals(
    matches: Sequence[Mapping[str, Any]],
    fields: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Anexa sinais derivados aos ``matches`` retornados pelo extrator.

    Cada ocorrência recebe um dicionário ``signals`` contendo os valores
    calculados e um campo ``confidence`` com o score ajustado levando em conta
    os pesos associados a esses sinais.
    """

    enriched: list[dict[str, Any]] = []
    for match in matches:
        match_payload: dict[str, Any] = dict(match)
        existing_signals: MutableMapping[str, Any] = {}
        if isinstance(match.get("signals"), Mapping):
            existing_signals = dict(match["signals"])  # type: ignore[assignment]

        computed_signals, confidence = _compute_signals_for_match(match, fields)
        computed_signals.update(existing_signals)

        match_payload["signals"] = computed_signals
        match_payload["confidence"] = max(confidence, 0.0)
        enriched.append(match_payload)

    return enriched


__all__ = [
    "ADMIN_MARKER_WEIGHT",
    "TITLE_BOOST_WEIGHT",
    "enrich_matches_with_signals",
]
