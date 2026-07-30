"""Source-scan tripwire (no JS test runner in this Next.js service):
the model picker must not reference retired DeepSeek model names."""

import pathlib

SRC = (
    pathlib.Path(__file__).resolve().parents[1] / "components" / "Header.jsx"
).read_text(encoding="utf-8")


def test_model_list_uses_live_deepseek_name():
    assert "deepseek-chat" not in SRC  # retired 2026-07-24
    assert "deepseek-v4-flash" in SRC
