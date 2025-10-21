from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from sentinela.services.publications.city_matching import CITY_CACHE_VERSION, get_cache_path, load_city_catalog
from sentinela.services.publications.city_matching.build_cache import CityCatalogError, build_cache, main


class _Response:
    def __init__(self, payload: list[dict[str, object]], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            from requests import HTTPError

            raise HTTPError(f"status {self.status_code}")


IBGE_SAMPLE = [
    {
        "id": 1100015,
        "nome": "Alta Floresta D'Oeste",
        "microrregiao": {
            "nome": "Cacoal",
            "mesorregiao": {
                "nome": "Leste Rondoniense",
                "UF": {
                    "id": 11,
                    "sigla": "RO",
                    "nome": "Rondônia",
                    "regiao": {"id": 1, "sigla": "N", "nome": "Norte"},
                },
            },
        },
    }
]

BRASILAPI_SAMPLE = [
    {
        "codigo_ibge": "1200013",
        "nome": "Acrelândia",
        "estado": "AC",
        "latitude": "-9.82581",
        "longitude": "-66.8972",
        "capital": False,
        "siafi_id": "0109",
        "ddd": "68",
        "fuso_horario": "America/Rio_Branco",
    }
]


def test_build_cache_from_ibge(tmp_path: Path) -> None:
    output = tmp_path / "municipios.json"

    with patch("sentinela.services.publications.city_matching.build_cache.requests.get") as mock_get:
        mock_get.return_value = _Response(IBGE_SAMPLE)
        build_cache(
            primary_source="ibge",
            output_path=output,
            refresh=True,
            version="test",
        )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metadata"]["source"] == "ibge"
    assert payload["metadata"]["record_count"] == 1
    assert payload["metadata"]["checksum"]
    assert payload["data"][0]["ibge_id"] == "1100015"
    assert payload["data"][0]["state"] == "Rondônia"


def test_build_cache_with_fallback(tmp_path: Path) -> None:
    output = tmp_path / "municipios.json"

    with patch("sentinela.services.publications.city_matching.build_cache.requests.get") as mock_get:
        mock_get.side_effect = [
            requests.RequestException("timeout"),
            _Response(BRASILAPI_SAMPLE),
        ]
        build_cache(
            primary_source="ibge",
            output_path=output,
            refresh=True,
            version="test",
        )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metadata"]["source"] == "brasilapi"
    assert payload["data"][0]["region"] == "Norte"
    assert payload["data"][0]["latitude"] == pytest.approx(-9.82581)


def test_build_cache_skips_when_not_refresh(tmp_path: Path) -> None:
    output = tmp_path / "municipios.json"
    output.write_text("{}", encoding="utf-8")

    with patch("sentinela.services.publications.city_matching.build_cache.fetch_catalog") as mock_fetch:
        build_cache(
            primary_source="ibge",
            output_path=output,
            refresh=False,
            version="test",
        )

    mock_fetch.assert_not_called()
    assert output.read_text(encoding="utf-8") == "{}"


def test_main_returns_error_on_failure(tmp_path: Path) -> None:
    with patch("sentinela.services.publications.city_matching.build_cache.fetch_catalog", side_effect=CityCatalogError("fail")):
        exit_code = main(["--output", str(tmp_path / "municipios.json"), "--source", "ibge", "--version", "test"])
    assert exit_code == 1


def test_load_city_catalog_reads_version(tmp_path: Path) -> None:
    path = get_cache_path("test")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "version": "test",
            "source": "ibge",
            "primary_source": "ibge",
            "downloaded_at": "2024-01-01T00:00:00Z",
            "record_count": 1,
            "checksum": "abc",
        },
        "data": [
            {"ibge_id": "1100015", "name": "Alta Floresta D'Oeste", "uf": "RO", "state": "Rondônia", "region": "Norte"}
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        loaded = load_city_catalog("test")
        assert loaded == payload
    finally:
        path.unlink()


def test_load_city_catalog_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_city_catalog("unknown")


def test_city_cache_version_constant_exposed() -> None:
    assert isinstance(CITY_CACHE_VERSION, str)
    assert CITY_CACHE_VERSION
