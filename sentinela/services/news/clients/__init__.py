"""Clientes HTTP utilizados pelo serviço de notícias."""

from .portal_service_client import PortalServiceClient
from .publications_api_sink import PublicationsAPISink

__all__ = ["PortalServiceClient", "PublicationsAPISink"]
