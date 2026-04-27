"""Tests for InflightDedup."""
import asyncio
import pytest


class TestInflightDedup:

    @pytest.mark.asyncio
    async def test_first_caller_runs_factory(self):
        from app.core.inflight_dedup import InflightDedup
        dedup = InflightDedup()
        called = {"count": 0}

        async def factory():
            called["count"] += 1
            return "result"

        out = await dedup.coalesce("url1", factory)
        assert out == "result"
        assert called["count"] == 1

    @pytest.mark.asyncio
    async def test_concurrent_callers_coalesce(self):
        """5 concurrent calls for same key → factory runs once, all get same value."""
        from app.core.inflight_dedup import InflightDedup
        dedup = InflightDedup()
        calls = {"count": 0}

        async def factory():
            calls["count"] += 1
            await asyncio.sleep(0.05)  # give coalescing a chance to occur
            return "shared"

        results = await asyncio.gather(*[
            dedup.coalesce("url-same", factory) for _ in range(5)
        ])
        assert all(r == "shared" for r in results)
        assert calls["count"] == 1
        assert dedup.hits >= 4  # 4 coalesced, 1 original

    @pytest.mark.asyncio
    async def test_different_keys_independent(self):
        from app.core.inflight_dedup import InflightDedup
        dedup = InflightDedup()

        async def factory_a():
            return "A"

        async def factory_b():
            return "B"

        a, b = await asyncio.gather(
            dedup.coalesce("url-a", factory_a),
            dedup.coalesce("url-b", factory_b),
        )
        assert a == "A"
        assert b == "B"

    @pytest.mark.asyncio
    async def test_exception_propagates_to_all_waiters(self):
        from app.core.inflight_dedup import InflightDedup
        dedup = InflightDedup()

        async def failing_factory():
            await asyncio.sleep(0.05)
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await asyncio.gather(*[
                dedup.coalesce("url-fail", failing_factory) for _ in range(3)
            ])

    @pytest.mark.asyncio
    async def test_entry_cleaned_up_after_exception(self):
        """After a failure, a subsequent call for same key retries."""
        from app.core.inflight_dedup import InflightDedup
        dedup = InflightDedup()
        attempts = {"n": 0}

        async def flaky():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("first try fails")
            return "second try succeeds"

        with pytest.raises(RuntimeError):
            await dedup.coalesce("url-flaky", flaky)
        out = await dedup.coalesce("url-flaky", flaky)
        assert out == "second try succeeds"
        assert attempts["n"] == 2

    @pytest.mark.asyncio
    async def test_entry_cleaned_up_after_success(self):
        """After success, entry is removed so a later unrelated call is not served stale."""
        from app.core.inflight_dedup import InflightDedup
        dedup = InflightDedup()

        async def factory_v1():
            return "v1"

        async def factory_v2():
            return "v2"

        out1 = await dedup.coalesce("url-same", factory_v1)
        out2 = await dedup.coalesce("url-same", factory_v2)
        assert out1 == "v1"
        assert out2 == "v2"  # not "v1" — dedup only while in-flight
