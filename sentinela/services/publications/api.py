"""Aplicação FastAPI responsável por leitura e ingestão de publicações."""
from __future__ import annotations

import os
from datetime import date
from typing import Iterable

import uvicorn
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sentinela.services.publications import (
    PublicationsContainer,
    build_publications_container,
)
from sentinela.services.publications.domain import Article, CityMention
from sentinela.services.publications.adapters import create_ingestion_router


class EnrichedCandidateResponse(BaseModel):
    """Representa um candidato de cidade retornado pelo pipeline de extração."""

    #: Identificador único da cidade candidato no cadastro oficial.
    city_id: str
    #: Nome canônico da cidade correspondente ao candidato.
    name: str
    #: Unidade federativa associada ao registro.
    uf: str
    #: Pontuação que indica a confiança na correspondência encontrada.
    score: float


class EnrichedCityResponse(BaseModel):
    """Agregação das ocorrências de cidades enriquecidas pela extração."""

    #: Código IBGE ou identificador interno da cidade reconhecida.
    city_id: str | None
    #: Trecho exato do texto associado à ocorrência.
    surface: str
    #: Posição inicial do trecho no corpo do artigo.
    start: int
    #: Posição final do trecho no corpo do artigo.
    end: int
    #: Frase completa utilizada para exibir o contexto.
    sentence: str
    #: Situação da classificação atribuída à ocorrência.
    status: str
    #: UF citada diretamente no texto, quando disponível.
    uf_surface: str | None
    #: Método responsável por identificar a ocorrência.
    method: str
    #: Nível de confiança calculado para a detecção da cidade.
    confidence: float
    #: Lista de candidatos avaliados para determinar a melhor cidade.
    candidates: list[EnrichedCandidateResponse]


class EnrichedPersonResponse(BaseModel):
    """Estrutura que descreve pessoas encontradas na etapa de extração."""

    #: Identificador canônico da pessoa encontrada.
    person_id: str
    #: Nome padronizado utilizado para exibir a pessoa.
    canonical_name: str
    #: Trecho exato do texto associado à ocorrência.
    surface: str
    #: Posição inicial do trecho no corpo do artigo.
    start: int
    #: Posição final do trecho no corpo do artigo.
    end: int
    #: Frase completa utilizada para exibir o contexto.
    sentence: str
    #: Método responsável por identificar a pessoa.
    method: str
    #: Nível de confiança calculado para a detecção da pessoa.
    confidence: float


class EnrichedArticleResponse(BaseModel):
    """Coleção de entidades enriquecidas vinculadas a um artigo."""

    #: URL do artigo processado pela pipeline de extração.
    url: str
    #: Versão do modelo de NER utilizado na análise.
    ner_version: str
    #: Versão do gazetteer aplicada durante o enriquecimento.
    gazetteer_version: str
    #: Data e hora em que o enriquecimento foi atualizado.
    updated_at: str
    #: Relação de pessoas encontradas no artigo analisado.
    people: list[EnrichedPersonResponse]
    #: Relação de cidades encontradas no artigo analisado.
    cities: list[EnrichedCityResponse]


class CityMentionResponse(BaseModel):
    """Resumo das cidades associadas ao artigo consultado."""

    #: Identificador utilizado para filtros e compatibilidade com o legado.
    identifier: str
    #: Código oficial associado à cidade, quando disponível.
    city_id: str | None = None
    #: Nome canônico ou rótulo utilizado para exibir a cidade.
    label: str | None = None
    #: Unidade federativa inferida para a cidade.
    uf: str | None = None
    #: Quantidade de ocorrências agregadas no artigo.
    occurrences: int = 1
    #: Métodos responsáveis por identificar a cidade no texto.
    sources: list[str] = Field(default_factory=list)


class ArticleResponse(BaseModel):
    """Representação pública de um artigo armazenado."""

    #: Nome do portal responsável pela publicação do artigo.
    portal: str
    #: Título exibido quando o artigo foi coletado.
    title: str
    #: Endereço do conteúdo completo disponível para o leitor.
    url: str
    #: Conteúdo do artigo em texto para consulta.
    content: str
    #: Data de publicação do artigo em formato ISO.
    published_at: str
    #: Resumo opcional para facilitar a leitura rápida.
    summary: str | None = None
    #: Classificação atribuída ao artigo após enriquecimento.
    classification: str | None = None
    #: Cidades associadas ao artigo após coleta ou enriquecimento.
    cities: list[CityMentionResponse] = Field(default_factory=list)


