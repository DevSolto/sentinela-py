from unittest.mock import MagicMock

import pytest
from pymongo.errors import OperationFailure

from sentinela.infrastructure.repositories.article_indexes import ensure_article_indexes


def test_ensure_article_indexes_ignores_existing_index_conflict():
    collection = MagicMock()
    error = OperationFailure(
        "Index already exists with a different name: portal_name_1_url_1",
        code=85,
        details={"errmsg": "Index already exists with a different name: portal_name_1_url_1"},
    )
    collection.create_index.side_effect = [error] + [None] * 7

    ensure_article_indexes(collection)

    assert collection.create_index.call_count == 8


def test_ensure_article_indexes_raises_for_unhandled_operation_failure():
    collection = MagicMock()
    error = OperationFailure("other failure", code=42, details={"errmsg": "other failure"})
    collection.create_index.side_effect = error

    with pytest.raises(OperationFailure):
        ensure_article_indexes(collection)
