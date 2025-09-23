"""Backward-compatible shim for legacy container imports."""
from __future__ import annotations

from dataclasses import dataclass

from sentinela.application.servico_coleta_noticias import NewsCollectorService
from sentinela.application.servico_registro_portal import (
    PortalRegistrationService,
)
from sentinela.services.news import build_news_container
from sentinela.services.portals import build_portals_container


@dataclass
class Container:
    """Aggregated container mirroring the legacy structure."""

    portal_service: PortalRegistrationService
    collector_service: NewsCollectorService


def build_container() -> Container:
    """Construct combined container using domain-specific builders."""

    portals_container = build_portals_container()
    news_container = build_news_container()

    return Container(
        portal_service=portals_container.portal_service,
        collector_service=news_container.collector_service,
    )
