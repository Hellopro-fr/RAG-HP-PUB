"""Pass 2 (batch sequential retry) bounded on the remaining async-job budget.

Production incident 2026-08-13: Pass 1 took 328s, Pass 2 then retried 4 URLs
SEQUENTIALLY at up to _ITEM_WALL_CLOCK_S (300s) + 2s gap each -> 328 + 4*302
~= 1536s > JOB_MAX_S (1500s). The worker watchdog (_abandon_job,
app/core/async_jobs.py) then abandoned the whole job, overwriting a record
whose `results` was still None (the heartbeat only ever writes
done/status/last_activity) -- so ALL 10 items in the chunk, including the 2
that had already succeeded in Pass 1, were read back by the BO as failed.

Fix: `_run_batch_core` takes an optional `deadline_monotonic` (an ABSOLUTE
time.monotonic() deadline). Pass 2 checks it BEFORE starting each retry and
stops the loop -- it never cancels one already in flight -- once fewer than
`_ITEM_WALL_CLOCK_S + _PASS2_BUDGET_MARGIN_S` seconds remain. Items that
never get a retry keep their Pass 1 verdict untouched (still retryable on the
BO's next run).

`deadline_monotonic=None` (the sync /detect-batch route's call shape) must
reproduce EXACTLY today's behaviour -- the non-regression guarantee, since
that path has no JOB_MAX_S to bound itself against.

Timing note: these tests use small REAL values for _ITEM_WALL_CLOCK_S /
_PASS2_BUDGET_MARGIN_S and real (small) deadlines rather than mocking
time.monotonic() -- the module's Pass 2 loop and the real `asyncio.wait_for`
around each retry share the same process-wide clock, and desyncing them
(mocking time.monotonic while asyncio's own event loop still calls the real
one internally for its timers) is a known footgun. Same approach as the
sibling tests/test_variant_rescue.py (real small sleeps, generous margins,
never real full-scale budgets).
"""
import logging

import pytest

from app.api import routes
from app.core import metrics
from app.models.schemas import BatchItem, BatchOpts, DetectionMode, DetectionResponse


@pytest.mark.asyncio
async def test_pass2_without_deadline_retries_unchanged(monkeypatch):
    """Non-regression guarantee: deadline_monotonic=None (today's call shape)
    must still retry every Pass-2-eligible item, exactly like before this
    change. Real ~2s cost (one Pass-2 retry gap) -- same order of magnitude as
    the sibling tests in tests/test_batch_core_refactor.py."""
    calls = {"n": 0}

    async def fake_detect(url, **kwargs):
        calls["n"] += 1
        if not kwargs.get("force_refresh"):
            return DetectionResponse(ok=False, url=url, method="fetch_failed")
        return DetectionResponse(ok=True, url=url, method="url_tld")

    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url="https://x.fr")]
    results, _ = await routes._run_batch_core(
        items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=1)
    )
    assert calls["n"] == 2, "Pass 1 (fetch_failed) + Pass 2 (recovered) — unchanged"
    assert results[0].ok is True


