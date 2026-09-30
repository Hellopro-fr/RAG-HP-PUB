"""debug=true and debug=false must select the same header/footer (R10 a).

extract_with_fallback (debug=false) and extract_all_debug (debug=true) are two
views of ONE decision: the debug payload exists to explain the production pick,
so it must return that pick. The assertions are order-agnostic on purpose —
they hold whichever strategy order is retained. Page shape: header_footer_pages.
"""

import pytest

pytest.importorskip("boilerpy3")

from common_utils.extractor.HeaderFooterExtractor import HeaderFooterExtractor

from header_footer_pages import MAIN_HTML, references

REFERENCE_HTMLS = references()


@pytest.fixture(scope="module")
def both_paths():
    prod = HeaderFooterExtractor(MAIN_HTML).extract_with_fallback(REFERENCE_HTMLS)
    debug = HeaderFooterExtractor(MAIN_HTML).extract_all_debug(REFERENCE_HTMLS)
    return prod, debug


def test_fixture_makes_strategies_disagree(both_paths):
    """Guard: the page must keep original and intersection apart, or the
    consistency tests below would pass for the wrong reason."""
    _, debug = both_paths
    assert debug["header_old"] == "Pompes Vannes Compresseurs"
    assert debug["header_structural"].startswith("Livraison gratuite")


@pytest.mark.parametrize("part", ["header", "footer"])
def test_debug_selects_what_production_selects(both_paths, part):
    prod, debug = both_paths
    assert debug[f"{part}_selected"] == prod[part]


@pytest.mark.parametrize("part", ["header", "footer"])
def test_debug_reports_the_production_method(both_paths, part):
    prod, debug = both_paths
    assert debug[f"{part}_method_used"] == prod[f"{part}_method"]
