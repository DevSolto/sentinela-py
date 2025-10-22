from sentinela.services.publications.city_matching import (
    CityMatcher,
    extract_cities_from_article,
)


def test_extract_cities_from_article_tracks_offsets_and_methods():
    catalog = [{"ibge_id": "3550308", "name": "São Paulo", "uf": "SP"}]
    matcher = CityMatcher(catalog)

    article = {
        "title": "Reunião em São Paulo define novos investimentos",
        "body": "Discussões em Vila Imaginária com delegação federal.",
    }

    payload = extract_cities_from_article(article, matcher)

    assert set(payload["fields"].keys()) == {"title", "body"}

    matches = payload["matches"]
    assert len(matches) == 1

    title_match = matches[0]
    assert title_match["city_id"] == "3550308"
    assert title_match["method"] == "automaton"
    assert article["title"][title_match["start"] : title_match["end"]] == "São Paulo"

    title_offsets = payload["fields"]["title"]["offsets"]
    assert title_offsets[title_match["start"]] == title_match["start"]
    assert title_offsets[title_match["end"] - 1] == title_match["end"] - 1

    body_offsets = payload["fields"]["body"]["offsets"]
    assert body_offsets == list(range(len(article["body"])))
