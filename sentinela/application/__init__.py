"""Interface pública dos serviços de aplicação do Sentinela."""

from .servico_coleta_noticias import NewsCollectorService
from .servico_registro_portal import PortalRegistrationService

__all__ = [
    "PortalRegistrationService",
    "NewsCollectorService",
]
