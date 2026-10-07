from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC, second precision: round-trips exactly through MySQL DATETIME."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