def configure_cors(app: FastAPI) -> None:
    """Configura o CORS padrão utilizado pelos serviços do Sentinela."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def include_routes(
    app: FastAPI, container: PublicationsContainer, *, prefix: str = ""
) -> None:
    """Registra rotas de consulta e ingestão de publicações na aplicação."""

    router = APIRouter(prefix=prefix, tags=["Publicações"])

    def map_enriched(result) -> EnrichedArticleResponse:
        return EnrichedArticleResponse(
            url=result.url,
            ner_version=result.ner_version,
            gazetteer_version=result.gazetteer_version,
            updated_at=result.updated_at.isoformat(),
            people=[
                EnrichedPersonResponse(
                    person_id=occ.person_id,
                    canonical_name=occ.canonical_name,
                    surface=occ.surface,
                    start=occ.start,
                    end=occ.end,
                    sentence=occ.sentence,
                    method=occ.method,
                    confidence=occ.confidence,
                )
                for occ in result.people
            ],
            cities=[
                EnrichedCityResponse(
                    city_id=occ.city_id,
                    surface=occ.surface,
                    start=occ.start,
                    end=occ.end,
                    sentence=occ.sentence,
                    status=occ.status,
                    uf_surface=occ.uf_surface,
                    method=occ.method,
                    confidence=occ.confidence,
                    candidates=[
                        EnrichedCandidateResponse(
                            city_id=candidate.city_id,
                            name=candidate.name,
                            uf=candidate.uf,
                            score=candidate.score,
                        )
                        for candidate in occ.candidates
                    ],
                )
                for occ in result.cities
            ],
        )

    @router.get("/enriched/articles", response_model=list[EnrichedArticleResponse])
    def list_enriched_articles() -> list[EnrichedArticleResponse]:
        """Lista os resultados enriquecidos disponíveis no armazenamento."""

        return [map_enriched(result) for result in container.extraction_store.list()]

    @router.get("/enriched/articles/{url:path}", response_model=EnrichedArticleResponse)
    def get_enriched_article(url: str) -> EnrichedArticleResponse:
        """Obtém o enriquecimento associado à URL informada."""

        result = container.extraction_store.get(url)
        if not result:
            raise HTTPException(status_code=404, detail="Resultado não encontrado")
        return map_enriched(result)

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
            classification=article.classification,
            cities=[_map_city_mention(mention) for mention in article.cities],
        )

    @router.get("/articles", response_model=list[ArticleResponse])
    def list_articles(
        portal: str,
        start_date: date,
        end_date: date,
        city: str | None = None,
    ) -> Iterable[ArticleResponse]:
        """Lista artigos por portal dentro do intervalo de datas informado."""

        if start_date > end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date deve ser anterior ou igual a end_date",
            )
        articles = container.query_service.list_articles(
            portal, start_date, end_date, city=city
        )
        return [map_article_response(article) for article in articles]

    app.include_router(router)
    ingestion_router = create_ingestion_router(container.article_repository)
    app.include_router(ingestion_router, prefix=prefix)


def create_app() -> FastAPI:
    """Instancia a aplicação com as rotas de publicações configuradas."""

    container = build_publications_container()
    app = FastAPI(
        title="Sentinela Publications API",
        version="1.0.0",
        description="Consulta de artigos coletados pelos serviços do Sentinela.",
    )
    configure_cors(app)
    include_routes(app, container)
    return app


def run() -> None:
    """Executa a API de publicações usando o Uvicorn."""

    load_dotenv()
    uvicorn.run(
        "sentinela.services.publications.api:create_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        factory=True,
    )


__all__ = [
    "CityMentionResponse",
    "ArticleResponse",
    "EnrichedArticleResponse",
    "EnrichedCandidateResponse",
    "EnrichedCityResponse",
    "EnrichedPersonResponse",
    "create_app",
    "configure_cors",
    "include_routes",
    "run",
]
