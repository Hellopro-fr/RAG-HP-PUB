"""Tests for the RecursionError guard around markdownify in TrafilaturaCleaning."""

import sys

from bs4 import BeautifulSoup

from common_utils.cleaner import TrafilaturaCleaning as tc
from common_utils.cleaner.TrafilaturaCleaning import TrafilaturaHp, _md_safe


def _boom(*args, **kwargs):
    raise RecursionError("maximum recursion depth exceeded")


def test_md_safe_converts_html():
    assert "Titre" in _md_safe("<h1>Titre</h1>", heading_style="ATX")


def test_md_safe_returns_empty_on_recursion_error(monkeypatch):
    monkeypatch.setattr(tc, "md", _boom)
    assert _md_safe("<b>x</b>", heading_style="ATX") == ""


def test_extract_article_skips_recursion_failures(monkeypatch):
    monkeypatch.setattr(tc, "md", _boom)
    hp = TrafilaturaHp({"url": "https://ex.com", "content": "", "fetch": False})
    soup = BeautifulSoup('<article class="product">x</article>', "html.parser")
    assert hp.extract_article(soup) is None


def test_deeply_nested_main_page_does_not_raise():
    """A Liferay-style page whose DOM depth exceeds the recursion limit must
    degrade to empty content (cascade fallback) instead of raising."""
    depth = 800
    nested = "<strong>" * depth + "x" + "</strong>" * depth
    html = f"<html><body><main>{nested}</main></body></html>"

    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(1000)
    try:
        hp = TrafilaturaHp({"url": "https://ex.com/deep", "content": html, "fetch": False})
        res = hp.extract()
    finally:
        sys.setrecursionlimit(limit)

    assert res.content == ""
