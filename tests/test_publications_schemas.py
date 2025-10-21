from datetime import datetime, timezone

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
    assert article.cities == ("São Paulo", "Campinas")


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
    assert [article.cities for article in domain_articles] == [
        ("São Paulo",),
        ("Campinas",),
    ]
    assert [article.classification for article in domain_articles] == [
        "portaria",
        "decreto",
    ]
