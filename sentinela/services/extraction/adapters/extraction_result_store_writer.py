"""Adaptador que grava resultados no armazenamento em memória."""
from __future__ import annotations

from sentinela.extraction import CityOccurrence, ExtractionResultWriter, PersonOccurrence

from .extraction_result_store import ExtractionResultStore


class ExtractionResultStoreWriter(ExtractionResultWriter):
    """Adapta :class:`ExtractionResultStore` à interface ``ExtractionResultWriter``."""

    def __init__(
        self,
        store: ExtractionResultStore,
        *,
        ner_version: str,
        gazetteer_version: str,
    ) -> None:
        """Configura a instância com as versões utilizadas durante o processamento."""

        self._store = store
        """Armazenamento compartilhado utilizado para registrar resultados."""

        self._ner_version = ner_version
        """Versão do modelo de NER associada aos registros gravados."""

        self._gazetteer_version = gazetteer_version
        """Versão do gazetteer empregada na normalização de cidades."""

    def ensure_person(self, canonical_name: str, aliases: set[str]) -> str:
        """Delegação direta para armazenar o identificador da pessoa."""

        return self._store.ensure_person(canonical_name, aliases)

    def record_person_occurrence(self, url: str, occurrence: PersonOccurrence) -> None:
        """Registra ocorrência de pessoa associada à notícia indicada."""

        self._store.append_person(
            url,
            occurrence,
            ner_version=self._ner_version,
            gazetteer_version=self._gazetteer_version,
        )

    def record_city_occurrence(self, url: str, occurrence: CityOccurrence) -> None:
        """Registra ocorrência de cidade associada à notícia indicada."""

        self._store.append_city(
            url,
            occurrence,
            ner_version=self._ner_version,
            gazetteer_version=self._gazetteer_version,
        )


__all__ = ["ExtractionResultStoreWriter"]
