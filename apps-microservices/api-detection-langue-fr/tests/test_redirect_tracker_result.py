import pytest
from unittest.mock import AsyncMock, patch
from app.services.scraper import ScrapeResult


class TestFetchHtmlReturnsScrapeResult:
    @pytest.mark.asyncio
    async def test_phase_1_returns_scrape_result(self):
        from app.services import redirect_tracker

        scrape = ScrapeResult(
            html="<html>FR</html>",
            final_url="https://example.com/",
            status_code=200,
        )
        with patch("app.services.redirect_tracker.scrape_html",
                   AsyncMock(return_value=scrape)):
            result = await redirect_tracker.fetch_html(
                "https://example.com/", proxy="http://auto:pw@proxy.apify.com:8000"
            )
        assert isinstance(result, ScrapeResult)
        assert result.status_code == 200
        assert result.html == "<html>FR</html>"

    @pytest.mark.asyncio
    async def test_phase_2_variant_fallback_returns_scrape_result(self):
        """When Phase 1 hits a variant-eligible error, Phase 2 retries variants."""
        from app.services import redirect_tracker

        variant_scrape = ScrapeResult(
            html="<html>FR</html>",
            final_url="http://example.com/",
            status_code=200,
        )

        side_effects = [
            Exception("page.goto: net::ERR_SSL_PROTOCOL_ERROR at https://www.example.com/"),
            variant_scrape,
        ]
        with patch("app.services.redirect_tracker.scrape_html",
                   AsyncMock(side_effect=side_effects)):
            result = await redirect_tracker.fetch_html(
                "https://www.example.com/", proxy="http://auto:pw@proxy.apify.com:8000"
            )
        assert isinstance(result, ScrapeResult)
        assert result.status_code == 200
        assert result.final_url == "http://example.com/"

    @pytest.mark.asyncio
    async def test_returns_none_on_complete_failure(self):
        from app.services import redirect_tracker

        with patch("app.services.redirect_tracker.scrape_html",
                   AsyncMock(return_value=None)):
            result = await redirect_tracker.fetch_html(
                "https://example.com/", proxy="http://auto:pw@proxy.apify.com:8000"
            )
        assert result is None
