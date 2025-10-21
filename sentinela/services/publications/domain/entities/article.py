"""Entidades específicas do serviço de publicações."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Article:
    """Representa um artigo armazenado pelo serviço de publicações."""

    #: Nome do portal responsável pela publicação do artigo.
    portal_name: str
    #: Título exibido quando o artigo foi coletado.
    title: str
    #: Endereço permanente utilizado para acessar o artigo.
    url: str
    #: Conteúdo textual normalizado do artigo.
    content: str
    #: Data e hora de publicação informadas pelo portal.
    published_at: datetime
    #: Resumo opcional disponibilizado na listagem de artigos.
    summary: Optional[str] = None
    #: Classificação atribuída ao artigo após enriquecimento ou ingestão.
    classification: Optional[str] = None
    #: Cidades mencionadas ou associadas ao artigo quando disponíveis.
    cities: tuple[str, ...] = field(default_factory=tuple)
    #: Informações adicionais preservadas para auditoria e rastreabilidade.
    raw: Dict[str, Any] = field(default_factory=dict)


__all__ = ["Article"]
