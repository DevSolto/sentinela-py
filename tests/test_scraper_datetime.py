from datetime import datetime

from sentinela.infrastructure.scraper import RequestsSoupScraper


def test_parse_datetime_handles_mixed_case_literals():
    scraper = RequestsSoupScraper()

    parsed = scraper._parse_datetime(
        "4 de novembro de 2024", date_format="%d DE %B DE %Y"
    )

    assert parsed == datetime(2024, 11, 4)
