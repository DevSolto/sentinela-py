"""Interface de linha de comando para operar o projeto Sentinela."""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sentinela.domain import Portal, PortalSelectors, Selector
from sentinela.services.news import build_news_container
from sentinela.services.portals import build_portals_container
from sentinela.services.publications.jobs.city_extraction_job import (
    build_default_job as build_city_extraction_job,
)
from sentinela.services.publications import build_publications_container


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

    report_articles = subparsers.add_parser(
        "report-articles",
        help=(
            "Gera um relatório CSV com dados dos artigos e das cidades associadas"
        ),
    )
    report_articles.add_argument(
        "portal", help="Nome do portal (blog) cadastrado para filtragem"
    )
    report_articles.add_argument(
        "start_date", help="Data inicial no formato YYYY-MM-DD"
    )
    report_articles.add_argument(
        "end_date", help="Data final no formato YYYY-MM-DD"
    )
    report_articles.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Caminho para salvar o relatório CSV (padrão: relatorio_<portal>.csv)"
        ),
    )

    extract_cities = subparsers.add_parser(
        "extract-cities",
        help="Extrai e atualiza as cidades mencionadas nos artigos coletados",
    )
    extract_cities.add_argument(
        "--portal",
        type=str,
        help="Limita o processamento a um portal específico",
    )
    extract_cities.add_argument(
        "--force",
        action="store_true",
        help="Reprocessa artigos mesmo quando não há mudanças detectadas",
    )
    extract_cities.add_argument(
        "--only-missing",
        action="store_true",
        help="Limita o processamento a artigos sem hash de extração registrado",
    )
    extract_cities.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Quantidade de documentos por página ao consultar o MongoDB",
    )
    extract_cities.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa sem persistir alterações, exibindo apenas o resumo",
    )
    extract_cities.add_argument(
        "--metrics-file",
        type=Path,
        help="Exporta o resumo final para um arquivo JSON",
    )

    # Nível de log por subcomando (também lê SENTINELA_LOG_LEVEL)
    for sp in (register, collect, list_articles, collect_all, extract_cities):
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
    elif args.command == "report-articles":
        start_date = _parse_date(args.start_date)
        end_date = _parse_date(args.end_date)
        container = build_publications_container()
        output_path = args.output or Path(f"relatorio_{args.portal}.csv")
        articles = container.query_service.list_articles(
            args.portal, start_date, end_date
        )
        fieldnames = [
            "portal",
            "titulo",
            "url",
            "conteudo",
            "publicado_em",
            "resumo",
            "classificacao",
            "cidade",
            "cidade_id",
            "uf",
            "ocorrencias",
            "fontes",
        ]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rows = 0
        with output_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            for article in articles:
                base_payload = {
                    "portal": article.portal_name,
                    "titulo": article.title,
                    "url": article.url,
                    "conteudo": article.content,
                    "publicado_em": article.published_at.isoformat(),
                    "resumo": article.summary or "",
                    "classificacao": article.classification or "",
                }
                if article.cities:
                    for city in article.cities:
                        writer.writerow(
                            {
                                **base_payload,
                                "cidade": city.label or city.identifier or "",
                                "cidade_id": city.city_id or "",
                                "uf": city.uf or "",
                                "ocorrencias": city.occurrences,
                                "fontes": ", ".join(city.sources),
                            }
                        )
                        rows += 1
                else:
                    writer.writerow(
                        {
                            **base_payload,
                            "cidade": "",
                            "cidade_id": "",
                            "uf": "",
                            "ocorrencias": "",
                            "fontes": "",
                        }
                    )
                    rows += 1
        print(
            f"Relatório gerado com {rows} registro(s) em '{output_path}'."
        )
    elif args.command == "extract-cities":
        job = build_city_extraction_job()
        result = job.run(
            batch_size=args.batch_size,
            force=args.force,
            only_missing=args.only_missing,
            dry_run=args.dry_run,
            portal=args.portal,
        )
        summary = result.to_summary()
        print(json.dumps(summary, ensure_ascii=False))
        if args.metrics_file:
            _write_metrics_file(args.metrics_file, summary)
        if result.errors:
            logging.getLogger("sentinela.cli").warning(
                "Job finalizado com %d erros", len(result.errors)
            )
            sys.exit(1)
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


def _write_metrics_file(path: Path, summary: dict[str, Any]) -> None:
    try:
        with path.open("w", encoding="utf-8") as stream:
            json.dump(summary, stream, ensure_ascii=False)
            stream.write("\n")
    except OSError as exc:
        logging.getLogger("sentinela.cli").error(
            "Falha ao escrever métricas em %s: %s", path, exc
        )


if __name__ == "__main__":
    main()
