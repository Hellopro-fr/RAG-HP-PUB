"""Source-scan tripwire: default selected bot must be a live DeepSeek model."""

import pathlib

SRC = (
    pathlib.Path(__file__).resolve().parents[1] / "components" / "AIAssistantUI.jsx"
).read_text(encoding="utf-8")


def test_default_bot_is_live_deepseek_name():
    assert "deepseek-chat" not in SRC  # retired 2026-07-24
    assert "useState('deepseek-v4-flash')" in SRC
