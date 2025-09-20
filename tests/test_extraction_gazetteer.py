from sentinela.extraction.gazetteer import CityGazetteer, CityRecord


def build_gazetteer():
    records = [
        CityRecord(id="1", name="São João", uf="PE", alt_names=("Sao Joao",)),
        CityRecord(id="2", name="São João", uf="SP"),
        CityRecord(id="3", name="Recife", uf="PE", alt_names=("Recife", "Recife-PE")),
    ]
    return CityGazetteer(records)


def test_gazetteer_resolves_with_context():
    gazetteer = build_gazetteer()
    resolution = gazetteer.resolve("São João", uf_surface=None, context_states={"PE"})
    assert resolution.status == "resolved"
    assert resolution.city_id == "1"


def test_gazetteer_marks_ambiguous_without_context():
    gazetteer = build_gazetteer()
    resolution = gazetteer.resolve("São João", uf_surface=None, context_states=set())
    assert resolution.status == "ambiguous"
    assert resolution.city_id is None
    assert len(resolution.candidates) == 2


def test_gazetteer_returns_foreign_when_not_found():
    gazetteer = build_gazetteer()
    resolution = gazetteer.resolve("Springfield", uf_surface=None, context_states=None)
    assert resolution.status == "foreign"
    assert resolution.city_id is None
