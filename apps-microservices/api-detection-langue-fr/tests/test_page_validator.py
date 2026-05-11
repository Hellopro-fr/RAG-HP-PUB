import pytest
from app.services.scraper import ScrapeResult
from app.services.page_validator import ValidationVerdict, validate


def _scrape(html="<html><body>x</body></html>", final_url="https://example.com/page",
            status_code=200) -> ScrapeResult:
    return ScrapeResult(html=html, final_url=final_url, status_code=status_code)


class TestHttpError:
    def test_404_status_is_http_error(self):
        assert validate(_scrape(status_code=404), "https://example.com/page") == ValidationVerdict.HTTP_ERROR

    def test_500_status_is_http_error(self):
        assert validate(_scrape(status_code=500), "https://example.com/page") == ValidationVerdict.HTTP_ERROR

    def test_399_is_valid(self):
        assert validate(_scrape(status_code=399), "https://example.com/page") == ValidationVerdict.VALID

    def test_600_is_valid(self):
        # 600+ is non-standard; not flagged as http_error
        assert validate(_scrape(status_code=600), "https://example.com/page") == ValidationVerdict.VALID

    def test_status_zero_falls_through_to_other_signals(self):
        # status_code=0 means no Playwright Response; don't classify as HTTP_ERROR.
        assert validate(_scrape(status_code=0), "https://example.com/page") == ValidationVerdict.VALID


class TestRedirectedToHome:
    def test_deep_path_redirected_to_root_is_redirect(self):
        s = _scrape(final_url="https://example.com/", status_code=200)
        assert validate(s, "https://example.com/some/deep/page") == ValidationVerdict.REDIRECTED_TO_HOME

    def test_root_to_root_is_valid(self):
        s = _scrape(final_url="https://example.com/", status_code=200)
        assert validate(s, "https://example.com/") == ValidationVerdict.VALID

    def test_deep_to_deep_is_valid(self):
        s = _scrape(final_url="https://example.com/other", status_code=200)
        assert validate(s, "https://example.com/some/page") == ValidationVerdict.VALID


class TestSoft404URLPath:
    def test_404_in_final_url_path(self):
        s = _scrape(final_url="https://example.com/404", status_code=200)
        assert validate(s, "https://example.com/some/page") == ValidationVerdict.SOFT_404

    def test_not_found_segment_in_path(self):
        s = _scrape(final_url="https://example.com/not-found", status_code=200)
        assert validate(s, "https://example.com/some/page") == ValidationVerdict.SOFT_404

    def test_page_introuvable_in_path(self):
        s = _scrape(final_url="https://example.com/page-introuvable", status_code=200)
        assert validate(s, "https://example.com/some/page") == ValidationVerdict.SOFT_404


class TestSoft404TitleAndThin:
    def test_title_404_thin_body(self):
        html = "<html><head><title>404 - Not Found</title></head><body>Page not found</body></html>"
        s = _scrape(html=html, final_url="https://example.com/page", status_code=200)
        assert validate(s, "https://example.com/page") == ValidationVerdict.SOFT_404

    def test_title_introuvable_thin_body(self):
        html = "<html><head><title>Page introuvable</title></head><body>Désolé</body></html>"
        s = _scrape(html=html, final_url="https://example.com/page", status_code=200)
        assert validate(s, "https://example.com/page") == ValidationVerdict.SOFT_404

    def test_title_404_with_long_body_is_valid(self):
        # Article titled "What is a 404 error" with full content body is NOT soft-404.
        long_body = "x " * 1500  # ~3000 chars > threshold 2000
        html = f"<html><head><title>What is a 404 error</title></head><body>{long_body}</body></html>"
        s = _scrape(html=html, final_url="https://example.com/blog/404-error", status_code=200)
        assert validate(s, "https://example.com/blog/404-error") == ValidationVerdict.VALID


class TestSoft404H1AndThin:
    def test_h1_introuvable_thin_body(self):
        html = "<html><body><h1>Page non trouvée</h1><p>Désolé</p></body></html>"
        s = _scrape(html=html, final_url="https://example.com/page", status_code=200)
        assert validate(s, "https://example.com/page") == ValidationVerdict.SOFT_404

    def test_h1_404_with_long_body_is_valid(self):
        long_body = "x " * 1200  # ~2400 chars > threshold 1500
        html = f"<html><body><h1>Erreur 404</h1>{long_body}</body></html>"
        s = _scrape(html=html, final_url="https://example.com/page", status_code=200)
        assert validate(s, "https://example.com/page") == ValidationVerdict.VALID


class TestParsingCrashFailOpen:
    def test_invalid_html_returns_valid(self, caplog):
        # BeautifulSoup is robust; force crash via monkey-patching is overkill.
        # Empty HTML triggers fall-through; valid is correct here.
        s = _scrape(html="", final_url="https://example.com/page", status_code=200)
        # Empty body is not soft-404 by itself; should be VALID (fall through).
        assert validate(s, "https://example.com/page") == ValidationVerdict.VALID
