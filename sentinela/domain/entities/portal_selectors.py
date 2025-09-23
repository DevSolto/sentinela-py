"""Estruturas de seletores necessários para navegar por um portal."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .selector import Selector


@dataclass(frozen=True)
class PortalSelectors:
    """Agrupa os seletores usados para localizar e extrair dados do portal."""

    #: Seletor para localizar cada artigo dentro da listagem principal.
    listing_article: Selector
    #: Seletor para extrair o título visível de cada artigo.
    listing_title: Selector
    #: Seletor responsável por obter o link absoluto de cada artigo.
    listing_url: Selector
    #: Seletor que alcança o conteúdo completo do artigo já aberto.
    article_content: Selector
    #: Seletor que captura a data de publicação do artigo.
    article_date: Selector
    #: Seletor opcional utilizado para extrair o resumo apresentado na listagem.
    listing_summary: Optional[Selector] = None
