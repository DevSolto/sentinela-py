from __future__ import annotations

import pytest

from sentinela.services.publications.city_matching import (
    aggregate_with_primary_city,
    extract_cities_from_article,
)
from sentinela.services.publications.city_matching.matcher import CityMatcher


@pytest.fixture
def sample_catalog():
    return [
        {"ibge_id": "1", "name": "Cidade A", "uf": "AA"},
        {"ibge_id": "2", "name": "Cidade B", "uf": "BB"},
        {"ibge_id": "3", "name": "Cidade C", "uf": "CC"},
    ]


def _build_match(city_id: str | None, *, confidence: float, signals: dict[str, object] | None = None, score: float | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "city_id": city_id,
        "surface": f"match-{city_id or 'unknown'}",
        "score": score if score is not None else confidence,
        "confidence": confidence,
        "signals": signals or {},
        "field": "body",
        "method": "automaton",
    }
    return payload


def test_signal_generation_from_extractor(sample_catalog):
    matcher = CityMatcher(
        {
            "data": [
                {"ibge_id": "1", "name": "Natal", "uf": "RN"},
                {"ibge_id": "2", "name": "São Paulo", "uf": "SP"},
            ]
        }
    )

    article = {
        "title": "Prefeito de Natal visita São Paulo",
        "body": "O prefeito de Natal (RN) discutiu acordos com representantes paulistas.",
    }

    payload = extract_cities_from_article(article, matcher)
    matches = payload["matches"]

    natal_title = next(
        match for match in matches if match["city_id"] == "1" and match["field"] == "title"
    )
    natal_body = next(
        match for match in matches if match["city_id"] == "1" and match["field"] != "title"
    )
    sao_paulo = next(
        match for match in matches if match["city_id"] == "2" and match["field"] == "title"
    )

    assert pytest.approx(natal_title["confidence"], rel=1e-6) == pytest.approx(1.0 + 0.4 + 0.6)
    assert natal_title["signals"]["admin_marker"] is True
    assert natal_title["signals"]["title_boost"] == pytest.approx(0.4)
    assert natal_title["signals"]["context_uf"] == "SP"

    assert pytest.approx(natal_body["confidence"], rel=1e-6) == pytest.approx(1.0 + 0.6)
    assert natal_body["signals"]["context_uf"] == "RN"

    assert pytest.approx(sao_paulo["confidence"], rel=1e-6) == pytest.approx(1.0 + 0.4 + 0.6)
    assert sao_paulo["signals"]["admin_marker"] is True
    assert sao_paulo["signals"]["context_uf"] == "SP"


def test_aggregator_c1_admin_marker_priority(sample_catalog):
    matches = [
        _build_match("1", confidence=1.0, signals={"admin_marker": True, "title_boost": 0.0, "context_uf": None}),
        _build_match("2", confidence=1.0, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": None}),
    ]

    payload = aggregate_with_primary_city(matches, sample_catalog)
    assert payload["primary_city"]["city_id"] == "1"
    suppressed = {entry["city_id"]: entry for entry in payload["disambiguation"]["suppressed"]}
    assert suppressed["2"]["rule"] == "admin_marker"


def test_aggregator_c2_title_boost_breaks_tie(sample_catalog):
    matches = [
        _build_match("1", confidence=1.0, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": None}),
        _build_match("2", confidence=1.0, signals={"admin_marker": False, "title_boost": 0.4, "context_uf": None}, score=0.6),
    ]

    payload = aggregate_with_primary_city(matches, sample_catalog)
    assert payload["primary_city"]["city_id"] == "2"
    suppressed = {entry["city_id"]: entry for entry in payload["disambiguation"]["suppressed"]}
    assert suppressed["1"]["rule"] == "title_boost"


def test_aggregator_c3_context_mismatch_penalises(sample_catalog):
    matches = [
        _build_match("1", confidence=1.0, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": "AA"}),
        _build_match("2", confidence=2.0, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": "AA"}),
    ]

    payload = aggregate_with_primary_city(matches, sample_catalog)
    assert payload["primary_city"]["city_id"] == "1"
    suppressed = {entry["city_id"]: entry for entry in payload["disambiguation"]["suppressed"]}
    assert suppressed["2"]["rule"] == "context_uf"


def test_aggregator_c4_occurrence_count_breaks_tie(sample_catalog):
    matches = [
        _build_match("1", confidence=1.0, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": None}),
        _build_match("1", confidence=1.0, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": None}),
        _build_match("2", confidence=2.0, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": None}),
    ]

    payload = aggregate_with_primary_city(matches, sample_catalog)
    assert payload["primary_city"]["city_id"] == "1"
    suppressed = {entry["city_id"]: entry for entry in payload["disambiguation"]["suppressed"]}
    assert suppressed["2"]["rule"] == "occurrences"


def test_aggregator_c5_deterministic_city_id_breaks_final_tie(sample_catalog):
    matches = [
        _build_match("1", confidence=1.0, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": None}),
        _build_match("2", confidence=1.0, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": None}),
    ]

    payload = aggregate_with_primary_city(matches, sample_catalog)
    assert payload["primary_city"]["city_id"] == "1"
    suppressed = {entry["city_id"]: entry for entry in payload["disambiguation"]["suppressed"]}
    assert suppressed["2"]["rule"] == "city_id"


def test_aggregator_c6_handles_unresolved_candidates(sample_catalog):
    matches = [
        _build_match(None, confidence=0.7, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": None}),
        _build_match("2", confidence=1.0, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": None}),
    ]

    payload = aggregate_with_primary_city(matches, sample_catalog)
    suppressed = payload["disambiguation"]["suppressed"]
    unresolved = next(entry for entry in suppressed if entry["city_id"] is None)
    assert unresolved["reason"] == "missing_candidate"
    assert payload["primary_city"]["city_id"] == "2"
