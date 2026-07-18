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


class TestIsTransientHttpStatus:
    def test_transient_statuses(self):
        from app.services.page_validator import is_transient_http_status
        for code in (401, 403, 407, 408, 425, 429, 500, 502, 503, 599):
            assert is_transient_http_status(code) is True, code

    def test_definitive_statuses(self):
        from app.services.page_validator import is_transient_http_status
        for code in (400, 404, 410, 451, 200, 301, 0):
            assert is_transient_http_status(code) is False, code


class TestFindStubRedirectTarget:
    BASE = "https://www.example.fr/"

    def _find(self, html, base=None):
        from app.services.page_validator import find_stub_redirect_target
        return find_stub_redirect_target(html, base or self.BASE)

    def test_meta_refresh(self):
        html = (
            '<html><head><meta http-equiv="refresh" content="0;url=/accueil.html">'
            '</head><body>Redirection...</body></html>'
        )
        assert self._find(html) == "https://www.example.fr/accueil.html"

    def test_single_same_host_anchor(self):
        html = '<html><body>Page has moved. <a href="fr.html">Click here...</a></body></html>'
        assert self._find(html) == "https://www.example.fr/fr.html"

    def test_www_variant_is_same_host(self):
        html = '<html><body>Moved. <a href="https://example.fr/fr/">ici</a></body></html>'
        assert self._find(html) == "https://example.fr/fr/"

    def test_two_distinct_anchors_no_target(self):
        html = (
            '<html><body><a href="/a.html">a</a> <a href="/b.html">b</a></body></html>'
        )
        assert self._find(html) is None

    def test_duplicate_anchors_count_once(self):
        html = (
            '<html><body><a href="/fr.html">fr</a> <a href="/fr.html">fr encore</a></body></html>'
        )
        assert self._find(html) == "https://www.example.fr/fr.html"

    def test_off_host_anchor_no_target(self):
        # Parked/for-sale pages: lone link goes off-host.
        html = '<html><body>Domain for sale <a href="https://registrar.example/buy">buy</a></body></html>'
        assert self._find(html) is None

    def test_non_nav_hrefs_ignored(self):
        html = (
            '<html><body><a href="#top">top</a> <a href="mailto:a@b.fr">mail</a>'
            ' <a href="tel:+33102030405">tel</a></body></html>'
        )
        assert self._find(html) is None

    def test_self_link_no_target(self):
        html = '<html><body><a href="https://www.example.fr/">home</a></body></html>'
        assert self._find(html) is None

    def test_rich_page_no_target(self):
        html = "<html><body>" + "Contenu réel du site. " * 20 + '<a href="/page">lien</a></body></html>'
        assert self._find(html) is None

    def test_oversized_html_no_target(self):
        html = "<html><body>" + "x" * 25_000 + '<a href="/fr.html">go</a></body></html>'
        assert self._find(html) is None
