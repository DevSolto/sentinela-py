"""Entidade que representa um artigo coletado."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple


@dataclass(frozen=True)
class CityMention:
    """Representa uma cidade associada ao artigo juntamente com metadados."""

    identifier: str
    city_id: Optional[str] = None
    label: Optional[str] = None
    uf: Optional[str] = None
    occurrences: int = 1
    sources: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_legacy(cls, value: str) -> "CityMention":
        """Cria uma menção a partir de um valor simples utilizado no legado."""

        text = value.strip()
        if not text:
            raise ValueError("city value cannot be empty")
        city_id = text if text.isdigit() else None
        label = None if city_id else text
        return cls(
            identifier=text,
            city_id=city_id,
            label=label,
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CityMention":
        """Reconstrói uma menção a partir da estrutura persistida no Mongo."""

        identifier = (
            data.get("identifier")
            or data.get("city_id")
            or data.get("ibge_id")
            or data.get("id")
            or data.get("label")
            or data.get("name")
            or data.get("nome")
        )
        if identifier is None:
            raise ValueError("missing identifier for city mention")
        city_id = data.get("city_id") or data.get("ibge_id") or data.get("id")
        label = data.get("label") or data.get("name") or data.get("nome")
        uf = data.get("uf")
        occurrences = data.get("occurrences")
        sources = data.get("sources")

        city_id_str = str(city_id) if city_id is not None else None
        label_str = str(label) if label is not None else None
        uf_str = str(uf) if uf is not None else None

        try:
            occurrences_int = int(occurrences)
        except (TypeError, ValueError):
            occurrences_int = 1
        if occurrences_int <= 0:
            occurrences_int = 1

        if isinstance(sources, Iterable) and not isinstance(sources, (str, bytes)):
            sources_tuple = tuple(str(item) for item in sources if str(item))
        else:
            sources_tuple = ()

        return cls(
            identifier=str(identifier),
            city_id=city_id_str,
            label=label_str,
            uf=uf_str,
            occurrences=occurrences_int,
            sources=sources_tuple,
        )

    @classmethod
    def from_raw(cls, value: Any) -> "CityMention":
        """Cria uma menção a partir de diferentes representações aceitas."""

        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls.from_mapping(value)
        if value is None:
            raise ValueError("invalid city value")
        return cls.from_legacy(str(value))

    @classmethod
    def parse_many(cls, values: Iterable[Any]) -> tuple["CityMention", ...]:
        """Converte uma coleção heterogênea em tupla de ``CityMention``."""

        mentions: list[CityMention] = []
        for value in values or ():
            try:
                mentions.append(cls.from_raw(value))
            except ValueError:
                continue
        return tuple(mentions)

    def to_mapping(self) -> Dict[str, Any]:
        """Serializa a menção para armazenamento em coleções MongoDB."""

        payload: Dict[str, Any] = {
            "identifier": self.identifier,
            "occurrences": self.occurrences,
        }
        if self.city_id is not None:
            payload["city_id"] = self.city_id
            payload["ibge_id"] = self.city_id
            payload["id"] = self.city_id
        if self.label is not None:
            payload["label"] = self.label
            payload["name"] = self.label
            payload["nome"] = self.label
        if self.uf is not None:
            payload["uf"] = self.uf
        if self.sources:
            payload["sources"] = list(dict.fromkeys(self.sources))
        return payload


@dataclass(frozen=True)
class Article:
    """Armazena os dados normalizados de um artigo extraído."""

    #: Nome do portal de origem associado ao artigo.
    portal_name: str
    #: Título final exibido para o artigo publicado.
    title: str
    #: Endereço original apontando para o conteúdo publicado.
    url: str
    #: Corpo completo do artigo em texto limpo.
    content: str
    #: Data e hora de publicação identificada durante a coleta.
    published_at: datetime
    #: Resumo opcional do artigo quando disponível na listagem.
    summary: Optional[str] = None
    #: Classificação atribuída ao artigo pelas etapas de enriquecimento.
    classification: Optional[str] = None
    #: Cidades associadas ao conteúdo identificadas durante o processamento.
    cities: tuple[CityMention, ...] = field(default_factory=tuple)
    #: Metadados de enriquecimento relacionados à extração de cidades.
    cities_extraction: Optional[Dict[str, Any]] = None
    #: Dados brutos adicionais preservados para auditoria ou uso futuro.
    raw: Dict[str, Any] = field(default_factory=dict)
