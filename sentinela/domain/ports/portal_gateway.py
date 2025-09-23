"""Porta de entrada que fornece configurações de portais."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from sentinela.domain.entities import Portal


class PortalGateway(ABC):
    """Define como a aplicação consulta portais cadastrados em outros serviços."""

    @abstractmethod
    def get_portal(self, name: str) -> Optional[Portal]:
        """Buscar um portal pelo nome e retornar sua configuração quando existir."""
