"""Characterization of extract_with_fallback, the production path (R10 a).

Freezes the exact production output before its selection logic is shared with
extract_all_debug: one case per branch of the Structural -> Class -> Original
cascade, the per-part merge, the method labels and the key order. Expected
values were recorded from the code at ddef39eb, not derived from the new table.
The call-sequence test freezes the short-circuit, so the refactor does not buy
its correctness with extra boilerpy3 runs.
"""

import pytest

pytest.importorskip("boilerpy3")

from common_utils.extractor.HeaderFooterExtractor import HeaderFooterExtractor

from header_footer_pages import (
    MAIN,
    MAIN_HTML,
    OTHER_BOTTOM,
    WRAPPED_BOTTOM,
    WRAPPED_TOP,
    page,
    references,
)

FULL_HEADER = (
    "Livraison gratuite des 50 euros HT Service client 01 23 45 67 89 du lundi "
    "au vendredi Acme Industrie Pompes Vannes Compresseurs"
)
NAV_HEADER = "Pompes Vannes Compresseurs"
FULL_FOOTER = "Copyright 2026 Acme Industrie Mentions legales Contact"
STRUCTURAL_BOTH = "Fallback (boilerpy3 Structural Intersection)"
STRUCTURAL = "Fallback (Structural)"
CLASS = "Fallback (Class)"
ORIGINAL = "Original (Semantic/CSS Pattern)"

# id -> (main html, reference htmls, expected output in key order, calls made)
CASES = {
    "structural_both": (
        MAIN_HTML,
        references(),
        [("header", FULL_HEADER), ("header_method", STRUCTURAL_BOTH),
         ("footer", FULL_FOOTER), ("footer_method", STRUCTURAL_BOTH)],
        ["structural"],
    ),
    "structural_header_class_footer": (
        MAIN_HTML,
        references(bottom=WRAPPED_BOTTOM),
        [("header", FULL_HEADER), ("header_method", STRUCTURAL),
         ("footer", FULL_FOOTER), ("footer_method", CLASS)],
        ["structural", "class"],
    ),
    "class_header_structural_footer": (
        MAIN_HTML,
        references(top=WRAPPED_TOP),
        [("header", FULL_HEADER), ("header_method", CLASS),
         ("footer", FULL_FOOTER), ("footer_method", STRUCTURAL)],
        ["structural", "class"],
    ),
    "class_both": (
        MAIN_HTML,
        references(top=WRAPPED_TOP, bottom=WRAPPED_BOTTOM),
        [("header", FULL_HEADER), ("header_method", CLASS),
         ("footer", FULL_FOOTER), ("footer_method", CLASS)],
        ["structural", "class"],
    ),
    "structural_header_original_footer": (
        MAIN_HTML,
        references(bottom=OTHER_BOTTOM),
        [("header", FULL_HEADER), ("header_method", STRUCTURAL),
         ("footer", FULL_FOOTER), ("footer_method", ORIGINAL)],
        ["structural", "class", "original footer"],
    ),
    "structural_header_no_footer": (
        page(*MAIN, bottom=""),
        references(bottom=OTHER_BOTTOM),
        [("header", FULL_HEADER), ("header_method", STRUCTURAL),
         ("footer", ""), ("footer_method", "None")],
        ["structural", "class", "original footer"],
    ),
    "original_both_without_references": (
        MAIN_HTML,
        [],
        [("header", NAV_HEADER), ("header_method", ORIGINAL),
         ("footer", FULL_FOOTER), ("footer_method", ORIGINAL)],
        ["structural", "class", "original header", "original footer"],
    ),
    "nothing_found": (
        page(*MAIN, top="<div><p>x</p></div>", bottom=""),
        [],
        [("header", ""), ("header_method", "None"),
         ("footer", ""), ("footer_method", "None")],
        ["structural", "class", "original header", "original footer"],
    ),
    "unparsable_input": (
        None,
        references(),
        [("header", ""), ("header_method", "None"),
         ("footer", ""), ("footer_method", "None")],
        [],
    ),
}


@pytest.fixture
def calls(monkeypatch):
    """Record which strategies production runs, in order."""
    seen = []
    run = HeaderFooterExtractor.run_intersection_logic
    header = HeaderFooterExtractor.extract_header
    footer = HeaderFooterExtractor.extract_footer

    def spy_run(self, reference_htmls, strategy="class", gap_config=None):
        seen.append(strategy)
        return run(self, reference_htmls, strategy=strategy, gap_config=gap_config)

    def spy_header(self, soup):
        seen.append("original header")
        return header(self, soup)

    def spy_footer(self, soup):
        seen.append("original footer")
        return footer(self, soup)

    monkeypatch.setattr(HeaderFooterExtractor, "run_intersection_logic", spy_run)
    monkeypatch.setattr(HeaderFooterExtractor, "extract_header", spy_header)
    monkeypatch.setattr(HeaderFooterExtractor, "extract_footer", spy_footer)
    return seen


@pytest.mark.parametrize("case", CASES)
def test_production_output_is_frozen(case):
    main_html, reference_htmls, expected, _ = CASES[case]
    result = HeaderFooterExtractor(main_html).extract_with_fallback(reference_htmls)
    assert list(result.items()) == expected


@pytest.mark.parametrize("case", CASES)
def test_production_short_circuit_is_frozen(case, calls):
    main_html, reference_htmls, _, expected_calls = CASES[case]
    HeaderFooterExtractor(main_html).extract_with_fallback(reference_htmls)
    assert calls == expected_calls
