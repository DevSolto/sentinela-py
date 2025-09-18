"""Application services public API for Sentinela."""

from .services import NewsCollectorService, PortalRegistrationService

__all__ = [
    "PortalRegistrationService",
    "NewsCollectorService",
]
