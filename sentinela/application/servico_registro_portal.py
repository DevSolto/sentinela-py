"""Serviço de cadastro e consulta de portais."""
from __future__ import annotations

from typing import Iterable

from sentinela.domain import Portal
from sentinela.domain.repositories import PortalRepository


class PortalRegistrationService:
    """Gerencia o ciclo de vida dos portais cadastrados no sistema."""

    def __init__(self, repository: PortalRepository) -> None:
        """Inicializa o serviço com o repositório de portais configurado.

        Args:
            repository: Implementação de ``PortalRepository`` responsável por
                persistir e recuperar portais cadastrados.
        """

        # Repositório responsável por verificar duplicidade e persistir dados.
        self._repository = repository

    def register(self, portal: Portal) -> None:
        """Registra um portal garantindo que não haja duplicidade de nomes.

        Args:
            portal: Instância de ``Portal`` preenchida com seletores e
                metadados necessários para a coleta.

        Raises:
            ValueError: Quando já existe um portal com o mesmo nome.
        """

        if self._repository.get_by_name(portal.name):
            raise ValueError(f"Portal '{portal.name}' already exists")
        self._repository.add(portal)

    def list_portals(self) -> Iterable[Portal]:
        """Lista todos os portais cadastrados atualmente.

        Returns:
            Um iterável com as instâncias de ``Portal`` conhecidas pelo
            repositório.
        """

        return self._repository.list_all()

    def get_portal(self, name: str) -> Portal:
        """Busca um portal pelo nome para reutilização nas coletas.

        Args:
            name: Nome do portal cadastrado, tal como definido no registro.

        Returns:
            A instância de ``Portal`` correspondente ao nome informado.

        Raises:
            ValueError: Quando não há portal cadastrado com o nome solicitado.
        """

        portal = self._repository.get_by_name(name)
        if not portal:
            raise ValueError(f"Portal '{name}' not found")
        return portal


__all__ = ["PortalRegistrationService"]
