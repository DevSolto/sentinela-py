"""Interface de linha de comando para operar o projeto Sentinela."""
from __future__ import annotations

import argparse
import logging
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sentinela.domain import Portal, PortalSelectors, Selector
from sentinela.services.news import build_news_container
from sentinela.services.portals import build_portals_container


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sentinela - coletor de notícias")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser(
        "register-portal", help="Registra um novo portal a partir de um arquivo JSON"
    )
    register.add_argument("path", type=Path, help="Caminho para o arquivo JSON")

    subparsers.add_parser("list-portals", help="Lista todos os portais cadastrados")

    collect = subparsers.add_parser(
        "collect", help="Coleta notícias para um portal em um intervalo de datas"
    )
    collect.add_argument("portal", help="Nome do portal cadastrado")
    collect.add_argument("start_date", help="Data inicial no formato YYYY-MM-DD")
    collect.add_argument(
        "end_date",
        nargs="?",
        help="Data final no formato YYYY-MM-DD. Se omitida usa a data inicial.",
    )

    list_articles = subparsers.add_parser(
        "list-articles", help="Lista notícias coletadas para um portal"
    )
    list_articles.add_argument("portal", help="Nome do portal cadastrado")
    list_articles.add_argument("start_date", help="Data inicial no formato YYYY-MM-DD")
    list_articles.add_argument("end_date", help="Data final no formato YYYY-MM-DD")

    collect_all = subparsers.add_parser(
        "collect-all", help="Coleta notícias em todas as páginas de um portal"
    )
    collect_all.add_argument("portal", help="Nome do portal cadastrado")
    collect_all.add_argument(
        "--start-page", type=int, default=1, help="Página inicial (default: 1)"
    )
    collect_all.add_argument(
        "--max-pages", type=int, default=None, help="Limite de páginas a varrer"
    )
    collect_all.add_argument(
        "--min-date",
        default=None,
        help="Data mínima dos artigos no formato YYYY-MM-DD (inclusive)",
    )

    # Nível de log por subcomando (também lê SENTINELA_LOG_LEVEL)
    for sp in (register, collect, list_articles, collect_all):
        sp.add_argument(
            "--log-level",
            default=None,
            help="Nível de log: DEBUG, INFO, WARNING, ERROR (padrão INFO)",
        )

    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    level_name = (
        getattr(args, "log_level", None) or os.getenv("SENTINELA_LOG_LEVEL", "INFO")
    )
    logging.basicConfig(
        level=getattr(logging, str(level_name).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    portals_container = build_portals_container()
    news_container = build_news_container()

    if args.command == "register-portal":
        portal = _load_portal_from_json(args.path)
        portals_container.portal_service.register(portal)
        print(f"Portal '{portal.name}' cadastrado com sucesso.")
    elif args.command == "list-portals":
        for portal in portals_container.portal_service.list_portals():
            print(f"- {portal.name}: {portal.base_url}")
    elif args.command == "collect":
        start_date = _parse_date(args.start_date)
        end_date = _parse_date(args.end_date) if args.end_date else start_date
        try:
            articles = news_container.collector_service.collect(
                args.portal, start_date, end_date
            )
        except ValueError as exc:
            print(str(exc))
            return
        print(f"{len(articles)} novas notícias coletadas para '{args.portal}'.")
    elif args.command == "list-articles":
        start_date = _parse_date(args.start_date)
        end_date = _parse_date(args.end_date)
        for article in news_container.collector_service.list_articles(
            args.portal, start_date, end_date
        ):
            print(
                json.dumps(
                    {
                        "portal": article.portal_name,
                        "titulo": article.title,
                        "url": article.url,
                        "publicado_em": article.published_at.isoformat(),
                    },
                    ensure_ascii=False,
                )
            )
    elif args.command == "collect-all":
        min_date = _parse_date(args.min_date) if args.min_date else None
        new_articles = news_container.collector_service.collect_all_for_portal(
            args.portal,
            start_page=args.start_page,
            max_pages=args.max_pages,
            min_published_date=min_date,
        )
        print(
            f"{len(new_articles)} novas notícias coletadas em '{args.portal}' (páginas iniciando em {args.start_page}{' com limite de ' + str(args.max_pages) if args.max_pages else ''})."
        )
    else:
        raise ValueError(f"Comando desconhecido: {args.command}")


def _parse_date(value: str) -> datetime.date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(
            "Datas devem estar no formato YYYY-MM-DD"
        ) from exc


def _load_portal_from_json(path: Path) -> Portal:
    data = json.loads(path.read_text(encoding="utf-8"))
    selectors = data["selectors"]
    portal_selectors = PortalSelectors(
        listing_article=_build_selector(selectors["listing_article"]),
        listing_title=_build_selector(selectors["listing_title"]),
        listing_url=_build_selector(selectors["listing_url"]),
        article_content=_build_selector(selectors["article_content"]),
        article_date=_build_selector(selectors["article_date"]),
        listing_summary=_build_selector(selectors["listing_summary"])
        if selectors.get("listing_summary")
        else None,
    )

    return Portal(
        name=data["name"],
        base_url=data["base_url"],
        listing_path_template=data["listing_path_template"],
        selectors=portal_selectors,
        headers=data.get("headers", {}),
        date_format=data.get("date_format", "%Y-%m-%d"),
    )


def _build_selector(data: dict[str, Any]) -> Selector:
    return Selector(query=data["query"], attribute=data.get("attribute"))


if __name__ == "__main__":
    main()
