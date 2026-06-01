"""Move-flow settings defaults (P3, Task 10)."""
from app.core.config import settings


def test_move_defaults():
    assert settings.MOVE_REQUESTS_PATH == "/app/gcs-move-requests"
    assert settings.MOVE_RESULTS_PATH == "/app/gcs-move-results"
    assert settings.MOVE_SOURCE_PREFIX == "stash"
    assert settings.MOVE_TARGET_PREFIX == "crawls"
    assert settings.MOVE_TIMEOUT_SECONDS == 120
