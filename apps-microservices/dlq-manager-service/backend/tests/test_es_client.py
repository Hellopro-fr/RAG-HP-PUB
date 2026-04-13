"""
Tests for ElasticsearchClient._build_query search routing logic.

These are unit tests that do NOT require a live Elasticsearch connection.
The method is tested as a pure function via a mock client.
"""
import re
import pytest
from unittest.mock import MagicMock

# Bootstrap the import without a real ES connection
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.es_client import ElasticsearchClient


@pytest.fixture()
def client():
    """Return an ElasticsearchClient with a mock underlying ES client."""
    return ElasticsearchClient(client=MagicMock())


class TestBuildQuerySearchRouting:
    """Verify the three routing branches in _build_query."""

    def test_quoted_field_value_routes_to_match_phrase(self, client):
        """error_reason:'...' must produce a match_phrase clause, not query_string."""
        query = client._build_query(
            filters={},
            search_term="error_reason:'Exception(\"Erreur: OSError\")'",
        )
        must = query["bool"]["must"]
        assert len(must) == 1
        clause = must[0]
        assert "match_phrase" in clause, f"Expected match_phrase, got: {clause}"
        assert "error_reason" in clause["match_phrase"]
        assert clause["match_phrase"]["error_reason"] == 'Exception("Erreur: OSError")'
        assert "query_string" not in clause

    def test_quoted_field_value_with_double_quotes(self, client):
        """error_reason:\"...\" (double-quoted) must also route to match_phrase."""
        query = client._build_query(
            filters={},
            search_term='service_name:"my-complex: service"',
        )
        must = query["bool"]["must"]
        assert len(must) == 1
        clause = must[0]
        assert "match_phrase" in clause
        assert clause["match_phrase"]["service_name"] == "my-complex: service"

    def test_unquoted_field_value_routes_to_query_string(self, client):
        """service_name:my-service (unquoted colon syntax) must use query_string."""
        query = client._build_query(
            filters={},
            search_term="service_name:my-service",
        )
        must = query["bool"]["must"]
        assert len(must) == 1
        clause = must[0]
        assert "query_string" in clause, f"Expected query_string, got: {clause}"
        assert clause["query_string"]["query"] == "service_name:my-service"

    def test_simple_term_gets_wildcard_wrapping(self, client):
        """Plain search term without special chars must be wrapped with wildcards."""
        query = client._build_query(filters={}, search_term="timeout")
        must = query["bool"]["must"]
        assert len(must) == 1
        clause = must[0]
        assert "query_string" in clause
        assert clause["query_string"]["query"] == "*timeout*"

    def test_wildcard_term_routes_to_query_string(self, client):
        """Terms with * or ? must go through query_string without extra wrapping."""
        query = client._build_query(filters={}, search_term="error_*")
        must = query["bool"]["must"]
        clause = must[0]
        assert "query_string" in clause
        assert clause["query_string"]["query"] == "error_*"

    def test_empty_search_term_produces_no_must_clause(self, client):
        """No search_term must not add any clause to bool.must."""
        query = client._build_query(filters={}, search_term="")
        assert query["bool"]["must"] == []

    def test_none_search_term_produces_no_must_clause(self, client):
        """None search_term must not add any clause to bool.must."""
        query = client._build_query(filters={}, search_term=None)
        assert query["bool"]["must"] == []
