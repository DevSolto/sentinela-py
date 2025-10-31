"""Interface de linha de comando para operar o projeto Sentinela."""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
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
from sentinela.services.publications.jobs.geo_enrichment_job import (
    build_geo_enrichment_job,
)
from sentinela.services.publications import build_publications_container

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


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
    collect_all.add_argument(
        "--dump-first-page-html",
        action="store_true",
        help=(
            "Quando informado, salva o HTML bruto da primeira página de listagem "
            "em um arquivo para auditoria"
        ),
    )
    collect_all.add_argument(
        "--dump-first-page-html-path",
        type=Path,
        help=(
            "Caminho do arquivo para salvar o HTML da primeira página. "
            "Padrão: ./audits/<portal>_pagina1_<timestamp>.html"
        ),
    )

    collect_portal = subparsers.add_parser(
        "collect-portal",
        help=(
            "Varre todas as páginas de listagem de um portal até não encontrar mais artigos"
        ),
    )
    collect_portal.add_argument("portal", help="Nome do portal cadastrado")
    collect_portal.add_argument(
        "--dump-first-page-html",
        action="store_true",
        help=(
            "Quando informado, salva o HTML bruto da primeira página de listagem "
            "em um arquivo para auditoria"
        ),
    )
    collect_portal.add_argument(
        "--dump-first-page-html-path",
        type=Path,
        help=(
            "Caminho do arquivo para salvar o HTML da primeira página. "
            "Padrão: ./audits/<portal>_pagina1_<timestamp>.html"
        ),
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
    report_articles.add_argument(
        "--apenas-com-cidades",
        action="store_true",
        help="Gera linhas somente para artigos que mencionem ao menos uma cidade",
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

    geo_enrich = subparsers.add_parser(
        "geo-enrich",
        help="Enriquece geograficamente artigos pendentes no MongoDB",
    )
    geo_enrich.add_argument(
        "--portal",
        type=str,
        help="Limita o processamento a um portal específico",
    )
    geo_enrich.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Quantidade de documentos por lote ao consultar o MongoDB",
    )
    geo_enrich.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa sem persistir alterações, exibindo apenas o resumo",
    )
    geo_enrich.add_argument(
        "--catalog-version",
        default=None,
        help="Versão do catálogo de municípios a utilizar",
    )
    geo_enrich.add_argument(
        "--ensure-complete",
        action="store_true",
        help="Garante o download do catálogo completo quando necessário",
    )
    geo_enrich.add_argument(
        "--minimum-record-count",
        type=int,
        default=5000,
        help="Quantidade mínima de cidades esperada ao validar o catálogo",
    )
    geo_enrich.add_argument(
        "--primary-source",
        default="ibge",
        help="Fonte primária utilizada ao atualizar o catálogo",
    )
    geo_enrich.add_argument(
        "--id-field",
        default="id",
        help="Campo preferencial usado para identificar o artigo",
    )
    geo_enrich.add_argument(
        "--fallback-id",
        action="append",
        default=["url", "_id"],
        help=(
            "Campos adicionais utilizados como fallback para identificar o artigo "
            "quando o campo principal estiver vazio"
        ),
    )
    geo_enrich.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Não inclui o payload completo da extração no documento atualizado",
    )
    geo_enrich.add_argument(
        "--reprocess-existing",
        action="store_true",
        help="Inclui artigos já marcados como geo-enriquecidos no processamento",
    )

    # Nível de log por subcomando (também lê SENTINELA_LOG_LEVEL)
    for sp in (
        register,
        collect,
        list_articles,
        collect_all,
        collect_portal,
        extract_cities,
        geo_enrich,
    ):
        sp.add_argument(
            "--log-level",
            default=None,
            help="Nível de log: DEBUG, INFO, WARNING, ERROR (padrão INFO)",
        )

    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    console = Console()
    level_name = (
        getattr(args, "log_level", None) or os.getenv("SENTINELA_LOG_LEVEL", "INFO")
    )
    handler = RichHandler(console=console, markup=True, rich_tracebacks=True)
    logging.basicConfig(
        level=getattr(logging, str(level_name).upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
        force=True,
    )

    logger = logging.getLogger("sentinela.cli")
    portals_container = build_portals_container()
    news_container = build_news_container()

    if args.command == "register-portal":
        portal = _load_portal_from_json(args.path)
        portals_container.portal_service.register(portal)
        console.print(f"[green]Portal '{portal.name}' cadastrado com sucesso.[/green]")
    elif args.command == "list-portals":
        portals = list(portals_container.portal_service.list_portals())
        if not portals:
            console.print("[yellow]Nenhum portal cadastrado no momento.[/yellow]")
        else:
            for portal in portals:
                console.print(f"[bold]-[/bold] {portal.name}: {portal.base_url}")
    elif args.command == "collect":
        start_date = _parse_date(args.start_date)
        end_date = _parse_date(args.end_date) if args.end_date else start_date
        total_days = (end_date - start_date).days + 1
        day_done_pattern = re.compile(r"^\\d{4}-\\d{2}-\\d{2}:")
        progress_columns = (
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        )
        with Progress(*progress_columns, console=console, transient=True) as progress:
            task_id = progress.add_task(
                f"[cyan]Coletando notícias de '{args.portal}'", total=total_days
            )

            def status_handler(message: str) -> None:
                if day_done_pattern.match(message):
                    progress.advance(task_id)
                progress.console.log(message)

            try:
                result = news_container.collector_service.collect(
                    args.portal,
                    start_date,
                    end_date,
                    status_publisher=status_handler,
                    keep_articles=False,
                )
            except (ValueError, RuntimeError) as exc:
                progress.stop()
                console.print(f"[red]{exc}[/red]")
                return
        console.print(
            f"[green]{result.total_new} novas notícias coletadas para '{args.portal}'.[/green]"
        )
    elif args.command == "list-articles":
        start_date = _parse_date(args.start_date)
        end_date = _parse_date(args.end_date)
        articles = news_container.collector_service.list_articles(
            args.portal, start_date, end_date
        )
        found_any = False
        for article in articles:
            found_any = True
            console.print_json(
                data={
                    "portal": article.portal_name,
                    "titulo": article.title,
                    "url": article.url,
                    "publicado_em": article.published_at.isoformat(),
                }
            )
        if not found_any:
            console.print(
                "[yellow]Nenhum artigo encontrado para os filtros informados.[/yellow]"
            )
    elif args.command == "collect-all":
        min_date = _parse_date(args.min_date) if args.min_date else None
        try:
            dump_path = _prepare_first_page_dump_path(args, args.portal)
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            return
        page_pattern = re.compile(r"^Página \\d+:")
        progress_columns = (
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TaskProgressColumn(),
            TimeElapsedColumn(),
        )
        with Progress(*progress_columns, console=console, transient=True) as progress:
            task_id = progress.add_task(
                f"[cyan]Varredura de '{args.portal}'", total=None, start=False
            )
            started = False

            def status_handler(message: str) -> None:
                nonlocal started
                progress.console.log(message)
                if not started:
                    progress.start_task(task_id)
                    started = True
                if page_pattern.match(message):
                    progress.advance(task_id)

            try:
                result = news_container.collector_service.collect_all_for_portal(
                    args.portal,
                    start_page=args.start_page,
                    max_pages=args.max_pages,
                    min_published_date=min_date,
                    keep_articles=False,
                    first_page_html_path=dump_path,
                    status_publisher=status_handler,
                )
            except (ValueError, RuntimeError) as exc:
                progress.stop()
                console.print(f"[red]{exc}[/red]")
                return
        limit_suffix = f" com limite de {args.max_pages}" if args.max_pages else ""
        console.print(
            f"[green]{result.total_new} novas notícias coletadas em '{args.portal}' "
            f"(páginas iniciando em {args.start_page}{limit_suffix}).[/green]"
        )
        if dump_path and dump_path.exists():
            console.print(f"[blue]HTML da primeira página salvo em '{dump_path}'.[/blue]")
    elif args.command == "collect-portal":
        try:
            dump_path = _prepare_first_page_dump_path(args, args.portal)
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            return
        page_pattern = re.compile(r"^Página \\d+:")
        progress_columns = (
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TaskProgressColumn(),
            TimeElapsedColumn(),
        )
        with Progress(*progress_columns, console=console, transient=True) as progress:
            task_id = progress.add_task(
                f"[cyan]Varrendo todas as páginas de '{args.portal}'", total=None, start=False
            )
            started = False

            def status_handler(message: str) -> None:
                nonlocal started
                progress.console.log(message)
                if not started:
                    progress.start_task(task_id)
                    started = True
                if page_pattern.match(message):
                    progress.advance(task_id)

            try:
                result = news_container.collector_service.collect_all_for_portal(
                    args.portal,
                    keep_articles=False,
                    first_page_html_path=dump_path,
                    status_publisher=status_handler,
                )
            except (ValueError, RuntimeError) as exc:
                progress.stop()
                console.print(f"[red]{exc}[/red]")
                return
        console.print(
            f"[green]{result.total_new} novas notícias coletadas em '{args.portal}' varrendo todas as páginas.[/green]"
        )
        if dump_path and dump_path.exists():
            console.print(f"[blue]HTML da primeira página salvo em '{dump_path}'.[/blue]")
    elif args.command == "report-articles":
        start_date = _parse_date(args.start_date)
        end_date = _parse_date(args.end_date)
        container = build_publications_container()
        output_path = args.output or Path(f"relatorio_{args.portal}.csv")
        articles = container.query_service.list_articles(
            args.portal, start_date, end_date
        )
        incluir_sem_cidades = not args.apenas_com_cidades
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
        progress_columns = (
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TaskProgressColumn(),
            TimeElapsedColumn(),
        )
        with Progress(*progress_columns, console=console, transient=True) as progress:
            task_id = progress.add_task(
                f"[cyan]Gerando relatório para '{args.portal}'", total=None
            )
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
                            progress.advance(task_id)
                    elif incluir_sem_cidades:
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
                        progress.advance(task_id)
                    progress.update(
                        task_id,
                        description=(
                            f"[cyan]Gerando relatório para '{args.portal}' ({rows} linha(s))"
                        ),
                    )
        console.print(
            f"[green]Relatório gerado com {rows} registro(s) em '{output_path}'.[/green]"
        )
    elif args.command == "extract-cities":
        job = build_city_extraction_job()
        with console.status("Executando extração de cidades...", spinner="dots"):
            result = job.run(
                batch_size=args.batch_size,
                force=args.force,
                only_missing=args.only_missing,
                dry_run=args.dry_run,
                portal=args.portal,
            )
        summary = result.to_summary()
        console.print_json(data=summary)
        if args.metrics_file:
            _write_metrics_file(args.metrics_file, summary)
            console.log(f"Métricas salvas em '{args.metrics_file}'.")
        if result.errors:
            logger.warning("Job finalizado com %d erros", len(result.errors))
            sys.exit(1)
    elif args.command == "geo-enrich":
        job = build_geo_enrichment_job(
            catalog_version=args.catalog_version,
            ensure_complete=args.ensure_complete,
            primary_source=args.primary_source,
            minimum_record_count=args.minimum_record_count,
        )
        with console.status("Executando geo-enriquecimento...", spinner="dots"):
            result = job.run(
                batch_size=args.batch_size,
                dry_run=args.dry_run,
                portal=args.portal,
                include_extraction=not args.skip_extraction,
                id_field=args.id_field,
                fallback_ids=args.fallback_id,
                reprocess_existing=args.reprocess_existing,
            )
        payload = result.to_mapping()
        console.print_json(data=payload)
        if result.errors:
            logger.warning("Job finalizado com %d erros", len(result.errors))
            if not args.dry_run:
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


def _prepare_first_page_dump_path(args: argparse.Namespace, portal: str) -> Path | None:
    if not getattr(args, "dump_first_page_html", False):
        return None

    raw_path: Path | None = getattr(args, "dump_first_page_html_path", None)
    if raw_path:
        path = raw_path
    else:
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        path = Path("audits") / f"{portal}_pagina1_{timestamp}.html"

    if not path.is_absolute():
        path = Path.cwd() / path

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"Não foi possível preparar diretório para salvar HTML da primeira página: {exc}"
        ) from exc

    return path


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
