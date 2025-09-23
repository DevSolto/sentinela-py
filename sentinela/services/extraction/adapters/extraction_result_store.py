"""Armazenamento em memória dos resultados de enriquecimento."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Iterator
from uuid import uuid4

from sentinela.extraction import CityOccurrence, PersonOccurrence

from ._stored_result import _StoredResult
from .enriched_article_result import EnrichedArticleResult


class ExtractionResultStore:
    """Mantém em memória os resultados enriquecidos produzidos pelo worker."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        """Garante acesso exclusivo às estruturas internas."""

        self._people_index: dict[str, str] = {}
        """Mapeia nomes canônicos para seus identificadores únicos."""

        self._aliases: dict[str, set[str]] = {}
        """Armazena apelidos conhecidos para cada pessoa identificada."""

        self._results: dict[str, _StoredResult] = {}
        """Resultados acumulados indexados pela URL da notícia."""

    def ensure_person(self, canonical_name: str, aliases: set[str]) -> str:
        """Garante que uma pessoa possua identificador estável e registra apelidos."""

        with self._lock:
            person_id = self._people_index.get(canonical_name)
            if not person_id:
                person_id = str(uuid4())
                self._people_index[canonical_name] = person_id
                self._aliases[person_id] = set(aliases)
            else:
                self._aliases.setdefault(person_id, set()).update(aliases)
            return person_id

    def _ensure_record(
        self, url: str, ner_version: str, gazetteer_version: str
    ) -> _StoredResult:
        """Recupera ou inicializa o registro mutável associado à notícia."""

        record = self._results.get(url)
        if record is None:
            record = _StoredResult(
                url=url,
                ner_version=ner_version,
                gazetteer_version=gazetteer_version,
            )
            self._results[url] = record
        elif (
            record.ner_version != ner_version
            or record.gazetteer_version != gazetteer_version
        ):
            record.ner_version = ner_version
            record.gazetteer_version = gazetteer_version
            record.people.clear()
            record.cities.clear()
        record.updated_at = datetime.now(timezone.utc)
        return record

    def append_person(
        self,
        url: str,
        occurrence: PersonOccurrence,
        *,
        ner_version: str,
        gazetteer_version: str,
    ) -> None:
        """Acrescenta uma ocorrência de pessoa ao registro indicado."""

        with self._lock:
            record = self._ensure_record(url, ner_version, gazetteer_version)
            record.people = _append_unique_person(record.people, occurrence)

    def append_city(
        self,
        url: str,
        occurrence: CityOccurrence,
        *,
        ner_version: str,
        gazetteer_version: str,
    ) -> None:
        """Acrescenta uma ocorrência de cidade ao registro indicado."""

        with self._lock:
            record = self._ensure_record(url, ner_version, gazetteer_version)
            record.cities = _append_unique_city(record.cities, occurrence)

    def get(self, url: str) -> EnrichedArticleResult | None:
        """Retorna um instantâneo do resultado enriquecido associado à URL."""

        with self._lock:
            record = self._results.get(url)
            if not record:
                return None
            return self._snapshot(record)

    def list(self) -> Iterator[EnrichedArticleResult]:
        """Gera instantâneos de todos os resultados disponíveis."""

        with self._lock:
            for record in list(self._results.values()):
                yield self._snapshot(record)

    def serialize(self) -> str:
        """Serializa o conteúdo do armazenamento para inspeções e depuração."""

        with self._lock:
            payload = {
                url: {
                    "ner_version": record.ner_version,
                    "gazetteer_version": record.gazetteer_version,
                    "updated_at": record.updated_at.isoformat(),
                    "people": [asdict(occ) for occ in record.people],
                    "cities": [
                        {
                            **asdict(occ),
                            "candidates": [
                                asdict(candidate) for candidate in occ.candidates
                            ],
                        }
                        for occ in record.cities
                    ],
                }
                for url, record in self._results.items()
            }
        return json.dumps(payload, ensure_ascii=False)

    def _snapshot(self, record: _StoredResult) -> EnrichedArticleResult:
        """Cria uma representação imutável a partir do registro mutável."""

        return EnrichedArticleResult(
            url=record.url,
            ner_version=record.ner_version,
            gazetteer_version=record.gazetteer_version,
            updated_at=record.updated_at,
            people=tuple(record.people),
            cities=tuple(record.cities),
        )


def _append_unique_person(
    values: list[PersonOccurrence], occurrence: PersonOccurrence
) -> list[PersonOccurrence]:
    """Evita duplicação de ocorrências de pessoas preservando inserções recentes."""

    filtered = [
        value
        for value in values
        if not (
            value.person_id == occurrence.person_id
            and value.start == occurrence.start
            and value.end == occurrence.end
        )
    ]
    filtered.append(occurrence)
    return filtered


def _append_unique_city(
    values: list[CityOccurrence], occurrence: CityOccurrence
) -> list[CityOccurrence]:
    """Evita duplicação de ocorrências de cidades preservando inserções recentes."""

    filtered = [
        value
        for value in values
        if not (
            value.city_id == occurrence.city_id
            and value.start == occurrence.start
            and value.end == occurrence.end
        )
    ]
    filtered.append(occurrence)
    return filtered


__all__ = ["ExtractionResultStore"]
