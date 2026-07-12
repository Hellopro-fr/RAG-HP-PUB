"""Tests for CleanHTML markdownify RecursionError guard."""

from common_utils.cleaner import CleanHTML as mod
from common_utils.cleaner.CleanHTML import CleanHTML


def test_clean_converts_table_content():
    out = CleanHTML("<table><tr><td>hi</td></tr></table>").clean()
    assert "hi" in out


def test_clean_returns_empty_on_recursion_error(monkeypatch):
    def boom(self, soup):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(mod.MarkdownConverter, "convert_soup", boom)
    out = CleanHTML("<table><tr><td>hi</td></tr></table>").clean()
    assert out == ""
