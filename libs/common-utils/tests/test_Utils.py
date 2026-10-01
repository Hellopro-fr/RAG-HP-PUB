"""Tests for Utils.to_valid_utf8 + sanitize_record UTF-8 hardening."""

from common_utils.database.Utils import Utils


def test_to_valid_utf8_strips_lone_surrogates():
    out = Utils.to_valid_utf8("abc\udca0def")
    assert out == "abcdef"
    out.encode("utf-8")  # must not raise — this is the Milvus-wire guarantee


def test_to_valid_utf8_strips_control_chars_but_keeps_tab_newline_cr():
    assert Utils.to_valid_utf8("a\x00b\x07c") == "abc"
    assert Utils.to_valid_utf8("a\tb\nc\rd") == "a\tb\nc\rd"


def test_to_valid_utf8_preserves_accented_text():
    assert Utils.to_valid_utf8("éàü caché — €") == "éàü caché — €"


def test_sanitize_record_cleans_strings_and_maps_none():
    rec = {"a": None, "b": "x\udca0y", "c": 5, "d": [1, 2]}
    out = Utils.sanitize_record(rec)
    assert out == {"a": "", "b": "xy", "c": 5, "d": [1, 2]}
    # every str value must now encode cleanly
    for v in out.values():
        if isinstance(v, str):
            v.encode("utf-8")
