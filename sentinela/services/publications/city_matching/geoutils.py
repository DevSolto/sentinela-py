"""Utilidades geográficas para o módulo de city matching."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

_EARTH_RADIUS_KM = 6371.0


def _extract_coordinates(payload: Any) -> tuple[float, float] | None:
    if isinstance(payload, Mapping):
        lat = payload.get("lat") or payload.get("latitude")
        lon = payload.get("lon") or payload.get("longitude")
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        if len(payload) < 2:
            return None
        lat, lon = payload[:2]
    else:
        return None

    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None

    return lat_f, lon_f


def haversine_distance_km(
    origin: Mapping[str, Any] | Sequence[Any] | None,
    destination: Mapping[str, Any] | Sequence[Any] | None,
) -> float | None:
    """Calcula a distância Haversine entre dois pontos geográficos.

    Retorna ``None`` quando as coordenadas fornecidas forem inválidas.
    """

    origin_coords = _extract_coordinates(origin)
    destination_coords = _extract_coordinates(destination)
    if origin_coords is None or destination_coords is None:
        return None

    lat1, lon1 = origin_coords
    lat2, lon2 = destination_coords

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    sin_delta_phi = math.sin(delta_phi / 2.0)
    sin_delta_lambda = math.sin(delta_lambda / 2.0)

    a = sin_delta_phi ** 2 + math.cos(phi1) * math.cos(phi2) * sin_delta_lambda ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return _EARTH_RADIUS_KM * c


__all__ = ["haversine_distance_km"]
