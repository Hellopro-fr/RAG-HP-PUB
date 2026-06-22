from boilerpy3 import extractors as Bpy

from app.core import extractor_core
from app.schemas.clean import OutputFormat

MAIN = "<html><body><header>Nav Home About</header><main>Real article body here.</main><footer>Copyright 2026 Contact</footer></body></html>"
REF1 = "<html><body><header>Nav Home About</header><main>Another page entirely.</main><footer>Copyright 2026 Contact</footer></body></html>"
REF2 = "<html><body><header>Nav Home About</header><main>Third distinct page.</main><footer>Copyright 2026 Contact</footer></body></html>"


def test_clean_core_text_matches_boilerpy():
    expected = Bpy.DefaultExtractor().get_content(MAIN)
    assert extractor_core.clean_core(MAIN, OutputFormat.TEXT) == expected


def test_clean_core_html_matches_boilerpy():
    expected = Bpy.KeepEverythingExtractor().get_marked_html(MAIN)
    assert extractor_core.clean_core(MAIN, OutputFormat.HTML) == expected


def test_header_footer_core_basic_keys():
    body = extractor_core.header_footer_core(MAIN, [REF1, REF2], debug=False)
    assert set(body) == {"header", "footer", "header_method", "footer_method"}


def test_header_footer_core_debug_keys():
    body = extractor_core.header_footer_core(MAIN, [REF1, REF2], debug=True)
    for k in ("strategies", "intersections_class", "intersections_structural",
              "cleaned_htmls", "gap_analysis", "header_method", "footer_method"):
        assert k in body
