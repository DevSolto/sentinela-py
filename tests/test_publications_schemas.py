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
        published_at=datetime(2024, 5, 20, 12, tzinfo=timezone.utc),
    )

    article = payload.to_domain()

    assert article.portal_name == payload.portal
    assert article.title == payload.title
    assert article.url == payload.url
    assert article.content == payload.content
    assert article.summary == payload.summary
    assert article.published_at == payload.published_at


def test_article_batch_payload_iterates_domain_articles():
    payload = ArticleBatchPayload(
        articles=[
            ArticlePayload(
                portal="Diário Oficial",
                title="Portaria 1",
                url="https://example.com/articles/1",
                content="Conteúdo 1",
                published_at=datetime(2024, 5, 19, tzinfo=timezone.utc),
            ),
            ArticlePayload(
                portal="Diário Oficial",
                title="Portaria 2",
                url="https://example.com/articles/2",
                content="Conteúdo 2",
                published_at=datetime(2024, 5, 20, tzinfo=timezone.utc),
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
