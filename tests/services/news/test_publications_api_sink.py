"""Testes para o cliente que publica artigos na API de publicações."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import httpx

from sentinela.domain import Article
from sentinela.services.news.clients import PublicationsAPISink


class _FailingClient:
    """Cliente HTTP falso que simula falha de conexão."""

    def post(self, *_args, **_kwargs):
        request = httpx.Request("POST", "http://example.com/articles/batch")
        raise httpx.ConnectError("boom", request=request)


@pytest.fixture
def sample_article() -> Article:
    """Cria um artigo mínimo para uso nos testes."""

    return Article(
        portal_name="portal",
        title="título",
        url="https://example.com/artigo",
        content="conteúdo",
        summary=None,
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def test_publish_many_raises_runtime_error_on_connection_failure(sample_article: Article) -> None:
    """Falhas de conexão devem produzir uma mensagem amigável ao usuário."""

    sink = PublicationsAPISink("http://example.com", client=_FailingClient())

    with pytest.raises(RuntimeError) as excinfo:
        list(sink.publish_many([sample_article]))

    assert "Não foi possível conectar ao serviço de publicações" in str(excinfo.value)
