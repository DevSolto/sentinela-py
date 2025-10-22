from datetime import datetime, timezone

from sentinela.domain import CityMention
from sentinela.services.publications.schemas import (
    ArticleBatchPayload,
    ArticlePayload,
)


def test_article_payload_to_domain_converts_all_fields():
    payload = ArticlePayload(
        portal="Diário Oficial",
        title="Portaria publicada",
        url="https://example.com/articles/1",
        content="Conteúdo da portaria",
        summary="Resumo curto",
        classification="portaria",
        published_at=datetime(2024, 5, 20, 12, tzinfo=timezone.utc),
        cities=["São Paulo", "Campinas"],
    )

    article = payload.to_domain()

    assert article.portal_name == payload.portal
    assert article.title == payload.title
    assert article.url == payload.url
    assert article.content == payload.content
    assert article.summary == payload.summary
    assert article.classification == payload.classification
    assert article.published_at == payload.published_at
    assert [mention.identifier for mention in article.cities] == [
        "São Paulo",
        "Campinas",
    ]
    assert [mention.label for mention in article.cities] == [
        "São Paulo",
        "Campinas",
    ]


def test_article_batch_payload_iterates_domain_articles():
    payload = ArticleBatchPayload(
        articles=[
            ArticlePayload(
                portal="Diário Oficial",
                title="Portaria 1",
                url="https://example.com/articles/1",
                content="Conteúdo 1",
                published_at=datetime(2024, 5, 19, tzinfo=timezone.utc),
                classification="portaria",
                cities=["São Paulo"],
            ),
            ArticlePayload(
                portal="Diário Oficial",
                title="Portaria 2",
                url="https://example.com/articles/2",
                content="Conteúdo 2",
                published_at=datetime(2024, 5, 20, tzinfo=timezone.utc),
                classification="decreto",
                cities=["Campinas"],
            ),
        ]
    )

    domain_articles = list(payload.to_domain())

    assert len(domain_articles) == 2
    assert [article.title for article in domain_articles] == [
        "Portaria 1",
        "Portaria 2",
    ]
    assert all(article.portal_name == "Diário Oficial" for article in domain_articles)
    assert [
        [mention.identifier for mention in article.cities]
        for article in domain_articles
    ] == [["São Paulo"], ["Campinas"]]
    assert [article.classification for article in domain_articles] == [
        "portaria",
        "decreto",
    ]


def test_article_payload_accepts_structured_city_mentions():
    mention_mapping = CityMention(
        identifier="4205407",
        city_id="4205407",
        label="Florianópolis",
        uf="SC",
        occurrences=2,
        sources=("ner", "pattern"),
    ).to_mapping()

    payload = ArticlePayload(
        portal="Diário Oficial",
        title="Portaria estruturada",
        url="https://example.com/articles/3",
        content="Conteúdo rico",
        published_at=datetime(2024, 5, 21, tzinfo=timezone.utc),
        cities=[mention_mapping],
        cities_extraction={"version": "v1"},
    )

    article = payload.to_domain()

    assert len(article.cities) == 1
    mention = article.cities[0]
    assert mention.identifier == "4205407"
    assert mention.city_id == "4205407"
    assert mention.label == "Florianópolis"
    assert mention.uf == "SC"
    assert mention.occurrences == 2
    assert set(mention.sources) == {"ner", "pattern"}
    assert article.cities_extraction == {"version": "v1"}
