"""Source-level regression tests for the DeepSeek V4 migration.

classifier.py is not importable outside the Docker image (it imports
api_recherche_lib, assembled at build time), so these are source-scan
tripwires: the retired model name must never come back, and every DeepSeek
call must explicitly disable V4's default thinking mode.
"""

import pathlib

SRC = (
    pathlib.Path(__file__).resolve().parents[1] / "app" / "core" / "classifier.py"
).read_text(encoding="utf-8")


def test_no_retired_deepseek_model_names():
    # Quoted literals only — the names may appear in explanatory comments
    assert '"deepseek-chat"' not in SRC and "'deepseek-chat'" not in SRC
    assert '"deepseek-reasoner"' not in SRC and "'deepseek-reasoner'" not in SRC


def test_deepseek_calls_use_v4_flash_with_thinking_disabled():
    assert SRC.count('model="deepseek-v4-flash"') == 2  # summary + classification
    # V4 defaults thinking ON; both calls must disable it (cost + temp=0 determinism)
    assert SRC.count('"thinking": {"type": "disabled"}') == 2
