"""Tests for the AdmissionController class."""
import asyncio
import pytest


class TestAdmissionController:
    """Core acquire/release logic."""

    @pytest.mark.asyncio
    async def test_acquire_returns_true_when_slot_available(self):
        from app.core.admission import AdmissionController
        ctrl = AdmissionController(max_slots=3)
        assert await ctrl.acquire() is True
        assert ctrl.inflight == 1

    @pytest.mark.asyncio
    async def test_acquire_returns_false_when_saturated(self):
        from app.core.admission import AdmissionController
        ctrl = AdmissionController(max_slots=2)
        assert await ctrl.acquire() is True
        assert await ctrl.acquire() is True
        # Third attempt: should be rejected
        assert await ctrl.acquire() is False
        assert ctrl.inflight == 2

    @pytest.mark.asyncio
    async def test_release_decrements_counter(self):
        from app.core.admission import AdmissionController
        ctrl = AdmissionController(max_slots=5)
        await ctrl.acquire()
        await ctrl.acquire()
        assert ctrl.inflight == 2
        await ctrl.release()
        assert ctrl.inflight == 1

    @pytest.mark.asyncio
    async def test_release_does_not_go_negative(self):
        """Defensive: double-release must not produce a negative counter."""
        from app.core.admission import AdmissionController
        ctrl = AdmissionController(max_slots=5)
        await ctrl.acquire()
        await ctrl.release()
        await ctrl.release()  # defensive no-op
        assert ctrl.inflight == 0

    @pytest.mark.asyncio
    async def test_atomic_under_concurrent_load(self):
        """100 concurrent acquires with max=5 → exactly 5 Trues."""
        from app.core.admission import AdmissionController
        ctrl = AdmissionController(max_slots=5)
        results = await asyncio.gather(*[ctrl.acquire() for _ in range(100)])
        assert sum(1 for r in results if r) == 5
        assert sum(1 for r in results if not r) == 95
        assert ctrl.inflight == 5
