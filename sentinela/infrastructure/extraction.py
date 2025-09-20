"""Infrastructure helpers for the entity extraction microservice."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Iterable

from pymongo import ASCENDING
from pymongo.collection import Collection

from sentinela.extraction.models import (
    CityOccurrence,
    NewsDocument,
    NewsRepository,
    PersonOccurrence,
    ExtractionResultWriter,
)


_VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ensure_identifier(name: str) -> str:
    if not _VALID_IDENTIFIER.match(name):  # pragma: no cover - defensive check
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


def _qualify_table(table: str, schema: str | None) -> str:
    table = _ensure_identifier(table)
    if schema:
        schema = _ensure_identifier(schema)
        return f'"{schema}"."{table}"'
    return f'"{table}"'


class MongoNewsRepository(NewsRepository):
    """Mongo-backed implementation of :class:`NewsRepository`."""

    def __init__(
        self,
        collection: Collection,
        *,
        title_field: str = "titulo",
        body_field: str = "corpo",
        published_at_field: str = "data_publicacao",
        source_field: str = "fonte",
    ) -> None:
        self._collection = collection
        self._title_field = title_field
        self._body_field = body_field
        self._published_at_field = published_at_field
        self._source_field = source_field
        self._collection.create_index([("ner_done", ASCENDING)], background=True)
        self._collection.create_index([("_id", ASCENDING)], background=True)

    def fetch_pending(
        self, batch_size: int, ner_version: str, gazetteer_version: str
    ) -> Iterable[NewsDocument]:
        query = {
            "$or": [
                {"ner_done": {"$exists": False}},
                {"ner_done": False},
                {"ner_version": {"$ne": ner_version}},
                {"gazetteer_version": {"$ne": gazetteer_version}},
            ]
        }
        cursor = (
            self._collection.find(query)
            .sort("_id", ASCENDING)
            .limit(max(1, batch_size))
        )
        for document in cursor:
            yield self._deserialize(document)

    def mark_processed(
        self,
        url: str,
        ner_version: str,
        gazetteer_version: str,
        processed_at: datetime,
    ) -> None:
        self._collection.update_one(
            {"_id": url},
            {
                "$set": {
                    "ner_done": True,
                    "ner_version": ner_version,
                    "gazetteer_version": gazetteer_version,
                    "processed_at": processed_at,
                },
                "$unset": {"errors": ""},
            },
        )

    def mark_error(self, url: str, message: str) -> None:
        self._collection.update_one(
            {"_id": url},
            {
                "$set": {
                    "ner_done": False,
                    "last_error": message,
                },
                "$push": {
                    "errors": {
                        "message": message,
                        "timestamp": datetime.now(timezone.utc),
                    }
                },
            },
            upsert=True,
        )

    def _deserialize(self, data: dict) -> NewsDocument:
        url = str(data.get("_id") or data.get("url"))
        title = str(data.get(self._title_field) or data.get("title") or "")
        body = str(data.get(self._body_field) or data.get("body") or "")
        published_raw = (
            data.get(self._published_at_field)
            or data.get("published_at")
            or datetime.fromtimestamp(0, timezone.utc)
        )
        published_at = self._parse_datetime(published_raw)
        source = data.get(self._source_field) or data.get("source")
        return NewsDocument(
            url=url,
            title=title,
            body=body,
            published_at=published_at,
            source=source,
        )

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(value, fmt)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed
                except ValueError:
                    continue
        return datetime.fromtimestamp(0, timezone.utc)


class PostgresExtractionResultWriter(ExtractionResultWriter):
    """DB-API implementation of :class:`ExtractionResultWriter`."""

    def __init__(
        self,
        connection,
        *,
        schema: str | None = None,
        people_table: str = "pessoas",
        person_alias_table: str | None = "pessoas_aliases",
        news_people_table: str = "noticias_pessoas",
        news_cities_table: str = "noticias_cidades",
    ) -> None:
        self._connection = connection
        self._people_table = _qualify_table(people_table, schema)
        self._person_alias_table = (
            _qualify_table(person_alias_table, schema) if person_alias_table else None
        )
        self._news_people_table = _qualify_table(news_people_table, schema)
        self._news_cities_table = _qualify_table(news_cities_table, schema)

    def ensure_person(self, canonical_name: str, aliases: set[str]) -> str:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {self._people_table} (nome_canonico)
                VALUES (%s)
                ON CONFLICT (nome_canonico) DO UPDATE
                SET nome_canonico = EXCLUDED.nome_canonico
                RETURNING id
                """,
                (canonical_name,),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    f"SELECT id FROM {self._people_table} WHERE nome_canonico = %s",
                    (canonical_name,),
                )
                row = cursor.fetchone()
                if row is None:  # pragma: no cover - defensive
                    raise RuntimeError(
                        f"Pessoa '{canonical_name}' não pôde ser persistida"
                    )
            person_id = str(row[0])

            if aliases and self._person_alias_table:
                records = [(person_id, alias) for alias in sorted(aliases)]
                cursor.executemany(
                    f"""
                    INSERT INTO {self._person_alias_table} (pessoa_id, alias)
                    VALUES (%s, %s)
                    ON CONFLICT (pessoa_id, alias) DO NOTHING
                    """,
                    records,
                )
        self._connection.commit()
        return person_id

    def record_person_occurrence(self, url: str, occurrence: PersonOccurrence) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {self._news_people_table} (
                    noticia_url,
                    pessoa_id,
                    nome_canonico,
                    surface,
                    start_offset,
                    end_offset,
                    frase,
                    metodo,
                    confianca
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (noticia_url, start_offset, end_offset) DO UPDATE
                SET
                    pessoa_id = EXCLUDED.pessoa_id,
                    nome_canonico = EXCLUDED.nome_canonico,
                    surface = EXCLUDED.surface,
                    frase = EXCLUDED.frase,
                    metodo = EXCLUDED.metodo,
                    confianca = EXCLUDED.confianca
                """,
                (
                    url,
                    occurrence.person_id,
                    occurrence.canonical_name,
                    occurrence.surface,
                    occurrence.start,
                    occurrence.end,
                    occurrence.sentence,
                    occurrence.method,
                    occurrence.confidence,
                ),
            )
        self._connection.commit()

    def record_city_occurrence(self, url: str, occurrence: CityOccurrence) -> None:
        candidates_payload = json.dumps(
            [
                {
                    "city_id": candidate.city_id,
                    "name": candidate.name,
                    "uf": candidate.uf,
                    "score": candidate.score,
                }
                for candidate in occurrence.candidates
            ],
            ensure_ascii=False,
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {self._news_cities_table} (
                    noticia_url,
                    cidade_id,
                    surface,
                    start_offset,
                    end_offset,
                    frase,
                    status,
                    uf_surface,
                    metodo,
                    confianca,
                    candidatos
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (noticia_url, start_offset, end_offset) DO UPDATE
                SET
                    cidade_id = EXCLUDED.cidade_id,
                    surface = EXCLUDED.surface,
                    frase = EXCLUDED.frase,
                    status = EXCLUDED.status,
                    uf_surface = EXCLUDED.uf_surface,
                    metodo = EXCLUDED.metodo,
                    confianca = EXCLUDED.confianca,
                    candidatos = EXCLUDED.candidatos
                """,
                (
                    url,
                    occurrence.city_id,
                    occurrence.surface,
                    occurrence.start,
                    occurrence.end,
                    occurrence.sentence,
                    occurrence.status,
                    occurrence.uf_surface,
                    occurrence.method,
                    occurrence.confidence,
                    candidates_payload,
                ),
            )
        self._connection.commit()


__all__ = [
    "MongoNewsRepository",
    "PostgresExtractionResultWriter",
]

