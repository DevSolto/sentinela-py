"""Contrato de persistência para portais cadastrados."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from sentinela.domain.entities import Portal


class PortalRepository(ABC):
    """Define operações de armazenamento e consulta de portais cadastrados."""

    @abstractmethod
    def add(self, portal: Portal) -> None:
        """Registrar um novo portal persistindo sua configuração."""

    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Portal]:
        """Recuperar um portal pelo seu identificador único."""

    @abstractmethod
    def list_all(self) -> Iterable[Portal]:
        """Listar todos os portais já cadastrados."""