@pytest.mark.asyncio
async def test_pass2_skips_retries_beyond_job_budget(monkeypatch, caplog):
    """FAILS on today's code: _run_batch_core has no notion of a job-level
    deadline at all, so Pass 2 always retries every eligible item regardless
    of how much of JOB_MAX_S is left (see module docstring). With a deadline
    that only leaves room for 1 of 3 retries, exactly 1 must be attempted;
    the other 2 keep their Pass 1 verdict untouched, and the skip is logged
    and counted."""
    monkeypatch.setattr(routes, "_ITEM_WALL_CLOCK_S", 1)
    monkeypatch.setattr(routes, "_PASS2_BUDGET_MARGIN_S", 0.5)  # threshold = 1.5s

    retried = []

    async def fake_detect(url, **kwargs):
        if not kwargs.get("force_refresh"):
            return DetectionResponse(ok=False, url=url, method="fetch_failed")
        retried.append(url)
        return DetectionResponse(ok=True, url=url, method="url_tld")

    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url=f"https://y{i}.fr") for i in range(3)]
    # 3.0s of remaining budget: the 1st retry's pre-check passes comfortably
    # (~2.2-2.5s remaining after Pass 1's own stagger overhead, well above the
    # 1.5s threshold); the real ~2s Pass-2 gap sleep before the 2nd check then
    # drops remaining to ~0.1-0.5s (comfortably below 1.5s) — stopping the
    # loop before a 2nd retry starts. Generous margins on both sides absorb
    # ordinary scheduling jitter.
    deadline = routes.time.monotonic() + 3.0
    before = metrics.PASS2_RETRY_SKIPPED_BUDGET._value.get()
    with caplog.at_level(logging.WARNING, logger="app.api.routes"):
        results, _ = await routes._run_batch_core(
            items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=1),
            deadline_monotonic=deadline,
        )
    after = metrics.PASS2_RETRY_SKIPPED_BUDGET._value.get()

    assert len(retried) == 1, f"expected exactly 1 retry attempted, got {retried}"
    assert sum(r.ok for r in results) == 1
    skipped = [r for r in results if not r.ok]
    assert len(skipped) == 2
    assert all(r.method == "fetch_failed" for r in skipped), (
        "items skipped for lack of budget must keep their Pass 1 verdict verbatim"
    )
    assert after - before == 2
    assert any("sautée" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_pass2_never_starts_retry_under_item_wall_clock_floor(monkeypatch):
    """A retry must never be handed less than a FULL _ITEM_WALL_CLOCK_S +
    margin of remaining budget: starting one with less would get it cancelled
    mid-navigation once the job watchdog (JOB_MAX_S) fires -- the documented
    cause of orphaned Playwright protocol callbacks in this service (same
    reasoning as the _MIN_PROBE_S floor in the variant rescue). Deadline is
    already below the floor before Pass 2 even starts -> zero real sleep."""
    monkeypatch.setattr(routes, "_ITEM_WALL_CLOCK_S", 1)
    monkeypatch.setattr(routes, "_PASS2_BUDGET_MARGIN_S", 0.5)  # threshold = 1.5s

    attempted = []

    async def fake_detect(url, **kwargs):
        if not kwargs.get("force_refresh"):
            return DetectionResponse(ok=False, url=url, method="fetch_failed")
        attempted.append(url)
        return DetectionResponse(ok=True, url=url, method="url_tld")

    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url="https://z.fr")]
    deadline = routes.time.monotonic() + 1.0  # < 1.5s threshold from the start
    results, _ = await routes._run_batch_core(
        items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=1),
        deadline_monotonic=deadline,
    )
    assert attempted == [], "no retry may start with less than a full item's headroom"
    assert results[0].method == "fetch_failed"


@pytest.mark.asyncio
async def test_pass2_skip_counter_reflects_skipped_count(monkeypatch):
    """Prometheus counter must reflect exactly the number of budget-skipped
    retries -- without it an operator can't tell "nothing left to retry"
    apart from "ran out of time to retry". Deadline already exhausted -> zero
    real sleep, all skipped in a single pre-check."""
    monkeypatch.setattr(routes, "_ITEM_WALL_CLOCK_S", 1)
    monkeypatch.setattr(routes, "_PASS2_BUDGET_MARGIN_S", 0.5)

    async def fake_detect(url, **kwargs):
        return DetectionResponse(ok=False, url=url, method="fetch_failed")

    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url=f"https://w{i}.fr") for i in range(3)]
    before = metrics.PASS2_RETRY_SKIPPED_BUDGET._value.get()
    deadline = routes.time.monotonic() - 1.0  # already in the past
    await routes._run_batch_core(
        items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=3),
        deadline_monotonic=deadline,
    )
    after = metrics.PASS2_RETRY_SKIPPED_BUDGET._value.get()
    assert after - before == 3
