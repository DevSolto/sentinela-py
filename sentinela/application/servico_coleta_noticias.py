"""Serviço de orquestração da coleta de notícias."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, List

from sentinela.domain import Article
from sentinela.domain.ports import ArticleSink, PortalGateway
from sentinela.domain.repositories import ArticleReadRepository
from sentinela.infrastructure.scraper import Scraper

@dataclass(slots=True)
class CollectionResult:
    """Resumo de uma execução de coleta de notícias."""

    total_new: int
    articles: List[Article]

    def __len__(self) -> int:  # pragma: no cover - compatibilidade com ``len``
        return self.total_new


class NewsCollectorService:
    """Coordena o fluxo de coleta, filtragem e persistência de notícias."""

    def __init__(
        self,
        portal_gateway: PortalGateway,
        article_sink: ArticleSink,
        scraper: Scraper,
        *,
        article_reader: ArticleReadRepository | None = None,
        status_publisher: Callable[[str], None] | None = None,
    ) -> None:
        """Configura o serviço com todas as dependências necessárias.

        Args:
            portal_gateway: Porta de acesso para recuperar portais cadastrados.
            article_sink: Componente responsável por persistir as notícias
                coletadas.
            scraper: Implementação utilizada para realizar a raspagem.
            article_reader: Repositório de leitura usado para consultar
                notícias já armazenadas, quando disponível.
            status_publisher: Callback opcional usado para publicar mensagens
                de status durante a coleta.
        """

        # Permite recuperar dados estruturados de portais cadastrados.
        self._portal_gateway = portal_gateway
        # Envia artigos novos para persistência externa.
        self._article_sink = article_sink
        # Executa a raspagem tanto por data quanto por paginação.
        self._scraper = scraper
        # Repositório de leitura compartilhado com a API de consulta.
        self._article_reader = article_reader
        # Função opcional para acompanhar logs de progresso.
        self._status_publisher = status_publisher

    def with_status_publisher(
        self, publisher: Callable[[str], None] | None
    ) -> "NewsCollectorService":
        """Cria uma nova instância compartilhando dependências e publisher.

        Args:
            publisher: Callback que deve ser utilizado para publicar mensagens
                de status.

        Returns:
            Uma nova instância de ``NewsCollectorService`` reutilizando todas as
            dependências atuais e com o novo ``publisher`` configurado.
        """

        return NewsCollectorService(
            portal_gateway=self._portal_gateway,
            article_sink=self._article_sink,
            scraper=self._scraper,
            article_reader=self._article_reader,
            status_publisher=publisher,
        )

    def _publish_status(
        self,
        message: str,
        status_publisher: Callable[[str], None] | None = None,
    ) -> None:
        """Publica mensagens de status usando o callback configurado."""

        callback = status_publisher or self._status_publisher
        if callback:
            callback(message)

    def collect(
        self,
        portal_name: str,
        start_date: date,
        end_date: date,
        status_publisher: Callable[[str], None] | None = None,
        *,
        keep_articles: bool = True,
        first_page_html_path: Path | None = None,
    ) -> CollectionResult:
        """Coleta notícias para um portal em um intervalo de datas.

        Args:
            portal_name: Nome do portal previamente cadastrado.
            start_date: Data inicial (inclusiva) utilizada para coleta diária.
            end_date: Data final (inclusiva) utilizada para coleta diária.
            status_publisher: Callback opcional para mensagens de progresso
                específicas desta execução.
            keep_articles: Quando ``True`` (padrão), mantém os artigos aceitos
                em memória para retorno. Quando ``False``, apenas o total é
                contabilizado, liberando as instâncias confirmadas logo após a
                persistência.

        Returns:
            Um ``CollectionResult`` com o total de artigos novos e, opcionalmente,
            a lista com as notícias retornadas pelo sink.

        Raises:
            ValueError: Quando o portal não existe ou quando ``start_date`` é
                posterior a ``end_date``.
        """

        if start_date > end_date:
            raise ValueError("start_date must be earlier than end_date")

        portal = self._portal_gateway.get_portal(portal_name)
        if not portal:
            raise ValueError(f"Portal '{portal_name}' not found")

        self._publish_status(
            f"Iniciando coleta para '{portal_name}' entre {start_date} e {end_date}",
            status_publisher,
        )

        collected: List[Article] = []
        total_new = 0
        current = start_date
        seen_urls: set[str] = set()
        # Percorre todas as datas do intervalo executando a raspagem diária.
        while current <= end_date:
            self._publish_status(
                f"Buscando artigos de {current.isoformat()}", status_publisher
            )
            day_articles = self._scraper.collect_for_date(portal, current)
            day_total = len(day_articles)
            # Remove URLs repetidas para evitar gravações duplicadas.
            unique_articles = [
                article for article in day_articles if article.url not in seen_urls
            ]
            for article in unique_articles:
                seen_urls.add(article.url)
            stored_articles_count = 0
            stored_articles_buffer: List[Article] | None = [] if keep_articles else None
            for stored_article in self._article_sink.publish_many(unique_articles):
                stored_articles_count += 1
                if stored_articles_buffer is not None:
                    stored_articles_buffer.append(stored_article)
            if stored_articles_buffer:
                collected.extend(stored_articles_buffer)
            total_new += stored_articles_count
            unique_articles.clear()
            day_articles.clear()
            self._publish_status(
                f"{current.isoformat()}: encontrados {day_total} artigos, "
                f"novos salvos {stored_articles_count}",
                status_publisher,
            )
            current += timedelta(days=1)
        self._publish_status(
            f"Coleta finalizada para '{portal_name}'. Total de novos artigos: {total_new}",
            status_publisher,
        )
        return CollectionResult(total_new=total_new, articles=collected)

    def list_articles(
        self, portal_name: str, start_date: date, end_date: date
    ) -> Iterable[Article]:
        """Recupera artigos persistidos dentro de um intervalo de datas.

        Args:
            portal_name: Nome do portal utilizado como filtro.
            start_date: Data mínima (inclusiva) para os artigos retornados.
            end_date: Data máxima (inclusiva) para os artigos retornados.

        Returns:
            Um iterável com os artigos cadastrados no período informado.

        Raises:
            RuntimeError: Caso o repositório de leitura não tenha sido
                configurado no serviço.
        """

        if not self._article_reader:
            raise RuntimeError("Article reader not configured for listing")
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        return self._article_reader.list_by_period(portal_name, start_dt, end_dt)

    def collect_all_for_portal(
        self,
        portal_name: str,
        start_page: int = 1,
        max_pages: int | None = None,
        min_published_date: date | None = None,
        *,
        keep_articles: bool = True,
        first_page_html_path: Path | None = None,
        status_publisher: Callable[[str], None] | None = None,
    ) -> CollectionResult:
        """Coleta notícias paginadas até atingir os limites informados.

        Args:
            portal_name: Nome do portal cadastrado que será varrido.
            start_page: Página inicial para a coleta paginada (mínimo 1).
            max_pages: Limite opcional de páginas a processar.
            min_published_date: Data mínima opcional para considerar novos
                artigos; itens mais antigos encerram a coleta.
            keep_articles: Indica se os artigos aceitos devem ser mantidos na
                memória até o final da execução. Utilize ``False`` quando
                apenas os contadores forem necessários.
            first_page_html_path: Quando informado, salva o HTML bruto da
                primeira página analisada no caminho indicado.
            status_publisher: Callback opcional para mensagens de status
                durante a coleta paginada.

        Returns:
            Um ``CollectionResult`` com o total de novos artigos e, quando
            solicitado, a lista dos itens confirmados pelo sink.

        Raises:
            ValueError: Quando o portal solicitado não está cadastrado.
        """

        log = logging.getLogger("sentinela.service")
        portal = self._portal_gateway.get_portal(portal_name)
        if not portal:
            raise ValueError(f"Portal '{portal_name}' not found")
        total_new = 0
        total_seen = 0
        total_skipped_in_run = 0
        total_skipped_existing_db = 0
        total_skipped_by_date = 0
        page = max(1, start_page)
        pages_processed = 0
        saved_urls: set[str] = set()
        first_page_dump_reported = False

        def publish(message: str) -> None:
            log.info(message)
            self._publish_status(message, status_publisher)

        publish(
            f"Portal '{portal_name}': iniciando na página {page}"
            + (f" (limite {max_pages})" if max_pages else "")
        )

        all_new: List[Article] = []
        # Realiza a coleta página a página até o limite de páginas ou data mínima.
        while True:
            if max_pages is not None and pages_processed >= max_pages:
                break

            # Coleta apenas uma página usando o scraper existente por paginação.
            current_page = page
            start_ts = time.perf_counter()
            collected = self._scraper.collect_all(
                portal,
                start_page=current_page,
                max_pages=1,
                first_page_html_path=(
                    first_page_html_path if pages_processed == 0 else None
                ),
            )
            elapsed = time.perf_counter() - start_ts
            if not collected:
                publish(
                    f"Portal '{portal_name}': página {current_page} sem itens, encerrando."
                )
                break

            if (
                first_page_html_path
                and not first_page_dump_reported
                and first_page_html_path.exists()
            ):
                publish(
                    "Portal '{portal}': HTML da primeira página salvo em {path}".format(
                        portal=portal_name, path=first_page_html_path
                    )
                )
                first_page_dump_reported = True

            page_seen_raw = len(collected)
            total_seen += page_seen_raw
            # Filtra duplicados existentes no banco e duplicados dentro do mesmo run.
            page_skipped_in_run = 0
            page_skipped_existing_db = 0
            page_skipped_by_date = 0
            stop_due_to_min_date = False

            if min_published_date is not None:
                filtered: List[Article] = []
                for article in collected:
                    if article.published_at.date() < min_published_date:
                        page_skipped_by_date += 1
                        stop_due_to_min_date = True
                        continue
                    filtered.append(article)
                collected = filtered

            batch: List[Article] = []
            for a in collected:
                if a.url in saved_urls:
                    page_skipped_in_run += 1
                    continue
                batch.append(a)
                saved_urls.add(a.url)
            stored_articles_count = 0
            stored_articles_buffer: List[Article] | None = [] if keep_articles else None
            for stored_article in self._article_sink.publish_many(batch):
                stored_articles_count += 1
                if stored_articles_buffer is not None:
                    stored_articles_buffer.append(stored_article)
            page_skipped_existing_db = len(batch) - stored_articles_count
            page_seen_considered = len(batch)
            total_skipped_in_run += page_skipped_in_run
            total_skipped_existing_db += page_skipped_existing_db
            total_skipped_by_date += page_skipped_by_date

            # Salva incrementalmente conforme novas notícias são confirmadas.
            total_new += stored_articles_count
            if keep_articles and stored_articles_buffer:
                all_new.extend(stored_articles_buffer)
            batch.clear()

            publish(
                "Página {page}: itens {page_seen_raw}, considerados {page_seen_considered}, novos {len_new}, "
                "descartados(run) {skip_run}, descartados(db) {skip_db}, descartados(data) {skip_date} | "
                "Tempo {elapsed:.2f}s | Totais: vistos {total_seen}, novos {total_new}, descartados(run) {total_skip_run}, "
                "descartados(db) {total_skip_db}, descartados(data) {total_skip_date}"
                .format(
                    page=current_page,
                    page_seen_raw=page_seen_raw,
                    page_seen_considered=page_seen_considered,
                    len_new=stored_articles_count,
                    skip_run=page_skipped_in_run,
                    skip_db=page_skipped_existing_db,
                    skip_date=page_skipped_by_date,
                    elapsed=elapsed,
                    total_seen=total_seen,
                    total_new=total_new,
                    total_skip_run=total_skipped_in_run,
                    total_skip_db=total_skipped_existing_db,
                    total_skip_date=total_skipped_by_date,
                )
            )
            collected.clear()

            page += 1
            pages_processed += 1

            if stop_due_to_min_date:
                publish(
                    "Portal '{portal}': data mínima {date} atingida na página {page}, encerrando."
                    .format(
                        portal=portal_name,
                        date=min_published_date.isoformat(),
                        page=current_page,
                    )
                )
                break

        publish(
            "Concluído. Páginas: {pages}, vistos: {seen}, novos: {new}, descartados(run): {skip_run}, "
            "descartados(db): {skip_db}, descartados(data): {skip_date}".format(
                pages=pages_processed,
                seen=total_seen,
                new=total_new,
                skip_run=total_skipped_in_run,
                skip_db=total_skipped_existing_db,
                skip_date=total_skipped_by_date,
            )
        )
        saved_urls.clear()
        return CollectionResult(total_new=total_new, articles=all_new)


__all__ = ["CollectionResult", "NewsCollectorService"]
