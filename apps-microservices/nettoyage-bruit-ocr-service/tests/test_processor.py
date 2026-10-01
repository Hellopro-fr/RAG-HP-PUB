"""JSON escape sanitization — now testing the REAL implementation.

Until 20-08-2026 this file carried its own copy of the regex, with the comment
"Reproduces the sanitization logic from processor.py". Two copies that could drift apart
without any of these 15 tests going red — the sanitization could have been fixed in
production and these tests would still have vouched for the old behaviour.

The regex now lives in a single named function, `processor.sanitize_json_escapes`, which
`_process_single_message` calls. This file imports it.
"""
import inspect
import json

import pytest

from app.core.processor import parse_llm_json, sanitize_json_escapes


def test_the_tested_functions_are_the_real_ones():
    """Anti-false-green guard: if `app` were stubbed, these would be MagicMocks.

    A MagicMock returns a MagicMock, which is truthy — every assertion below would pass
    on nothing at all.
    """
    for fn, nom in ((sanitize_json_escapes, "sanitize_json_escapes"),
                    (parse_llm_json, "parse_llm_json")):
        assert inspect.isfunction(fn), (
            "%s is not a real function (%r): the service package is stubbed. "
            "Run with PYTHONPATH=. from the service root." % (nom, type(fn))
        )
        assert fn.__module__.endswith("processor")


class TestJsonEscapeSanitization:
    def test_valid_json_unchanged(self):
        raw = '{"contenu": "texte normal sans backslash"}'
        assert json.loads(sanitize_json_escapes(raw)) == {"contenu": "texte normal sans backslash"}

    def test_ok_response_unchanged(self):
        raw = '{"contenu": "ok"}'
        assert json.loads(sanitize_json_escapes(raw)) == {"contenu": "ok"}

    def test_valid_escapes_preserved(self):
        raw = '{"contenu": "line1\\nline2\\ttab"}'
        result = json.loads(sanitize_json_escapes(raw))
        assert result["contenu"] == "line1\nline2\ttab"

    def test_invalid_escape_fixed(self):
        raw = '{"contenu": "test\\evalue"}'
        result = json.loads(sanitize_json_escapes(raw))
        assert result["contenu"] == "test\\evalue"

    def test_invalid_escape_backslash_s(self):
        raw = '{"contenu": "R.C.S. Strasbourg\\sSIRET"}'
        result = json.loads(sanitize_json_escapes(raw))
        assert result["contenu"] == "R.C.S. Strasbourg\\sSIRET"

    def test_invalid_escape_backslash_a(self):
        raw = '{"contenu": "article\\article"}'
        result = json.loads(sanitize_json_escapes(raw))
        assert result["contenu"] == "article\\article"

    def test_multiple_invalid_escapes(self):
        raw = '{"contenu": "\\alpha \\delta \\gamma"}'
        result = json.loads(sanitize_json_escapes(raw))
        assert result["contenu"] == "\\alpha \\delta \\gamma"

    def test_mixed_valid_and_invalid_escapes(self):
        raw = '{"contenu": "line\\n\\ebreak"}'
        result = json.loads(sanitize_json_escapes(raw))
        assert result["contenu"] == "line\n\\ebreak"

    def test_backslash_b_is_valid_json_escape(self):
        """\\b is a valid JSON escape (backspace) — regex correctly preserves it."""
        raw = '{"contenu": "test\\bvalue"}'
        result = json.loads(sanitize_json_escapes(raw))
        assert result["contenu"] == "test\x08value"

    def test_unicode_escape_preserved(self):
        raw = '{"contenu": "euro\\u20ac sign"}'
        result = json.loads(sanitize_json_escapes(raw))
        assert result["contenu"] == "euro\u20ac sign"

    def test_empty_contenu(self):
        raw = '{"contenu": ""}'
        result = json.loads(sanitize_json_escapes(raw))
        assert result["contenu"] == ""


class TestJsonParseFallback:
    def test_fallback_on_double_escaped_backslash(self):
        """Already-escaped \\\\ followed by invalid escape char — regex breaks it."""
        raw = '{"contenu": "already\\\\escaped"}'
        result = parse_llm_json(raw)
        assert result["contenu"] == "ok"

    def test_regex_handles_escaped_backslash_then_asterisk(self):
        """\\\\\\* is properly sanitized without needing fallback."""
        raw = '{"contenu": "complex\\\\\\*mixed"}'
        result = parse_llm_json(raw)
        assert "complex" in result["contenu"]

    def test_normal_json_still_parsed(self):
        raw = '{"contenu": "texte nettoyé sans problème"}'
        result = parse_llm_json(raw)
        assert result["contenu"] == "texte nettoyé sans problème"

    def test_invalid_escape_fixed_before_fallback(self):
        raw = '{"contenu": "test\\evalue"}'
        result = parse_llm_json(raw)
        assert result["contenu"] == "test\\evalue"