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
    assert len(matches) == 2

    title_matches = [match for match in matches if match["field"] == "title"]
    assert len(title_matches) == 1
    title_match = title_matches[0]
    assert title_match["city_id"] == "3550308"
    assert title_match["method"] == "automaton"
    assert article["title"][title_match["start"] : title_match["end"]] == "São Paulo"

    body_matches = [match for match in matches if match["field"] == "body"]
    assert len(body_matches) == 1
    body_match = body_matches[0]
    assert body_match["city_id"] is None
    assert body_match["method"] == "regex"
    assert (
        article["body"][body_match["start"] : body_match["end"]]
        == "Vila Imaginária"
    )

    title_offsets = payload["fields"]["title"]["offsets"]
    assert title_offsets[title_match["start"]] == title_match["start"]
    assert title_offsets[title_match["end"] - 1] == title_match["end"] - 1

    body_offsets = payload["fields"]["body"]["offsets"]
    assert body_offsets[body_match["start"]] == body_match["start"]
    assert body_offsets[body_match["end"] - 1] == body_match["end"] - 1
