from __future__ import annotations

import json
from pathlib import Path

from sentinela.services.publications import geo_cli


def test_geo_cli_enrich_command(tmp_path: Path) -> None:
    article_path = tmp_path / "article.json"
    article_path.write_text(
        json.dumps(
            {
                "id": "artigo-geo-1",
                "title": "Prefeito de Natal visita São Paulo",
                "body": (
                    "O prefeito de Natal participou de um encontro em São Paulo "
                    "para discutir políticas públicas."
                ),
            }
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "output.json"

    args = geo_cli._parse_args(  # type: ignore[attr-defined]
        [
            "enrich",
            str(article_path),
            "--output",
            str(output_path),
            "--pretty",
        ]
    )

    assert args.command == "enrich"
    exit_code = geo_cli._run_enrich(args)  # type: ignore[attr-defined]
    assert exit_code == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["article_id"] == "artigo-geo-1"
    assert any(city.get("name") == "São Paulo" for city in payload["mentioned_cities"])
    assert payload["metadata"]["catalog_version"]

