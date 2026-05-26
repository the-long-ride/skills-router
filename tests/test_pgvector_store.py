"""Tests for pgvector store helpers."""

import pytest

from skills_router.storage.pgvector_store import PgVectorBrainIndexStore, _vector_literal


def test_pgvector_requires_dsn():
    with pytest.raises(ValueError, match="pgvector_dsn"):
        PgVectorBrainIndexStore("", connect=lambda _dsn: None)


def test_vector_literal_accepts_384_dimensions():
    literal = _vector_literal([0.1] * 384)

    assert literal is not None
    assert literal.startswith("[")
    assert literal.endswith("]")


def test_vector_literal_rejects_wrong_dimensions():
    assert _vector_literal([0.1, 0.2]) is None
