"""Agregador de ocorrências de cidades."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

CONTEXT_MATCH_BONUS = 0.3
CONTEXT_MISMATCH_PENALTY = 0.7
_TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True)
class AggregatedCity:
    city_id: str
    name: str
    uf: str | None
    score: float
    occurrences: int
    admin_markers: int
    title_boost_sum: float
    context_matches: int
    context_mismatches: int
    matches: tuple[Mapping[str, Any], ...]


def _nearly_equal(left: float, right: float) -> bool:
    return abs(left - right) <= _TOLERANCE


def _resolve_catalog(
    catalog: Sequence[Mapping[str, Any]] | Mapping[str, Any]
) -> dict[str, Mapping[str, Any]]:
    if isinstance(catalog, Mapping):
        entries = catalog.get("data", [])
    else:
        entries = catalog
    resolved: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        city_id = entry.get("ibge_id")
        if not city_id:
            continue
        resolved[str(city_id)] = entry
    return resolved


def _prepare_match_payload(match: Mapping[str, Any]) -> Mapping[str, Any]:
    signals = match.get("signals") if isinstance(match.get("signals"), Mapping) else {}
    confidence = float(match.get("confidence") or match.get("score") or 0.0)
    adjusted = confidence
    adjustments: list[Mapping[str, Any]] = []
    return {
        **match,
        "signals": dict(signals),
        "confidence": confidence,
        "adjusted_confidence": adjusted,
        "adjustments": adjustments,
    }


def _context_adjust(
    match_payload: MutableMapping[str, Any],
    city_uf: str | None,
) -> tuple[float, str | None]:
    adjusted = float(match_payload["adjusted_confidence"])
    signals = match_payload.get("signals", {})
    context_uf = None
    if isinstance(signals, Mapping):
        context_uf = signals.get("context_uf")
    if not context_uf or not city_uf:
        return adjusted, None
    if context_uf == city_uf:
        adjusted += CONTEXT_MATCH_BONUS
        match_payload.setdefault("adjustments", []).append(
            {"type": "context_match", "value": CONTEXT_MATCH_BONUS}
        )
        match_payload["adjusted_confidence"] = adjusted
        return adjusted, "match"
    adjusted = max(0.0, adjusted - CONTEXT_MISMATCH_PENALTY)
    match_payload.setdefault("adjustments", []).append(
        {"type": "context_mismatch", "value": -CONTEXT_MISMATCH_PENALTY}
    )
    match_payload["adjusted_confidence"] = adjusted
    return adjusted, "mismatch"


def aggregate_city_mentions(
    matches: Iterable[Mapping[str, Any]],
    catalog: Sequence[Mapping[str, Any]] | Mapping[str, Any],
) -> tuple[AggregatedCity, ...]:
    """Consolida os matches individuais em pontuações por cidade."""

    catalog_by_id = _resolve_catalog(catalog)
    aggregated: dict[str, MutableMapping[str, Any]] = {}

    for raw_match in matches:
        city_id = raw_match.get("city_id") or raw_match.get("candidate_id")
        if not city_id:
            # Menções sem cidade definida são consideradas posteriormente pelo
            # chamador dentro da etapa de desambiguação.
            continue
        city_id = str(city_id)
        catalog_entry = catalog_by_id.get(city_id, {})
        name = str(
            catalog_entry.get("name")
            or raw_match.get("name")
            or raw_match.get("surface")
            or city_id
        )
        uf = catalog_entry.get("uf") or raw_match.get("uf")

        prepared = dict(_prepare_match_payload(raw_match))
        adjusted_confidence, context_status = _context_adjust(prepared, uf)
        prepared["adjusted_confidence"] = adjusted_confidence

        city_payload = aggregated.setdefault(
            city_id,
            {
                "city_id": city_id,
                "name": name,
                "uf": uf,
                "score": 0.0,
                "occurrences": 0,
                "admin_markers": 0,
                "title_boost_sum": 0.0,
                "context_matches": 0,
                "context_mismatches": 0,
                "matches": [],
            },
        )

        city_payload["score"] += adjusted_confidence
        city_payload["occurrences"] += 1

        signals = prepared.get("signals")
        if isinstance(signals, Mapping):
            if signals.get("admin_marker"):
                city_payload["admin_markers"] += 1
            title_boost = float(signals.get("title_boost") or 0.0)
            if title_boost:
                city_payload["title_boost_sum"] += title_boost
            if context_status == "match":
                city_payload["context_matches"] += 1
            elif context_status == "mismatch":
                city_payload["context_mismatches"] += 1

        city_payload["matches"].append(prepared)

    result: list[AggregatedCity] = []
    for payload in aggregated.values():
        result.append(
            AggregatedCity(
                city_id=payload["city_id"],
                name=payload["name"],
                uf=payload.get("uf"),
                score=float(payload["score"]),
                occurrences=int(payload["occurrences"]),
                admin_markers=int(payload["admin_markers"]),
                title_boost_sum=float(payload["title_boost_sum"]),
                context_matches=int(payload["context_matches"]),
                context_mismatches=int(payload["context_mismatches"]),
                matches=tuple(payload["matches"]),
            )
        )
    return tuple(result)


def _register_suppression(
    store: MutableMapping[str, dict[str, Any]],
    record: AggregatedCity,
    reason: str,
    rule: str,
) -> None:
    store.setdefault(
        record.city_id,
        {
            "city_id": record.city_id,
            "name": record.name,
            "uf": record.uf,
            "score": record.score,
            "occurrences": record.occurrences,
            "reason": reason,
            "rule": rule,
        },
    )


def primary_city_selection(
    aggregated: Sequence[AggregatedCity],
) -> tuple[AggregatedCity | None, list[dict[str, Any]]]:
    if not aggregated:
        return None, []

    suppressed: dict[str, dict[str, Any]] = {}
    remaining = list(aggregated)

    # 1) Maior score acumulado
    max_score = max(item.score for item in remaining)
    top = [item for item in remaining if _nearly_equal(item.score, max_score)]
    for item in remaining:
        if item not in top:
            _register_suppression(suppressed, item, "lower_score", "score")
    if len(top) == 1:
        return top[0], list(suppressed.values())
    remaining = top

    # 2) Maior quantidade de marcadores administrativos
    max_admin = max(item.admin_markers for item in remaining)
    top = [item for item in remaining if item.admin_markers == max_admin]
    for item in remaining:
        if item not in top:
            _register_suppression(suppressed, item, "tie_break", "admin_marker")
    if len(top) == 1:
        return top[0], list(suppressed.values())
    remaining = top

    # 3) Maior reforço proveniente do título
    max_title = max(item.title_boost_sum for item in remaining)
    top = [item for item in remaining if _nearly_equal(item.title_boost_sum, max_title)]
    for item in remaining:
        if item not in top:
            _register_suppression(suppressed, item, "tie_break", "title_boost")
    if len(top) == 1:
        return top[0], list(suppressed.values())
    remaining = top

    # 4) Menor quantidade de conflitos de UF
    min_mismatches = min(item.context_mismatches for item in remaining)
    top = [item for item in remaining if item.context_mismatches == min_mismatches]
    for item in remaining:
        if item not in top:
            _register_suppression(suppressed, item, "tie_break", "context_uf")
    if len(top) == 1:
        return top[0], list(suppressed.values())
    remaining = top

    # 5) Maior número de ocorrências
    max_occurrences = max(item.occurrences for item in remaining)
    top = [item for item in remaining if item.occurrences == max_occurrences]
    for item in remaining:
        if item not in top:
            _register_suppression(suppressed, item, "tie_break", "occurrences")
    if len(top) == 1:
        return top[0], list(suppressed.values())
    remaining = top

    # 6) Desempate determinístico pelo identificador
    remaining.sort(key=lambda item: item.city_id)
    selected = remaining[0]
    for item in remaining[1:]:
        _register_suppression(suppressed, item, "tie_break", "city_id")
    return selected, list(suppressed.values())


def aggregate_with_primary_city(
    matches: Iterable[Mapping[str, Any]],
    catalog: Sequence[Mapping[str, Any]] | Mapping[str, Any],
) -> dict[str, Any]:
    matches = tuple(matches)
    aggregated = aggregate_city_mentions(matches, catalog)
    mentioned = sorted(
        aggregated,
        key=lambda item: (
            -item.score,
            -item.admin_markers,
            -item.title_boost_sum,
            item.context_mismatches,
            -item.occurrences,
            item.city_id,
        ),
    )
    primary, suppressed = primary_city_selection(mentioned)

    unresolved: list[dict[str, Any]] = []
    for match in matches:
        city_id = match.get("city_id") or match.get("candidate_id")
        if city_id:
            continue
        unresolved.append(
            {
                "city_id": None,
                "name": match.get("surface"),
                "uf": match.get("uf"),
                "score": float(match.get("confidence") or match.get("score") or 0.0),
                "occurrences": 1,
                "reason": "missing_candidate",
                "rule": "candidate_id",
            }
        )

    suppressed_payload = list(suppressed)
    suppressed_payload.extend(unresolved)

    payload = {
        "primary_city": None,
        "mentioned_cities": tuple(
            {
                "city_id": item.city_id,
                "name": item.name,
                "uf": item.uf,
                "score": item.score,
                "occurrences": item.occurrences,
                "admin_markers": item.admin_markers,
                "title_boost_sum": item.title_boost_sum,
                "context_matches": item.context_matches,
                "context_mismatches": item.context_mismatches,
                "matches": item.matches,
            }
            for item in mentioned
        ),
        "disambiguation": {"suppressed": tuple(suppressed_payload)},
    }

    if primary is not None:
        payload["primary_city"] = {
            "city_id": primary.city_id,
            "name": primary.name,
            "uf": primary.uf,
            "score": primary.score,
            "occurrences": primary.occurrences,
            "admin_markers": primary.admin_markers,
            "title_boost_sum": primary.title_boost_sum,
            "context_matches": primary.context_matches,
            "context_mismatches": primary.context_mismatches,
        }

    return payload


__all__ = [
    "AggregatedCity",
    "CONTEXT_MATCH_BONUS",
    "CONTEXT_MISMATCH_PENALTY",
    "aggregate_city_mentions",
    "aggregate_with_primary_city",
    "primary_city_selection",
]
