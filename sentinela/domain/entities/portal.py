"""Entidade que descreve um portal configurado para coleta."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict

from .portal_selectors import PortalSelectors


@dataclass(frozen=True)
class Portal:
    """Representa um portal de notícias configurado pelo usuário."""

    #: Nome único do portal para identificação interna.
    name: str
    #: Endereço base utilizado para montar URLs completas do portal.
    base_url: str
    #: Template de caminho contendo ``{date}`` para gerar páginas de listagem.
    listing_path_template: str
    #: Estrutura de seletores responsável por orientar a raspagem do portal.
    selectors: PortalSelectors
    #: Cabeçalhos HTTP adicionais aplicados durante as requisições ao portal.
    headers: Dict[str, str] = field(default_factory=dict)
    #: Formato de data aplicado ao preencher ``{date}`` no template de listagem.
    date_format: str = "%Y-%m-%d"

    def listing_url_for(self, target_date: datetime) -> str:
        """Gerar a URL da listagem correspondente à data desejada."""

        if "{date}" not in self.listing_path_template:
            raise ValueError(
                "O template de listagem deve conter '{date}' para coleta por data. "
                "Use o comando 'collect-all' ou configure listing_path_template com '{date}'."
            )
        formatted_date = target_date.strftime(self.date_format)
        path = self.listing_path_template.format(date=formatted_date)
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
