from datetime import datetime

import pytest

from sentinela.infrastructure.scraper import RequestsSoupScraper


def test_parse_datetime_handles_mixed_case_literals():
    scraper = RequestsSoupScraper()

    parsed = scraper._parse_datetime(
        "4 de novembro de 2024", date_format="%d DE %B DE %Y"
    )

    assert parsed == datetime(2024, 11, 4)


@pytest.mark.parametrize(
    "value",
    [
        "2025-10-24T22:39:27+00:00",
        "2025-10-24T19:39:27-03:00",
        "2025-10-24 22:39:27+00:00",
    ],
)
def test_parse_datetime_accepts_iso8601_with_timezone(value: str):
    scraper = RequestsSoupScraper()

    parsed = scraper._parse_datetime(value, date_format="%Y-%m-%d")

    assert parsed == datetime(2025, 10, 24, 22, 39, 27)


def test_parse_datetime_handles_brazilian_format_with_literal_text():
    scraper = RequestsSoupScraper()

    parsed = scraper._parse_datetime(
        "Publicado em 24/10/2025 às 21h15 • atualizado em 25/10/2025 às 10h00",
        date_format=r"(?P<published>\d{2}/\d{2}/\d{4} às \d{2}h\d{2})",
    )

    assert parsed == datetime(2025, 10, 24, 21, 15)
