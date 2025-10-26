from datetime import datetime, timezone
from unittest.mock import patch

from sentinela.services.publications.city_matching import (
    CITY_CACHE_VERSION,
    CityMatcher,
)
from sentinela.services.publications.city_matching.extractor import (
    extract_cities_from_article,
)


def _build_matcher() -> CityMatcher:
    catalog = [
        {"ibge_id": "2504009", "name": "Campina Grande", "uf": "PB"},
        {"ibge_id": "3304557", "name": "Rio de Janeiro", "uf": "RJ"},
        {"ibge_id": "3550308", "name": "São Paulo", "uf": "SP"},
    ]
    return CityMatcher(catalog)


def test_extract_cities_from_article_returns_structured_matches() -> None:
    matcher = _build_matcher()
    article = {
        "title": "Campina Grande celebra acordo com Rio de Janeiro",
        "body": "A comitiva de Campina Grande visitará São Paulo amanhã.",
    }
    frozen_now = datetime(2024, 5, 20, 15, 30, tzinfo=timezone.utc)

    with patch(
        "sentinela.services.publications.city_matching.extractor.dt.datetime"
    ) as mock_datetime:
        mock_datetime.now.return_value = frozen_now
        result = extract_cities_from_article(article, matcher)

    assert set(result["fields"].keys()) == {"title", "body"}

    title_info = result["fields"]["title"]
    assert title_info["normalized_text"].startswith("campina grande")
    assert title_info["offsets"][0] == 0

    body_info = result["fields"]["body"]
    assert "campina" in body_info["normalized_text"]
    assert len(body_info["offsets"]) == len(body_info["normalized_text"])

    matches = {}
    for match in result["matches"]:
        key = (match["field"], match["surface"])
        matches[key] = (match["start"], match["end"])
        assert "signals" in match
        assert "confidence" in match
        signals = match["signals"]
        assert isinstance(signals, dict)
        assert {"title_boost", "admin_marker", "context_uf"} <= signals.keys()
        assert isinstance(match["confidence"], float)
    assert matches[("title", "Campina Grande")] == (
        article["title"].index("Campina Grande"),
        article["title"].index("Campina Grande") + len("Campina Grande"),
    )
    assert matches[("title", "Rio de Janeiro")] == (
        article["title"].index("Rio de Janeiro"),
        article["title"].index("Rio de Janeiro") + len("Rio de Janeiro"),
    )
    assert matches[("body", "Campina Grande")] == (
        article["body"].index("Campina Grande"),
        article["body"].index("Campina Grande") + len("Campina Grande"),
    )
    assert matches[("body", "São Paulo")] == (
        article["body"].index("São Paulo"),
        article["body"].index("São Paulo") + len("São Paulo"),
    )

    metadata = result["cities_extraction"]
    assert metadata["version"] == CITY_CACHE_VERSION
    assert metadata["ts"] == frozen_now.isoformat()
    assert metadata["notes"] == []


def test_extract_cities_from_article_falls_back_to_content_field() -> None:
    matcher = _build_matcher()
    article = {
        "title": "Campina Grande anuncia investimentos",
        "content": "O evento terá participação de representantes do Rio de Janeiro.",
    }
    frozen_now = datetime(2024, 6, 1, 10, tzinfo=timezone.utc)

    with patch(
        "sentinela.services.publications.city_matching.extractor.dt.datetime"
    ) as mock_datetime:
        mock_datetime.now.return_value = frozen_now
        result = extract_cities_from_article(article, matcher)

    assert set(result["fields"].keys()) == {"title", "content"}
    assert result["cities_extraction"]["notes"] == ["used_content_field"]

    match_fields = {m["field"] for m in result["matches"]}
    assert match_fields == {"title", "content"}

    content_match = next(m for m in result["matches"] if m["field"] == "content")
    assert "signals" in content_match
    assert "confidence" in content_match
    expected_start = article["content"].index("Rio de Janeiro")
    assert content_match["start"] == expected_start
    assert content_match["end"] == expected_start + len("Rio de Janeiro")
