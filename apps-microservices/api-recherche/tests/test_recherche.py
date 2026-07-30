"""Source-level regression tests for the DeepSeek V4 migration in recherche.py
(not importable locally: pulls pymilvus + live settings)."""

import pathlib

SRC = (
    pathlib.Path(__file__).resolve().parents[1] / "app" / "core" / "recherche.py"
).read_text(encoding="utf-8")


def test_no_retired_deepseek_model_names():
    # Quoted literals only — the names may appear in explanatory comments
    assert '"deepseek-chat"' not in SRC and "'deepseek-chat'" not in SRC
    assert '"deepseek-reasoner"' not in SRC and "'deepseek-reasoner'" not in SRC


def test_deepseek_default_is_v4_flash_with_thinking_disabled():
    assert '"deepseek-v4-flash"' in SRC
    assert '"thinking": {"type": "disabled"}' in SRC


def test_routing_accepts_both_v4_models():
    assert '"deepseek-v4-pro"' in SRC
    assert '"deepseek-v4-flash"' in SRC
