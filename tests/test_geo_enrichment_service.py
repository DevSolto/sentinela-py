from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from typing import Iterable

import pytest


@pytest.fixture(scope="module")
def geo_module():
    module_path = Path(__file__).resolve().parents[1] / "packages/@farol/geo-enrichment/__init__.py"
    spec = importlib.util.spec_from_file_location(
        "farol_geo_enrichment",
        module_path,
        submodule_search_locations=[str(module_path.parent)],
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.skip("Não foi possível carregar o módulo de geo enrichment")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_enrich_geo_runs_full_pipeline(geo_module):
    RawMatch = geo_module.RawMatch
    GeoOutput = geo_module.GeoOutput
    enrich_geo = geo_module.enrich_geo

    article = {"id": "art-1"}
    raw_matches: Iterable[RawMatch] = [RawMatch(surface="Natal", candidate_id=None, score=0.6, method="pattern")]

    call_order: list[str] = []

    def load_catalog():
        call_order.append("catalog")
        return [{"ibge_id": "2408102", "name": "Natal"}]

    def apply_signals(matches, article_doc, catalog):
        call_order.append("signals")
        assert article_doc is article
        assert catalog[0]["name"] == "Natal"
        return [replace(match, signals={"title_boost": 0.4}) for match in matches]

    def disambiguate(matches, article_doc, catalog):
        call_order.append("disambiguate")
        assert article_doc is article
        return [replace(match, candidate_id=catalog[0]["ibge_id"]) for match in matches]

    def aggregate(matches, article_doc, catalog):
        call_order.append("aggregate")
        assert isinstance(matches, tuple)
        assert matches[0].candidate_id == catalog[0]["ibge_id"]
        return GeoOutput(
            article_id=article_doc["id"],
            matches=matches,
            mentioned_cities=(),
            disambiguation={"suppressed": ()},
        )

    result = enrich_geo(
        article,
        raw_matches,
        load_catalog=load_catalog,
        apply_signals=apply_signals,
        disambiguate=disambiguate,
        aggregate=aggregate,
    )

    assert isinstance(result, GeoOutput)
    assert call_order == ["catalog", "signals", "disambiguate", "aggregate"]


@pytest.fixture
def catalog_records():
    return [
        {"ibge_id": "2408102", "name": "Natal", "uf": "RN"},
        {"ibge_id": "3550308", "name": "São Paulo", "uf": "SP"},
    ]


@pytest.fixture
def sample_article():
    return {
        "id": "art-42",
        "title": "Prefeito de Natal visita São Paulo",
        "body": "O prefeito de Natal esteve em São Paulo para firmar parcerias.",
    }


def test_enrich_geo_happy_path(geo_module, catalog_records, sample_article):
    RawMatch = geo_module.RawMatch
    GeoOutput = geo_module.GeoOutput
    enrich_geo = geo_module.enrich_geo

    raw_matches = [
        RawMatch(surface="Natal", candidate_id=None, score=0.5, method="pattern"),
        RawMatch(surface="São Paulo", candidate_id=None, score=0.2, method="automaton"),
    ]

    def load_catalog():
        return catalog_records

    def apply_signals(matches, article_doc, catalog):
        boosted = []
        for match in matches:
            boost = 0.3 if match.surface in article_doc["title"] else 0.0
            boosted.append(
                replace(
                    match,
                    score=match.score + boost,
                    signals={**match.signals, "title_boost": boost},
                )
            )
        return boosted

    def disambiguate(matches, article_doc, catalog):
        catalog_by_name = {entry["name"]: entry["ibge_id"] for entry in catalog}
        return [replace(match, candidate_id=catalog_by_name.get(match.surface)) for match in matches]

    def aggregate(matches, article_doc, catalog):
        catalog_by_id = {entry["ibge_id"]: entry for entry in catalog}
        mentioned = []
        for match in matches:
            entry = catalog_by_id.get(match.candidate_id)
            if entry is None:
                continue
            payload = {
                "city_id": entry["ibge_id"],
                "name": entry["name"],
                "uf": entry["uf"],
                "surface": match.surface,
                "score": match.confidence or match.score,
                "signals": match.signals,
            }
            mentioned.append(payload)
        return GeoOutput(
            article_id=article_doc["id"],
            matches=matches,
            primary_city=mentioned[0] if mentioned else None,
            mentioned_cities=tuple(mentioned),
            disambiguation={"suppressed": ()},
            metadata={"catalog_size": len(catalog)},
        )

    output = enrich_geo(
        sample_article,
        raw_matches,
        load_catalog=load_catalog,
        apply_signals=apply_signals,
        disambiguate=disambiguate,
        aggregate=aggregate,
    )

    assert output.article_id == sample_article["id"]
    assert len(output.matches) == 2
    assert {city["city_id"] for city in output.mentioned_cities} == {
        "2408102",
        "3550308",
    }
    assert output.metadata == {"catalog_size": len(catalog_records)}
