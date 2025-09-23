"""Entidade que descreve como localizar informações em uma página HTML."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Selector:
    """Configura um seletor CSS utilizado durante a coleta de dados."""

    #: Expressão CSS aplicada para encontrar o elemento desejado na página.
    query: str
    #: Nome do atributo que deve ser lido no elemento; usa o texto quando ausente.
    attribute: Optional[str] = None
