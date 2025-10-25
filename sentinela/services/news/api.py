"""Aplicação FastAPI com as rotas de coleta de notícias."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import date, datetime

import uvicorn
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from sentinela.domain import Article, CityMention
from sentinela.services.extraction import notify_news_ready
from sentinela.services.news import NewsContainer, build_news_container


class CollectRequest(BaseModel):
    """Parâmetros necessários para iniciar a coleta de notícias."""

    #: Nome do portal previamente cadastrado para coleta.
    portal: str
    #: Data inicial utilizada como filtro de pesquisa.
    start_date: date
    #: Data final opcional; quando omitida utiliza ``start_date``.
    end_date: date | None = None


class CityMentionResponse(BaseModel):
    """Resumo da menção de cidade associada a um artigo."""

    identifier: str
    city_id: str | None = None
    label: str | None = None
    uf: str | None = None
    occurrences: int = 1
    sources: list[str] = Field(default_factory=list)


class ArticleResponse(BaseModel):
    """Representação de um artigo retornado nas rotas de coleta."""

    #: Nome do portal de origem associado ao artigo coletado.
    portal: str
    #: Título obtido na página de detalhe do artigo.
    title: str
    #: Endereço público usado para acessar o artigo.
    url: str
    #: Conteúdo integral do artigo em texto plano.
    content: str
    #: Data e hora de publicação no formato ISO 8601.
    published_at: str
    #: Resumo opcional presente na listagem de notícias.
    summary: str | None = None
    #: Cidades relacionadas ao artigo já identificadas pela pipeline.
    cities: list[CityMentionResponse] = Field(default_factory=list)


class CollectResponse(BaseModel):
    """Resumo da operação de coleta retornado ao cliente."""

    #: Portal utilizado como origem para a coleta.
    portal: str
    #: Quantidade de artigos novos encontrados.
    collected: int
    #: Lista dos artigos coletados durante a operação.
    articles: list[ArticleResponse]


class ExtractionReadyRequest(BaseModel):
    """Payload utilizado para notificar o serviço de extração sobre um artigo."""

    #: Nome do portal responsável pelo artigo enviado para extração.
    portal: str
    #: Título do artigo a ser processado pela extração.
    title: str
    #: URL de onde o artigo pode ser obtido integralmente.
    url: str
    #: Conteúdo do artigo já normalizado.
    content: str
    #: Instante de publicação informado na requisição.
    published_at: str
    #: Resumo opcional enviado junto ao artigo.
    summary: str | None = None
    #: Cidades previamente conhecidas associadas ao artigo.
    cities: list[CityMentionResponse | str] | None = None

    def to_article(self) -> Article:
        """Converte o payload recebido em uma entidade ``Article``."""

        mentions: tuple[CityMention, ...] = ()
        if self.cities:
            converted: list[CityMention] = []
            for item in self.cities:
                if isinstance(item, CityMentionResponse):
                    converted.append(
                        CityMention(
                            identifier=item.identifier,
                            city_id=item.city_id,
                            label=item.label,
                            uf=item.uf,
                            occurrences=item.occurrences,
                            sources=tuple(item.sources),
                        )
                    )
                else:
                    try:
                        converted.append(CityMention.from_raw(item))
                    except ValueError:
                        continue
            mentions = tuple(converted)
        return Article(
            portal_name=self.portal,
            title=self.title,
            url=self.url,
            content=self.content,
            published_at=datetime.fromisoformat(self.published_at),
            summary=self.summary,
            cities=mentions,
        )


def configure_cors(app: FastAPI) -> None:
    """Aplica a configuração padrão de CORS utilizada pelos serviços."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def include_routes(app: FastAPI, container: NewsContainer, *, prefix: str = "") -> None:
    """Registra as rotas de coleta de notícias na aplicação informada."""

    router = APIRouter(prefix=prefix, tags=["Coleta de Notícias"])

    def _map_city_mention(mention: CityMention) -> CityMentionResponse:
        return CityMentionResponse(
            identifier=mention.identifier,
            city_id=mention.city_id,
            label=mention.label,
            uf=mention.uf,
            occurrences=mention.occurrences,
            sources=list(mention.sources),
        )

    def map_article_response(article: Article) -> ArticleResponse:
        return ArticleResponse(
            portal=article.portal_name,
            title=article.title,
            url=article.url,
            content=article.content,
            published_at=article.published_at.isoformat(),
            summary=article.summary,
            cities=[_map_city_mention(mention) for mention in article.cities],
        )

    def handle_value_error(exc: ValueError) -> HTTPException:
        detail = str(exc)
        status = 404 if "not found" in detail.lower() else 400
        return HTTPException(status_code=status, detail=detail)

    @router.post("/collect", response_model=CollectResponse)
    def collect_articles(request: CollectRequest) -> CollectResponse:
        """Executa a coleta síncrona de notícias para o portal informado."""

        try:
            end_date = request.end_date or request.start_date
            result = container.collector_service.collect(
                request.portal, request.start_date, end_date
            )
        except ValueError as exc:
            raise handle_value_error(exc)

        response = CollectResponse(
            portal=request.portal,
            collected=result.total_new,
            articles=[map_article_response(article) for article in result.articles],
        )
        if result.articles:
            notify_news_ready(result.articles)
        return response

    @router.post("/extraction/ready")
    def publish_for_extraction(request: ExtractionReadyRequest) -> dict[str, int]:
        """Encaminha um artigo diretamente para a fila de extração."""

        article = request.to_article()
        notify_news_ready([article])
        return {"queued": 1}

    @router.post("/collect/stream")
    async def collect_articles_stream(
        request: Request, payload: CollectRequest
    ) -> EventSourceResponse:
        """Inicia a coleta e transmite eventos em tempo real via SSE."""

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()

        def push(event: str, data: str) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, {"event": event, "data": data})

        def finish() -> None:
            loop.call_soon_threadsafe(queue.put_nowait, None)

        def status_callback(message: str) -> None:
            push("log", message)

        async def run_collection() -> None:
            try:
                end_date = payload.end_date or payload.start_date
                result = await loop.run_in_executor(
                    None,
                    lambda: container.collector_service.collect(
                        payload.portal,
                        payload.start_date,
                        end_date,
                        status_publisher=status_callback,
                    ),
                )
                response = CollectResponse(
                    portal=payload.portal,
                    collected=result.total_new,
                    articles=[map_article_response(article) for article in result.articles],
                )
                push("summary", json.dumps(response.model_dump()))
            except ValueError as exc:
                push("error", str(exc))
            except Exception:  # pragma: no cover - defensive path
                push(
                    "error",
                    "Erro inesperado durante a coleta de artigos. Verifique os logs do servidor.",
                )
            finally:
                finish()

        task = asyncio.create_task(run_collection())

        async def event_generator():
            try:
                while True:
                    if await request.is_disconnected():
                        task.cancel()
                        break
                    event = await queue.get()
                    if event is None:
                        break
                    yield event
            finally:
                if not task.done():
                    task.cancel()

        return EventSourceResponse(event_generator())

    app.include_router(router)


def create_app() -> FastAPI:
    """Instancia a aplicação com as rotas de coleta configuradas."""

    container = build_news_container()
    app = FastAPI(
        title="Sentinela News API",
        version="1.0.0",
        description="Coleta e monitoramento de notícias em portais cadastrados.",
    )
    configure_cors(app)
    include_routes(app, container)
    return app


def run() -> None:
    """Executa a API de notícias utilizando o Uvicorn."""

    load_dotenv()
    uvicorn.run(
        "sentinela.services.news.api:create_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        factory=True,
    )


__all__ = [
    "CityMentionResponse",
    "ArticleResponse",
    "CollectRequest",
    "CollectResponse",
    "create_app",
    "configure_cors",
    "include_routes",
    "run",
]
