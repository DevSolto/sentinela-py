from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from sentinela.services.publications.city_matching import catalog as catalog_module
from sentinela.services.publications.city_matching.build_cache import CityCatalogError


def _write_catalog(path: Path, *, record_count: int) -> None:
    payload = {
        "metadata": {
            "version": "test",
            "record_count": record_count,
            "source": "fixture",
            "primary_source": "fixture",
            "checksum": "abc",
            "downloaded_at": "2024-01-01T00:00:00Z",
        },
        "data": [
            {
                "ibge_id": "1100015",
                "name": "Alta Floresta D'Oeste",
                "uf": "RO",
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class _FakeStorage:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = deepcopy(payload)
        self.saved: list[tuple[str, dict]] = []
        self.load_calls: list[str] = []

    def load(self, version: str):
        self.load_calls.append(version)
        if self._payload is None:
            return None
        return json.loads(json.dumps(self._payload))

    def save(self, version: str, payload):
        self.saved.append((version, json.loads(json.dumps(payload))))


def test_load_city_catalog_fetches_full_dataset_when_sample(monkeypatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "catalog.json"
    _write_catalog(cache_path, record_count=10)

    monkeypatch.setattr(catalog_module, "get_cache_path", lambda version=None: cache_path)

    fetched_payload = [
        {"ibge_id": "5300108", "name": "Brasília", "uf": "DF"},
        {"ibge_id": "3550308", "name": "São Paulo", "uf": "SP"},
    ]

    calls: list[str] = []

    def fake_fetcher(primary: str):
        calls.append(primary)
        return fetched_payload, "ibge"

    result = catalog_module.load_city_catalog(
        "test",
        ensure_complete=True,
        minimum_record_count=20,
        fetcher=fake_fetcher,
    )

    assert calls == ["ibge"]
    assert {entry["ibge_id"] for entry in result["data"]} == {
        city["ibge_id"] for city in fetched_payload
    }
    for entry in result["data"]:
        assert entry["name"] in {city["name"] for city in fetched_payload}
        assert "ibge_context" in entry
        assert "coords" in entry
    assert result["metadata"]["record_count"] == len(fetched_payload)

    stored = json.loads(cache_path.read_text(encoding="utf-8"))
    assert {entry["ibge_id"] for entry in stored["data"]} == {
        city["ibge_id"] for city in fetched_payload
    }


def test_load_city_catalog_returns_original_when_fetch_fails(monkeypatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "catalog.json"
    _write_catalog(cache_path, record_count=10)

    monkeypatch.setattr(catalog_module, "get_cache_path", lambda version=None: cache_path)

    def failing_fetcher(primary: str):
        raise CityCatalogError("boom")

    result = catalog_module.load_city_catalog(
        "test",
        ensure_complete=True,
        minimum_record_count=20,
        fetcher=failing_fetcher,
    )

    assert result["metadata"]["source"] == "fixture"


def test_load_city_catalog_uses_cached_when_complete(monkeypatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "catalog.json"
    _write_catalog(cache_path, record_count=6000)

    monkeypatch.setattr(catalog_module, "get_cache_path", lambda version=None: cache_path)

    result = catalog_module.load_city_catalog(
        "test",
        ensure_complete=True,
        minimum_record_count=20,
        fetcher=lambda primary: (_ for _ in ()).throw(RuntimeError("should not fetch")),
    )

    assert result["metadata"]["record_count"] == 6000


def test_load_city_catalog_reads_from_storage_before_fetch(monkeypatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "catalog.json"
    _write_catalog(cache_path, record_count=10)

    monkeypatch.setattr(catalog_module, "get_cache_path", lambda version=None: cache_path)

    storage_payload = {
        "metadata": {"record_count": 6000, "version": "test"},
        "data": [
            {"ibge_id": "3550308", "name": "São Paulo", "uf": "SP"},
            {"ibge_id": "5208707", "name": "Goiânia", "uf": "GO"},
        ],
    }
    storage = _FakeStorage(storage_payload)

    def failing_fetcher(primary: str):  # pragma: no cover - não deve ser chamado
        raise AssertionError("fetcher não deve ser chamado quando storage possui catálogo completo")

    result = catalog_module.load_city_catalog(
        "test",
        ensure_complete=True,
        minimum_record_count=20,
        fetcher=failing_fetcher,
        storage=storage,
    )

    assert storage.load_calls == ["test"]
    assert {entry["ibge_id"] for entry in result["data"]} == {
        "3550308",
        "5208707",
    }
    for entry in result["data"]:
        assert "ibge_context" in entry
    stored = json.loads(cache_path.read_text(encoding="utf-8"))
    assert {entry["ibge_id"] for entry in stored["data"]} == {
        "3550308",
        "5208707",
    }


def test_load_city_catalog_uses_storage_even_without_ensure(monkeypatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "catalog.json"
    _write_catalog(cache_path, record_count=10)

    monkeypatch.setattr(catalog_module, "get_cache_path", lambda version=None: cache_path)

    storage_payload = {
        "metadata": {"record_count": 6000, "version": "test"},
        "data": [
            {"ibge_id": "3550308", "name": "São Paulo", "uf": "SP"},
            {"ibge_id": "5208707", "name": "Goiânia", "uf": "GO"},
        ],
    }
    storage = _FakeStorage(storage_payload)

    result = catalog_module.load_city_catalog("test", storage=storage)

    assert storage.load_calls == ["test"]
    assert {entry["ibge_id"] for entry in result["data"]} == {
        "3550308",
        "5208707",
    }
    stored = json.loads(cache_path.read_text(encoding="utf-8"))
    assert {entry["ibge_id"] for entry in stored["data"]} == {
        "3550308",
        "5208707",
    }


def test_load_city_catalog_persists_refresh_into_storage(monkeypatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "catalog.json"
    _write_catalog(cache_path, record_count=10)

    monkeypatch.setattr(catalog_module, "get_cache_path", lambda version=None: cache_path)

    storage = _FakeStorage()

    fetched_payload = [
        {"ibge_id": "5300108", "name": "Brasília", "uf": "DF"},
        {"ibge_id": "3550308", "name": "São Paulo", "uf": "SP"},
    ]

    result = catalog_module.load_city_catalog(
        "test",
        ensure_complete=True,
        minimum_record_count=20,
        fetcher=lambda primary: (fetched_payload, "ibge"),
        storage=storage,
    )

    assert storage.saved
    version, payload = storage.saved[-1]
    assert version == "test"
    assert {entry["ibge_id"] for entry in payload["data"]} == {
        city["ibge_id"] for city in fetched_payload
    }
    assert {entry["ibge_id"] for entry in result["data"]} == {
        city["ibge_id"] for city in fetched_payload
    }


def test_load_city_catalog_enriches_geographic_context(monkeypatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "catalog.json"
    payload = {
        "metadata": {
            "version": "test",
            "record_count": 2,
            "source": "fixture",
            "primary_source": "fixture",
            "checksum": "xyz",
            "downloaded_at": "2024-01-01T00:00:00Z",
        },
        "data": [
            {
                "ibge_id": "1001",
                "name": "Cidade X",
                "uf": "AX",
                "region": "Norte",
                "state": "Estado X",
                "intermediate_region": "Intermediária X",
                "immediate_region": "Imediata X",
                "mesoregion": "Mesorregião X",
                "microregion": "Microrregião X",
                "latitude": -10.0,
                "longitude": -45.0,
            },
            {
                "ibge_id": "1002",
                "name": "Capital X",
                "uf": "AX",
                "region": "Norte",
                "state": "Estado X",
                "latitude": -12.0,
                "longitude": -47.0,
                "capital": True,
                "bounding_box": {
                    "min_lat": -12.2,
                    "min_lon": -47.2,
                    "max_lat": -11.8,
                    "max_lon": -46.8,
                },
            },
        ],
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(catalog_module, "get_cache_path", lambda version=None: cache_path)

    result = catalog_module.load_city_catalog("test")
    entries = {entry["ibge_id"]: entry for entry in result["data"]}

    city = entries["1001"]
    assert city["coords"] == {"lat": -10.0, "lon": -45.0}
    assert city["state_capital"]["ibge_id"] == "1002"
    assert city["ibge_context"]["state_capital"]["coords"] == {"lat": -12.0, "lon": -47.0}

    capital = entries["1002"]
    assert capital["coords"] == {"lat": -12.0, "lon": -47.0}
    assert capital["bbox"] == {"south": -12.2, "west": -47.2, "north": -11.8, "east": -46.8}
    assert capital["ibge_context"]["state_capital"]["ibge_id"] == "1002"
