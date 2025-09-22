"""Dependency container for portal-related services."""
from __future__ import annotations

from dataclasses import dataclass

from sentinela.application.services import PortalRegistrationService
from sentinela.infrastructure.database import MongoClientFactory
from sentinela.infrastructure.repositories import MongoPortalRepository


@dataclass
class PortalsContainer:
    """Container exposing portal service dependencies."""

    portal_repository: MongoPortalRepository
    portal_service: PortalRegistrationService


def build_portals_container(
    factory: MongoClientFactory | None = None,
) -> PortalsContainer:
    """Build the portal service container."""

    factory = factory or MongoClientFactory()
    database = factory.get_database()

    portal_repository = MongoPortalRepository(database["portals"])
    portal_service = PortalRegistrationService(portal_repository)

    return PortalsContainer(
        portal_repository=portal_repository,
        portal_service=portal_service,
    )
