from __future__ import annotations

import pytest

from sentinela.services.publications.city_matching import (
    aggregate_with_primary_city,
    extract_cities_from_article,
)
from sentinela.services.publications.city_matching.geoutils import (
    haversine_distance_km,
)
from sentinela.services.publications.city_matching.matcher import CityMatcher


@pytest.fixture
def sample_catalog():
    capital_a = {
        "ibge_id": "2",
        "name": "Cidade B",
        "uf": "AA",
        "region": "Região Norte",
        "state": "Estado A",
        "intermediate_region": "Intermediária A",
        "immediate_region": "Imediata A",
        "mesoregion": "Mesorregião A",
        "microregion": "Microrregião A",
        "coords": {"lat": -15.0, "lon": -47.0},
        "bbox": {"south": -15.2, "west": -47.2, "north": -14.8, "east": -46.8},
        "capital": True,
    }
    capital_c = {
        "ibge_id": "3",
        "name": "Cidade C",
        "uf": "CC",
        "region": "Região Sul",
        "state": "Estado C",
        "intermediate_region": "Intermediária C",
        "immediate_region": "Imediata C",
        "mesoregion": "Mesorregião C",
        "microregion": "Microrregião C",
        "coords": {"lat": -25.0, "lon": -49.0},
        "bbox": {"south": -25.2, "west": -49.2, "north": -24.8, "east": -48.8},
        "capital": True,
    }

    capital_a_summary = {
        "ibge_id": capital_a["ibge_id"],
        "name": capital_a["name"],
        "uf": capital_a["uf"],
        "coords": capital_a["coords"],
        "bbox": capital_a["bbox"],
    }

    capital_c_summary = {
        "ibge_id": capital_c["ibge_id"],
        "name": capital_c["name"],
        "uf": capital_c["uf"],
        "coords": capital_c["coords"],
        "bbox": capital_c["bbox"],
    }

    city_a = {
        "ibge_id": "1",
        "name": "Cidade A",
        "uf": "AA",
        "region": "Região Norte",
        "state": "Estado A",
        "intermediate_region": "Intermediária A",
        "immediate_region": "Imediata A",
        "mesoregion": "Mesorregião A",
        "microregion": "Microrregião A",
        "coords": {"lat": -10.0, "lon": -45.0},
        "bbox": {"south": -10.2, "west": -45.2, "north": -9.8, "east": -44.8},
        "state_capital": capital_a_summary,
        "ibge_context": {
            "region": "Região Norte",
            "state": "Estado A",
            "intermediate_region": "Intermediária A",
            "immediate_region": "Imediata A",
            "mesoregion": "Mesorregião A",
            "microregion": "Microrregião A",
            "state_capital": capital_a_summary,
        },
    }

    capital_a_enriched = {
        **capital_a,
        "state_capital": capital_a_summary,
        "ibge_context": {
            "region": "Região Norte",
            "state": "Estado A",
            "intermediate_region": "Intermediária A",
            "immediate_region": "Imediata A",
            "mesoregion": "Mesorregião A",
            "microregion": "Microrregião A",
            "state_capital": capital_a_summary,
        },
    }

    capital_c_enriched = {
        **capital_c,
        "state_capital": capital_c_summary,
        "ibge_context": {
            "region": "Região Sul",
            "state": "Estado C",
            "intermediate_region": "Intermediária C",
            "immediate_region": "Imediata C",
            "mesoregion": "Mesorregião C",
            "microregion": "Microrregião C",
            "state_capital": capital_c_summary,
        },
    }

    city_a.setdefault("capital", False)

    return [city_a, capital_a_enriched, capital_c_enriched]


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
        _build_match("2", confidence=2.0, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": "ZZ"}),
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


def test_aggregate_with_primary_city_enriches_context(sample_catalog):
    matches = [
        _build_match("1", confidence=1.2, signals={"admin_marker": True, "title_boost": 0.1, "context_uf": "AA"}),
        _build_match("2", confidence=0.9, signals={"admin_marker": False, "title_boost": 0.0, "context_uf": "AA"}),
    ]

    payload = aggregate_with_primary_city(matches, sample_catalog)

    mentioned = {entry["city_id"]: entry for entry in payload["mentioned_cities"]}
    city_a = mentioned["1"]
    assert city_a["region"] == "Região Norte"
    assert city_a["coords"] == {"lat": -10.0, "lon": -45.0}
    assert city_a["bbox"] == {"south": -10.2, "west": -45.2, "north": -9.8, "east": -44.8}
    assert city_a["ibge_context"]["state_capital"]["ibge_id"] == "2"

    primary = payload["primary_city"]
    assert primary["city_id"] == "1"
    expected_distance = haversine_distance_km(
        sample_catalog[0]["coords"],
        sample_catalog[0]["state_capital"]["coords"],
    )
    assert primary["distance_from_state_capital_km"] == pytest.approx(expected_distance, rel=1e-6)
