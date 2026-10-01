"""Source-level regression test: DEEPSEEK_MODEL default must be a live V4 name
(config.py may not be importable locally without pydantic-settings)."""

import pathlib

SRC = (
    pathlib.Path(__file__).resolve().parents[1] / "app" / "config.py"
).read_text(encoding="utf-8")


def test_deepseek_model_default_is_v4_flash():
    assert "deepseek-chat" not in SRC  # retired 2026-07-24
    assert 'DEEPSEEK_MODEL: str = "deepseek-v4-flash"' in SRC
