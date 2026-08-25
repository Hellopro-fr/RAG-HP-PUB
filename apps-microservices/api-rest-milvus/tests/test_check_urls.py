"""Tests for check_urls.py — verifies guard wraps each batch query."""

import pytest
from unittest.mock import MagicMock, patch

from tests.conftest import FakeGuard


class TestCheckUrlsGuardIntegration:
    """Verify that check_urls batch loop acquires a slot per query."""

    @pytest.mark.asyncio
    async def test_guard_slot_per_batch_in_check(self, fake_guard, mock_collection):
        """Each batch query in _check_urls_batch should get its own slot."""
        mock_collection.query.return_value = [
            {"url": "https://example.com/page1", "page_type": "content"},
        ]

        from app.router.check_urls import _check_urls_batch

        result = await _check_urls_batch(
            guard=fake_guard,
            collection=mock_collection,
            urls_to_check=["https://example.com/page1"],
        )

        assert fake_guard.acquire_count == 1
        assert fake_guard.release_count == 1
        assert "https://example.com/page1" in result["found_urls"]

    @pytest.mark.asyncio
    async def test_batch_no_longer_reports_header_footer(self, fake_guard, mock_collection):
        """has_header/has_footer must NOT come back from the URL-scoped batch.

        They were a side effect of a query filtered on the URLs being checked, so
        they were only true when the exact page carrying the record happened to be
        in the list. Header/footer is a property of the DOMAIN — it now has its own
        query. Returning it here again would re-open the false negative.
        """
        mock_collection.query.return_value = [
            {"url": "https://example.com/page1", "page_type": "header"},
        ]

        from app.router.check_urls import _check_urls_batch

        result = await _check_urls_batch(
            guard=fake_guard,
            collection=mock_collection,
            urls_to_check=["https://example.com/page1"],
        )

        assert "has_header" not in result
        assert "has_footer" not in result
        # ...and a header record is still excluded from the found URLs.
        assert result["found_urls"] == set()


class TestDomainHeaderFooter:
    """_check_domain_header_footer queries by DOMAIN, not by URL."""

    @pytest.mark.asyncio
    async def test_scopes_the_query_to_the_domain_and_both_page_types(
        self, fake_guard, mock_collection
    ):
        mock_collection.query.return_value = [
            {"page_type": "header"},
            {"page_type": "footer"},
        ]

        from app.router.check_urls import _check_domain_header_footer

        result = await _check_domain_header_footer(
            guard=fake_guard, collection=mock_collection, domain="ld-packaging.fr"
        )

        assert result == {"has_header": True, "has_footer": True}
        assert fake_guard.acquire_count == 1
        assert fake_guard.release_count == 1

        expr = mock_collection.query.call_args.kwargs["expr"]
        assert "domaine == 'ld-packaging.fr'" in expr
        assert "page_type in ['header', 'footer']" in expr
        # The URL the record hangs on is irrelevant — filtering on it is the bug.
        assert "url" not in expr
        # chunk_number is a dedup filter for URL counting; nothing proves the
        # header/footer rows carry it, so it must not gate an existence check.
        assert "chunk_number" not in expr

    @pytest.mark.asyncio
    async def test_header_alone_does_not_imply_footer(self, fake_guard, mock_collection):
        mock_collection.query.return_value = [{"page_type": "header"}]

        from app.router.check_urls import _check_domain_header_footer

        result = await _check_domain_header_footer(
            guard=fake_guard, collection=mock_collection, domain="example.com"
        )

        assert result == {"has_header": True, "has_footer": False}

    @pytest.mark.asyncio
    async def test_no_records_means_neither(self, fake_guard, mock_collection):
        mock_collection.query.return_value = []

        from app.router.check_urls import _check_domain_header_footer

        result = await _check_domain_header_footer(
            guard=fake_guard, collection=mock_collection, domain="yara.fr"
        )

        assert result == {"has_header": False, "has_footer": False}

    @pytest.mark.asyncio
    async def test_quote_in_domain_is_escaped(self, fake_guard, mock_collection):
        """A quote in the domain must not break out of the filter expression."""
        mock_collection.query.return_value = []

        from app.router.check_urls import _check_domain_header_footer

        await _check_domain_header_footer(
            guard=fake_guard, collection=mock_collection, domain="o'brien.fr"
        )

        expr = mock_collection.query.call_args.kwargs["expr"]
        assert "o\\'brien.fr" in expr
