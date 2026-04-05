import re
import json
import pytest


def sanitize_json_escapes(json_string: str) -> str:
    """Reproduces the sanitization logic from processor.py"""
    return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_string)


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