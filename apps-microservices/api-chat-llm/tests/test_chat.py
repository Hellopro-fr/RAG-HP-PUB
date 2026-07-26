"""Source-level regression tests for the DeepSeek V4 migration in chat.py
(not importable locally: pulls google-genai + live settings)."""

import pathlib

SRC = (
    pathlib.Path(__file__).resolve().parents[1] / "app" / "core" / "chat.py"
).read_text(encoding="utf-8")


def test_no_retired_deepseek_model_names():
    # Quoted literals only — the names may appear in explanatory comments
    assert '"deepseek-chat"' not in SRC and "'deepseek-chat'" not in SRC
    assert '"deepseek-reasoner"' not in SRC and "'deepseek-reasoner'" not in SRC


def test_deepseek_defaults_are_v4_flash():
    # DeepSeek class hardcode + LLMProvider default
    assert SRC.count('"deepseek-v4-flash"') == 2


def test_thinking_disabled_for_deepseek_paths():
    assert '"thinking": {"type": "disabled"}' in SRC
