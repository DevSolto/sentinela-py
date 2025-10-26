"""Interface pública para o pacote de enriquecimento geográfico."""
from .service import GeoOutput, RawMatch, enrich_geo

__all__ = ["GeoOutput", "RawMatch", "enrich_geo"]
