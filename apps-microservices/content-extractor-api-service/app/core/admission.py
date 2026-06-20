"""In-process sync admission guard. SYNC_MAX_INFLIGHT=0 disables it (always admit).
Mirrors image-comparison's try_acquire/release slot model: the check + reserve are
synchronous with NO await between them, so there is no yield point and no race."""
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class SyncAdmission:
    def __init__(self, max_inflight: int) -> None:
        self._max = max_inflight
        self._inflight = 0

    def try_acquire(self) -> bool:
        if self._max <= 0:                       # disabled -> always admit
            return True
        if self._inflight >= self._max:
            return False
        self._inflight += 1
        return True

    def release(self) -> None:
        if self._max <= 0:
            return
        self._inflight = max(0, self._inflight - 1)


admission = SyncAdmission(settings.SYNC_MAX_INFLIGHT)
