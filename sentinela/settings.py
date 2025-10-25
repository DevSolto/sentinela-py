"""Configurações compartilhadas carregadas a partir de variáveis de ambiente."""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

_DEFAULT_API_BIND_HOST = "0.0.0.0"
_DEFAULT_API_PUBLIC_HOST = "127.0.0.1"
_DEFAULT_API_PORT = 8000


@lru_cache(maxsize=None)
def get_api_port() -> int:
    """Retorna a porta configurada para expor a API agregada."""

    return int(os.getenv("SENTINELA_API_PORT", os.getenv("PORT", _DEFAULT_API_PORT)))


@lru_cache(maxsize=None)
def get_api_bind_host() -> str:
    """Retorna o host utilizado pelo Uvicorn para escutar conexões."""

    return os.getenv("SENTINELA_API_BIND_HOST", _DEFAULT_API_BIND_HOST)


@lru_cache(maxsize=None)
def get_api_public_host() -> str:
    """Retorna o host público utilizado para construir URLs internas."""

    return os.getenv("SENTINELA_API_HOST", _DEFAULT_API_PUBLIC_HOST)


@lru_cache(maxsize=None)
def get_api_base_url() -> str:
    """Retorna a URL base da API para uso em clientes internos."""

    return os.getenv(
        "SENTINELA_API_URL",
        f"http://{get_api_public_host()}:{get_api_port()}",
    )


__all__ = [
    "get_api_base_url",
    "get_api_bind_host",
    "get_api_port",
    "get_api_public_host",
]
