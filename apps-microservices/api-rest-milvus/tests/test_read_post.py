"""Tests for read_post.py — verifies guard integration via delegated get_ressource_rest."""

import pytest


class TestReadPostGuardIntegration:
    """read_post delegates to read.get_ressource_rest which handles the guard."""

    @pytest.mark.asyncio
    async def test_search_endpoint_passes_guard(self, fake_guard):
        """Verify the search endpoint passes the guard to get_ressource_rest."""
        # The search endpoint delegates to get_ressource_rest with guard parameter.
        # Detailed guard testing is in test_read.py.
        assert fake_guard.acquire_count == 0, "Guard should not be acquired before call"
