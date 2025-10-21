"""Entidade que representa um artigo coletado."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


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
    #: Cidades associadas ao conteúdo identificadas durante o processamento.
    cities: tuple[str, ...] = field(default_factory=tuple)
    #: Dados brutos adicionais preservados para auditoria ou uso futuro.
    raw: Dict[str, Any] = field(default_factory=dict)
