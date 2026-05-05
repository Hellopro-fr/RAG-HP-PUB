import pytest
from app.services.scraper import ScrapeResult


class TestScrapeResultShape:
    def test_minimal_construction(self):
        r = ScrapeResult(html="<html></html>", final_url="https://example.com/", status_code=200)
        assert r.html == "<html></html>"
        assert r.final_url == "https://example.com/"
        assert r.status_code == 200
        assert r.content_type == ""
        assert r.headers == {}

    def test_full_construction(self):
        r = ScrapeResult(
            html="<html></html>",
            final_url="https://example.com/",
            status_code=404,
            content_type="text/html; charset=utf-8",
            headers={"server": "nginx"},
        )
        assert r.status_code == 404
        assert r.content_type.startswith("text/html")
        assert r.headers["server"] == "nginx"


from unittest.mock import AsyncMock, MagicMock, patch


class TestScrapeHtmlReturnsScrapeResult:
    @pytest.mark.asyncio
    async def test_returns_scrape_result_with_status_code(self):
        """scrape_html captures response.status and returns ScrapeResult."""
        from app.services import scraper

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "text/html"}

        mock_page = MagicMock()
        mock_page.goto = AsyncMock(return_value=mock_response)
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>" + "x" * 200 + "</body></html>")
        mock_page.url = "https://example.com/final"
        mock_page.unroute_all = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.route = AsyncMock()
        mock_page.on = MagicMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()
        mock_context.add_cookies = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_pw = MagicMock()
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.scraper.async_playwright", return_value=mock_pw), \
             patch("app.services.scraper._launch_browser",
                   AsyncMock(return_value=(mock_browser, False))):
            result = await scraper.scrape_html(
                "https://example.com/",
                proxy="http://auto:pw@proxy.apify.com:8000",
            )

        assert result is not None
        assert isinstance(result, scraper.ScrapeResult)
        assert result.status_code == 200
        assert result.final_url == "https://example.com/final"
        assert "<html>" in result.html

    @pytest.mark.asyncio
    async def test_status_code_zero_when_no_response(self):
        """When Playwright returns no Response, status_code defaults to 0."""
        from app.services import scraper

        mock_page = MagicMock()
        mock_page.goto = AsyncMock(return_value=None)
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>" + "x" * 200 + "</body></html>")
        mock_page.url = "https://example.com/"
        mock_page.unroute_all = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.route = AsyncMock()
        mock_page.on = MagicMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()
        mock_context.add_cookies = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_pw = MagicMock()
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.scraper.async_playwright", return_value=mock_pw), \
             patch("app.services.scraper._launch_browser",
                   AsyncMock(return_value=(mock_browser, False))):
            result = await scraper.scrape_html(
                "https://example.com/",
                proxy="http://auto:pw@proxy.apify.com:8000",
            )

        assert result is not None
        assert result.status_code == 0
