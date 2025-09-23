"""Implementações de repositório de portais baseadas em MongoDB."""
from __future__ import annotations

from typing import Iterable, Optional

from pymongo.collection import Collection

from sentinela.domain import Portal, PortalSelectors, Selector
from sentinela.domain.repositories import PortalRepository


class MongoPortalRepository(PortalRepository):
    """Persiste e busca entidades :class:`Portal` em uma coleção MongoDB."""

    def __init__(self, collection: Collection) -> None:
        """Inicializa o repositório com a coleção de portais.

        Parameters
        ----------
        collection:
            Coleção MongoDB na qual os documentos de portal serão gravados e
            consultados.
        """

        self._collection: Collection = collection
        """Coleção MongoDB onde os portais são armazenados."""

    def add(self, portal: Portal) -> None:
        """Insere um novo portal serializando todos os seletores associados."""

        self._collection.insert_one(self._serialize_portal(portal))

    def get_by_name(self, name: str) -> Optional[Portal]:
        """Busca um portal pelo nome convertendo o documento encontrado."""

        data = self._collection.find_one({"name": name})
        if not data:
            return None
        return self._deserialize_portal(data)

    def list_all(self) -> Iterable[Portal]:
        """Itera sobre todos os portais persistidos desserializando cada um."""

        for data in self._collection.find():
            yield self._deserialize_portal(data)

    def _serialize_portal(self, portal: Portal) -> dict:
        """Transforma a entidade ``Portal`` em um documento pronto para MongoDB.

        Todos os seletores são convertidos para dicionários simples para que o
        driver do Mongo possa armazená-los corretamente.
        """

        return {
            "name": portal.name,
            "base_url": portal.base_url,
            "listing_path_template": portal.listing_path_template,
            "headers": portal.headers,
            "date_format": portal.date_format,
            "selectors": {
                "listing_article": portal.selectors.listing_article.__dict__,
                "listing_title": portal.selectors.listing_title.__dict__,
                "listing_url": portal.selectors.listing_url.__dict__,
                "article_content": portal.selectors.article_content.__dict__,
                "article_date": portal.selectors.article_date.__dict__,
                "listing_summary": (
                    portal.selectors.listing_summary.__dict__
                    if portal.selectors.listing_summary
                    else None
                ),
            },
        }

    def _deserialize_portal(self, data: dict) -> Portal:
        """Reconstrói uma entidade ``Portal`` a partir de um documento MongoDB."""

        selectors = data["selectors"]
        return Portal(
            name=data["name"],
            base_url=data["base_url"],
            listing_path_template=data["listing_path_template"],
            headers=data.get("headers", {}),
            date_format=data.get("date_format", "%Y-%m-%d"),
            selectors=PortalSelectors(
                listing_article=Selector(**selectors["listing_article"]),
                listing_title=Selector(**selectors["listing_title"]),
                listing_url=Selector(**selectors["listing_url"]),
                article_content=Selector(**selectors["article_content"]),
                article_date=Selector(**selectors["article_date"]),
                listing_summary=(
                    Selector(**selectors["listing_summary"])
                    if selectors.get("listing_summary")
                    else None
                ),
            ),
        )


__all__ = ["MongoPortalRepository"]
