from sentinela.extraction.disambiguation import disambiguate_city
from sentinela.extraction.gazetteer import CityRecord


def test_disambiguate_city_requires_context_for_natal():
    candidates = [CityRecord(id="2408102", name="Natal", uf="RN")]

    result = disambiguate_city("Natal", candidates, uf_surface=None, context_states=[])

    assert result.status == "unknown_uf"
    assert result.city is None
    assert result.confidence < 0.5

    context_result = disambiguate_city(
        "Natal", candidates, uf_surface=None, context_states=["RN"]
    )

    assert context_result.status == "resolved"
    assert context_result.city is not None
    assert context_result.city.id == "2408102"
    assert context_result.confidence > result.confidence


def test_disambiguate_city_uses_uf_surface_for_ambiguous_palmas():
    candidates = [
        CityRecord(id="1721000", name="Palmas", uf="TO"),
        CityRecord(id="4117602", name="Palmas", uf="PR"),
    ]

    ambiguous = disambiguate_city("Palmas", candidates, uf_surface=None, context_states=[])
    assert ambiguous.status == "ambiguous"
    assert ambiguous.city is None

    context = disambiguate_city("Palmas", candidates, uf_surface=None, context_states=["TO"])
    assert context.status == "resolved"
    assert context.city is not None
    assert context.city.uf == "TO"

    explicit = disambiguate_city("Palmas", candidates, uf_surface="TO", context_states=[])
    assert explicit.status == "resolved"
    assert explicit.city is not None
    assert explicit.city.id == "1721000"
