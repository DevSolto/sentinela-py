"""Heurísticas de desambiguação de cidades.

O módulo avalia o conjunto de candidatos retornados pelo gazetteer e aplica
regras contextuais para atribuir um ``status`` e um fator de confiança.
Esse fator representa apenas a parcela de desambiguação e deve ser combinado
com a pontuação do tipo de match (NER, padrão, regex etc.) multiplicando os
dois valores. Documentamos explicitamente os pesos para facilitar calibração
futura.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable, Sequence, Set, TYPE_CHECKING

from .models import CityCandidate

if TYPE_CHECKING:  # pragma: no cover - apenas para anotações
    from .gazetteer import CityRecord


@dataclass(frozen=True, slots=True)
class DisambiguationResult:
    """Resultado da desambiguação de uma menção a cidade."""

    city: "CityRecord" | None
    status: str
    confidence: float
    candidates: tuple[CityCandidate, ...]


_AMBIGUOUS_SURFACES: dict[str, Set[str]] = {
    # Termos que frequentemente aparecem fora de contexto municipal e precisam
    # de reforço (menção de UF) para ganharem alta confiança.
    "natal": {"RN"},
    "esperanca": {"PB"},
    "palmas": {"TO"},
}

_CONFIDENCE_RESOLVED = 0.95
_CONFIDENCE_AMBIGUOUS = 0.5
_CONFIDENCE_UNKNOWN_UF = 0.4
_CONFIDENCE_FOREIGN = 0.2


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize_surface(surface: str) -> str:
    return " ".join(surface.lower().split())


def _make_candidates(entries: Sequence["CityRecord"]) -> tuple[CityCandidate, ...]:
    if not entries:
        return ()
    weight = 1.0 / len(entries)
    return tuple(
        CityCandidate(city_id=entry.id, name=entry.name, uf=entry.uf, score=weight)
        for entry in entries
    )


def _has_reliable_context(
    surface_key: str,
    candidate_uf: str,
    *,
    uf_surface: str | None,
    context_states: Set[str],
) -> bool:
    """Return True when the context gives confidence for ambiguous nomes."""

    ambiguous_states = _AMBIGUOUS_SURFACES.get(surface_key)
    if not ambiguous_states:
        return True

    if uf_surface and uf_surface.upper() in ambiguous_states:
        return True
    if candidate_uf.upper() in context_states:
        return True
    if context_states & {state.upper() for state in ambiguous_states}:
        return True
    return False


def disambiguate_city(
    surface: str,
    candidates: Iterable["CityRecord"],
    *,
    uf_surface: str | None,
    context_states: Iterable[str] | None = None,
) -> DisambiguationResult:
    """Avalia candidatos do gazetteer e define status/confiança.

    As etapas principais são:

    1. Aplicar filtro pela UF explícita (``Cidade-UF`` ou similar) quando
       existente. Caso não exista candidato com essa UF, considera-se o contexto
       insuficiente e retorna ``unknown_uf``.
    2. Usar menções a estados no texto para reduzir a lista.
    3. Para nomes marcados como ambíguos, exigir pelo menos uma indicação de UF
       (no texto ou na superfície) para atingir ``resolved``. Caso contrário o
       status fica ``unknown_uf`` e a confiança reduzida.

    Os fatores de confiança resultantes são combinados com o score do match
    original multiplicando os valores.
    """

    context_set = {state.upper() for state in (context_states or []) if state}
    candidate_list = list(candidates)
    if not candidate_list:
        return DisambiguationResult(
            city=None,
            status="foreign",
            confidence=_CONFIDENCE_FOREIGN,
            candidates=(),
        )

    uf_filtered = list(candidate_list)
    if uf_surface:
        uf_upper = uf_surface.upper()
        filtered = [candidate for candidate in uf_filtered if candidate.uf.upper() == uf_upper]
        if filtered:
            uf_filtered = filtered
        else:
            return DisambiguationResult(
                city=None,
                status="unknown_uf",
                confidence=_CONFIDENCE_UNKNOWN_UF,
                candidates=_make_candidates(uf_filtered),
            )

    if len(uf_filtered) > 1 and context_set:
        context_filtered = [
            candidate for candidate in uf_filtered if candidate.uf.upper() in context_set
        ]
        if context_filtered:
            uf_filtered = context_filtered

    if len(uf_filtered) == 1:
        candidate = uf_filtered[0]
        surface_key = _normalize_surface(_strip_accents(surface))
        if not _has_reliable_context(
            surface_key, candidate.uf, uf_surface=uf_surface, context_states=context_set
        ):
            return DisambiguationResult(
                city=None,
                status="unknown_uf",
                confidence=_CONFIDENCE_UNKNOWN_UF,
                candidates=_make_candidates(uf_filtered),
            )
        return DisambiguationResult(
            city=candidate,
            status="resolved",
            confidence=_CONFIDENCE_RESOLVED,
            candidates=_make_candidates(uf_filtered),
        )

    return DisambiguationResult(
        city=None,
        status="ambiguous",
        confidence=_CONFIDENCE_AMBIGUOUS,
        candidates=_make_candidates(uf_filtered),
    )


__all__ = ["DisambiguationResult", "disambiguate_city"]
