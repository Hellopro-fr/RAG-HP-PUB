"""Auto-stash settings defaults (P2, Task 6)."""
from app.core.config import settings


def test_auto_stash_defaults():
    assert settings.AUTO_STASH_ENABLED is False
    assert settings.STASH_GRACE_SECONDS == 3600
    assert settings.STASH_SAFETY_TIMEOUT_SECONDS == 172800
    assert settings.STASH_DISK_HIGH_WATER_PCT == 85
    assert settings.STASH_MAX_PER_SWEEP == 5
