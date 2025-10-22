from sentinela.extraction.normalization import normalize_text_with_offsets
from sentinela.services.publications.city_matching import CityMatcher


def test_normalize_text_with_offsets_removes_accents_and_hyphen():
    text = "São-Paulo"
    normalised, offsets = normalize_text_with_offsets(text)
    assert normalised == "sao paulo"
    assert offsets == list(range(len(text)))


def test_city_matcher_detects_catalog_cities_with_correct_offsets():
    catalog = [
        {"ibge_id": "2504009", "name": "Campina Grande", "uf": "PB"},
        {"ibge_id": "3304557", "name": "Rio de Janeiro", "uf": "RJ"},
    ]
    matcher = CityMatcher(catalog)

    text = "Campina Grande firmou acordo com o Rio de Janeiro hoje."
    matches = matcher.find_matches(text)

    assert len(matches) == 2

    first, second = matches

    assert first.city_id == "2504009"
    assert first.name == "Campina Grande"
    assert first.uf == "PB"
    assert first.surface == "Campina Grande"
    assert (first.start, first.end) == (0, 14)
    assert first.method == "automaton"
    assert first.score == 1.0

    assert second.city_id == "3304557"
    assert second.name == "Rio de Janeiro"
    assert second.uf == "RJ"
    assert second.surface == "Rio de Janeiro"
    assert (second.start, second.end) == (35, 49)
    assert second.method == "automaton"
    assert second.score == 1.0


def test_city_matcher_ignores_names_outside_catalog():
    matcher = CityMatcher({"data": []})

    text = "O evento ocorreu em Vila Imaginária na semana passada."
    matches = matcher.find_matches(text)

    assert matches == []


def test_city_matcher_handles_accented_and_unaccented_variants():
    catalog = [
        {
            "ibge_id": "2111300",
            "name": "São Luís",
            "uf": "MA",
            "alt_names": ["Sao Luis", "São Luiz"],
        }
    ]
    matcher = CityMatcher(catalog)

    surfaces = ["São Luís", "Sao Luis"]
    for surface in surfaces:
        text = f"Delegação visita {surface} para assinatura de convênio."
        matches = matcher.find_matches(text)

        assert matches
        match = next(m for m in matches if m.city_id == "2111300")
        assert match.name == "São Luís"
        assert match.uf == "MA"
        assert match.surface == surface
        assert text[match.start : match.end] == surface
        assert match.method == "automaton"
        assert match.score == 1.0


def test_city_matcher_prefers_catalog_city_over_fallback_for_variants():
    catalog = [{"ibge_id": "2111300", "name": "São Luís", "uf": "MA"}]
    matcher = CityMatcher(catalog)

    text = "Prefeitura de Sao Luis amplia vacinação."
    matches = matcher.find_matches(text)

    assert len(matches) == 1
    match = matches[0]
    assert match.city_id == "2111300"
    assert match.surface == "Sao Luis"
    assert match.method == "automaton"


def test_city_matcher_discards_entries_without_ibge_id():
    catalog = [
        {"name": "Cidade Imaginária", "uf": "ZZ"},
        {"ibge_id": "3550308", "name": "São Paulo", "uf": "SP"},
    ]
    matcher = CityMatcher(catalog)

    text = "Reunião em Cidade Imaginária ocorre junto com agenda em São Paulo."
    matches = matcher.find_matches(text)

    assert all(match.city_id for match in matches)
    assert {match.city_id for match in matches} == {"3550308"}


def test_city_matcher_handles_case_and_accent_variations():
    catalog = [{"ibge_id": "3550308", "name": "São Paulo", "uf": "SP"}]
    matcher = CityMatcher(catalog)

    text = "VISITA SAO PAULO CONFIRMADA PARA HOJE."
    matches = matcher.find_matches(text)

    assert len(matches) == 1
    match = matches[0]
    assert match.city_id == "3550308"
    assert match.surface == "SAO PAULO"
