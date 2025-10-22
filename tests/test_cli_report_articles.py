from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

import pytest

from sentinela import cli


@dataclass
class _City:
    label: str | None = None
    identifier: str | None = None
    city_id: str | None = None
    uf: str | None = None
    occurrences: int = 0
    sources: tuple[str, ...] = ()


@dataclass
class _Article:
    portal_name: str
    title: str
    url: str
    content: str
    published_at: datetime
    summary: str | None = None
    classification: str | None = None
    cities: Iterable[_City] = ()


class _QueryService:
    def __init__(self, articles: list[_Article]) -> None:
        self._articles = articles

    def list_articles(self, *_args, **_kwargs):
        return self._articles


@pytest.fixture(autouse=True)
def _noop_load_dotenv(monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)


def test_report_articles_exports_full_content(tmp_path: Path, monkeypatch, capsys):
    output = tmp_path / "relatorio.csv"
    article = _Article(
        portal_name="Portal X",
        title="Notícia",
        url="https://exemplo.com/artigo",
        content="conteúdo integral do artigo",
        published_at=datetime(2024, 1, 2, 12, 0, 0),
        summary="Resumo",
        classification="Categoria",
        cities=[
            _City(
                label="Cidade Y",
                identifier="cidade-y",
                city_id="123",
                uf="PE",
                occurrences=2,
                sources=("titulo", "corpo"),
            )
        ],
    )

    fake_publications_container = SimpleNamespace(
        query_service=_QueryService([article])
    )

    monkeypatch.setattr(cli, "build_portals_container", lambda: SimpleNamespace())
    monkeypatch.setattr(cli, "build_news_container", lambda: SimpleNamespace())
    monkeypatch.setattr(
        cli,
        "build_publications_container",
        lambda: fake_publications_container,
    )

    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "sentinela-cli",
            "report-articles",
            "Portal X",
            "2024-01-01",
            "2024-01-31",
            "--output",
            str(output),
        ],
    )

    cli.main()

    captured = capsys.readouterr()
    assert "Relatório gerado com 1 registro(s)" in captured.out

    with output.open(encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)

    assert reader.fieldnames is not None
    assert "conteudo" in reader.fieldnames
    assert rows[0]["conteudo"] == "conteúdo integral do artigo"


def test_report_articles_allows_filtering_only_with_cities(
    tmp_path: Path, monkeypatch, capsys
):
    output = tmp_path / "relatorio.csv"
    with_city = _Article(
        portal_name="Portal X",
        title="Notícia",
        url="https://exemplo.com/artigo",
        content="conteúdo com cidade",
        published_at=datetime(2024, 1, 2, 12, 0, 0),
        cities=[_City(label="Cidade Y", occurrences=1, sources=("titulo",))],
    )
    without_city = _Article(
        portal_name="Portal X",
        title="Notícia sem cidade",
        url="https://exemplo.com/sem-cidade",
        content="conteúdo sem menções",
        published_at=datetime(2024, 1, 3, 12, 0, 0),
        cities=[],
    )

    fake_publications_container = SimpleNamespace(
        query_service=_QueryService([with_city, without_city])
    )

    monkeypatch.setattr(cli, "build_portals_container", lambda: SimpleNamespace())
    monkeypatch.setattr(cli, "build_news_container", lambda: SimpleNamespace())
    monkeypatch.setattr(
        cli,
        "build_publications_container",
        lambda: fake_publications_container,
    )

    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "sentinela-cli",
            "report-articles",
            "Portal X",
            "2024-01-01",
            "2024-01-31",
            "--output",
            str(output),
            "--apenas-com-cidades",
        ],
    )

    cli.main()

    captured = capsys.readouterr()
    assert "Relatório gerado com 1 registro(s)" in captured.out

    with output.open(encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["titulo"] == "Notícia"
    assert rows[0]["cidade"] == "Cidade Y"
