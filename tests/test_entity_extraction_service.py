from datetime import datetime, timezone
from typing import Iterable, List

from sentinela.domain import CityMention
from sentinela.extraction import (
    CityGazetteer,
    CityRecord,
    EntityExtractionService,
    EntitySpan,
    NewsDocument,
)
from sentinela.extraction.models import (
    CityOccurrence,
    ExtractionResultWriter,
    NewsRepository,
    PersonOccurrence,
)
from sentinela.extraction.ner import NEREngine


class FakeNewsRepository(NewsRepository):
    def __init__(self, documents: Iterable[NewsDocument]):
        self._documents = list(documents)
        self.processed: List[str] = []
        self.errors: List[str] = []

    def fetch_pending(self, batch_size: int, ner_version: str, gazetteer_version: str):
        return list(self._documents)

    def mark_processed(self, url: str, ner_version: str, gazetteer_version: str, processed_at):
        self.processed.append(url)

    def mark_error(self, url: str, message: str) -> None:
        self.errors.append(url)


class FakeNER(NEREngine):
    def __init__(self, entities: Iterable[EntitySpan]):
        self.entities = list(entities)

    def analyze(self, text: str):
        return list(self.entities)


class FakeResultWriter(ExtractionResultWriter):
    def __init__(self):
        self.people: List[PersonOccurrence] = []
        self.cities: List[CityOccurrence] = []
        self.counter = 0

    def ensure_person(self, canonical_name: str, aliases: set[str]) -> str:
        self.counter += 1
        return str(self.counter)

    def record_person_occurrence(self, url: str, occurrence: PersonOccurrence) -> None:
        self.people.append(occurrence)

    def record_city_occurrence(self, url: str, occurrence: CityOccurrence) -> None:
        self.cities.append(occurrence)


class FakeArticleCitiesWriter:
    def __init__(self) -> None:
        self.updates: list[
            tuple[str, tuple[CityMention, ...], str | None, dict[str, object] | None]
        ] = []

    def update_article_cities(
        self,
        url: str,
        cities: tuple[CityMention, ...],
        *,
        portal: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.updates.append((url, cities, portal, metadata))


def test_entity_extraction_service_processes_people_and_cities():
    document = NewsDocument(
        url="http://example.com",
        title="PREFEITO DE RECIFE anuncia obras",
        body="O prefeito de Recife-PE, João da Silva, falou com Maria Souza.",
        published_at=datetime.now(timezone.utc),
        source="test",
    )
    normalized_text = " ".join(document.combined_text().split())
    joao_start = normalized_text.index("João")
    maria_start = normalized_text.index("Maria")
    recife_start = normalized_text.index("Recife")
    ner_entities = [
        EntitySpan(label="PERSON", text="João da Silva", start=joao_start, end=joao_start + 13, score=0.92),
        EntitySpan(label="PERSON", text="Maria Souza", start=maria_start, end=maria_start + 11, score=0.88),
        EntitySpan(label="GPE", text="Recife", start=recife_start, end=recife_start + 6, score=0.75),
    ]
    gazetteer = CityGazetteer(
        [
            CityRecord(id="1", name="Recife", uf="PE", alt_names=("Recife",)),
            CityRecord(id="2", name="Recife", uf="PB"),
        ]
    )
    repository = FakeNewsRepository([document])
    result_writer = FakeResultWriter()
    article_cities_writer = FakeArticleCitiesWriter()
    service = EntityExtractionService(
        news_repository=repository,
        result_writer=result_writer,
        ner_engine=FakeNER(ner_entities),
        gazetteer=gazetteer,
        ner_version="1",
        gazetteer_version="1",
        batch_size=10,
        article_cities_writer=article_cities_writer,
    )

    result = service.process_next_batch()

    assert result.processed == 1
    assert not result.errors
    assert repository.processed == [document.url]
    assert len(result_writer.people) == 2
    assert {p.canonical_name for p in result_writer.people} == {
        "João Da Silva",
        "Maria Souza",
    }
    assert len(result_writer.cities) >= 1
    city_occurrence = result_writer.cities[0]
    assert city_occurrence.status in {"resolved", "ambiguous"}
    assert city_occurrence.uf_surface in {"PE", None}
    assert len(article_cities_writer.updates) == 1
    updated_url, updated_cities, updated_portal, metadata = article_cities_writer.updates[0]
    assert updated_url == document.url
    assert updated_portal == document.source
    assert any(
        mention.identifier == "1" or (mention.label or "").startswith("Recife")
        for mention in updated_cities
    )
    assert metadata is None
