"""Pass 2 (batch sequential retry) bounded on the remaining async-job budget.

Production incident 2026-08-13: Pass 1 took 328s, Pass 2 then retried 4 URLs
SEQUENTIALLY at up to _ITEM_WALL_CLOCK_S (300s) + 2s gap each -> 328 + 4*302
~= 1536s > JOB_MAX_S (1500s). The worker watchdog (_abandon_job,
app/core/async_jobs.py) then abandoned the whole job, overwriting a record
whose `results` was still None (the heartbeat only ever writes
done/status/last_activity) -- so ALL 10 items in the chunk, including the 2
that had already succeeded in Pass 1, were read back by the BO as failed.

Fix: `_run_batch_core` takes an optional `deadline_monotonic` (an ABSOLUTE
time.monotonic() deadline). BOTH Pass 2 retry loops -- the sequential one
(complete/simple modes) and the grouped one (first_match, reachable from the
async worker too: AsyncBatchSubmitRequest.mode is forwarded verbatim) --
check it BEFORE starting each retry and stop -- never cancel one already in
flight -- once fewer than `_ITEM_WALL_CLOCK_S + _PASS2_BUDGET_MARGIN_S`
seconds remain. Items that never get a retry keep their Pass 1 verdict
untouched (still retryable on the BO's next run).

`deadline_monotonic=None` (the sync /detect-batch route's call shape) must
reproduce EXACTLY today's behaviour -- the non-regression guarantee, since
that path has no JOB_MAX_S to bound itself against.

Timing: NOT mocking time.monotonic() -- a prior version of this file did,
and it hung: asyncio's own event loop calls the same process-wide
`time.monotonic` for its internal timers (`loop.call_later` /
`asyncio.wait_for`), so freezing/jumping it out from under a live loop
desyncs its scheduling logic. Real (small) wall-clock instead: the
_PASS2_RETRY_GAP_S inter-retry throttle (2s in prod) is monkeypatched down
to 0.2s via the fixture below, which IS what drives the remaining-budget
math between checks in the two "k of n" tests -- `_ITEM_WALL_CLOCK_S` /
`_PASS2_BUDGET_MARGIN_S` are shrunk to small values too so the deadline
windows stay well clear of real `asyncio.wait_for` timeouts. Margins were
picked comfortably larger (~0.1s) than ordinary asyncio scheduling jitter.
"""
import logging

import pytest

from app.api import routes
from app.core import metrics
from app.models.schemas import BatchItem, BatchOpts, DetectionMode, DetectionResponse


@pytest.fixture(autouse=True)
def _small_retry_gap(monkeypatch):
    """_PASS2_RETRY_GAP_S defaults to 2s (prod inter-retry throttle) --
    shrink it here so no test in this file pays real multi-second cost for
    it (finding 6, code review). 0.2s is also what the two "k of n" tests
    below rely on as their exact per-retry budget consumption."""
    monkeypatch.setattr(routes, "_PASS2_RETRY_GAP_S", 0.2)


@pytest.mark.asyncio
async def test_pass2_without_deadline_retries_unchanged(monkeypatch):
    """Non-regression guarantee: deadline_monotonic=None (today's call shape)
    must still retry every Pass-2-eligible item, exactly like before this
    change."""
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
    that only leaves room for 2 of 3 retries, exactly 2 must be attempted;
    the 3rd keeps its Pass 1 verdict untouched, and the skip is logged and
    counted.

    threshold = _ITEM_WALL_CLOCK_S(1) + _PASS2_BUDGET_MARGIN_S(0.4) = 1.4s.
    Pass 1's own per-item stagger (process_single, unrelated to this fix)
    costs ~0.5s here (max_concurrency=1 caps it there regardless of item
    count) before Pass 2 even starts; each attempted retry then costs the
    real _PASS2_RETRY_GAP_S (0.2s, see fixture) before the check for the next
    one. deadline=2.2: check1 sees ~1.7 (>=1.4, proceeds), check2 sees ~1.5
    (>=1.4, proceeds), check3 sees ~1.3 (<1.4, stops) -- ~0.1-0.3s margin
    either side of the boundary, well above ordinary asyncio scheduling
    jitter."""
    monkeypatch.setattr(routes, "_ITEM_WALL_CLOCK_S", 1)
    monkeypatch.setattr(routes, "_PASS2_BUDGET_MARGIN_S", 0.4)

    retried = []

    async def fake_detect(url, **kwargs):
        if not kwargs.get("force_refresh"):
            return DetectionResponse(ok=False, url=url, method="fetch_failed")
        retried.append(url)
        return DetectionResponse(ok=True, url=url, method="url_tld")

    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url=f"https://y{i}.fr") for i in range(3)]
    deadline = routes.time.monotonic() + 2.2
    before = metrics.PASS2_RETRY_SKIPPED_BUDGET._value.get()
    with caplog.at_level(logging.WARNING, logger="app.api.routes"):
        results, _ = await routes._run_batch_core(
            items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=1),
            deadline_monotonic=deadline,
        )
    after = metrics.PASS2_RETRY_SKIPPED_BUDGET._value.get()

    assert len(retried) == 2, f"expected exactly 2 retries attempted, got {retried}"
    assert sum(r.ok for r in results) == 2
    skipped = [r for r in results if not r.ok]
    assert len(skipped) == 1
    assert all(r.method == "fetch_failed" for r in skipped), (
        "items skipped for lack of budget must keep their Pass 1 verdict verbatim"
    )
    assert after - before == 1
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
    monkeypatch.setattr(routes, "_PASS2_BUDGET_MARGIN_S", 0.4)  # threshold = 1.4s

    attempted = []

    async def fake_detect(url, **kwargs):
        if not kwargs.get("force_refresh"):
            return DetectionResponse(ok=False, url=url, method="fetch_failed")
        attempted.append(url)
        return DetectionResponse(ok=True, url=url, method="url_tld")

    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url="https://z.fr")]
    deadline = routes.time.monotonic() + 1.0  # < 1.4s threshold from the start
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
    monkeypatch.setattr(routes, "_PASS2_BUDGET_MARGIN_S", 0.4)

    async def fake_detect(url, **kwargs):
        return DetectionResponse(ok=False, url=url, method="fetch_failed")

    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url=f"https://w{i}.fr") for i in range(3)]
    before = metrics.PASS2_RETRY_SKIPPED_BUDGET._value.get()
    deadline = routes.time.monotonic() - 1.0  # already in the past
    await routes._run_batch_core(
        # max_concurrency=1 keeps Pass 1's own per-item stagger (unrelated to
        # this test) capped at ~0.5s instead of ~1s -- irrelevant to the
        # assertion (deadline is already in the past either way) but faster.
        items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=1),
        deadline_monotonic=deadline,
    )
    after = metrics.PASS2_RETRY_SKIPPED_BUDGET._value.get()
    assert after - before == 3


@pytest.mark.asyncio
async def test_pass2_first_match_skips_retries_beyond_job_budget(monkeypatch, caplog):
    """Finding 2 (code review): the first_match Pass 2 loop (grouped retry,
    routes.py ~886-935) runs the identical sleep(gap)+wait_for(
    _ITEM_WALL_CLOCK_S) sequence with no total cap of its own -- and IS
    reachable from the async worker (AsyncBatchSubmitRequest.mode accepts any
    DetectionMode and async_jobs.py forwards it verbatim). FAILS if that loop
    doesn't apply the same deadline_monotonic pre-check as the sequential
    loop above.

    3 singleton groups (no explicit `group` -> one item per implicit group),
    all fetch_failed in Pass 1. Same math as the sequential test above:
    threshold=1.4s, deadline=1.7s, ~0.2s real cost per attempted retry ->
    exactly 2 of 3 groups get a retry, the 3rd keeps its Pass 1 verdict."""
    monkeypatch.setattr(routes, "_ITEM_WALL_CLOCK_S", 1)
    monkeypatch.setattr(routes, "_PASS2_BUDGET_MARGIN_S", 0.4)

    retried = []

    async def fake_detect(url, **kwargs):
        if not kwargs.get("force_refresh"):
            return DetectionResponse(ok=False, url=url, method="fetch_failed")
        retried.append(url)
        return DetectionResponse(ok=True, url=url, method="url_tld")

    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url=f"https://fm{i}.fr") for i in range(3)]
    deadline = routes.time.monotonic() + 1.7
    before = metrics.PASS2_RETRY_SKIPPED_BUDGET._value.get()
    with caplog.at_level(logging.WARNING, logger="app.api.routes"):
        results, _ = await routes._run_batch_core(
            items, DetectionMode.FIRST_MATCH, BatchOpts(max_concurrency=3),
            deadline_monotonic=deadline,
        )
    after = metrics.PASS2_RETRY_SKIPPED_BUDGET._value.get()

    assert len(retried) == 2, f"expected exactly 2 retries attempted, got {retried}"
    assert sum(r.ok for r in results) == 2
    skipped = [r for r in results if not r.ok]
    assert len(skipped) == 1
    assert skipped[0].method == "fetch_failed", (
        "the group skipped for lack of budget must keep its Pass 1 verdict verbatim"
    )
    assert after - before == 1
    assert any("sautée" in r.message for r in caplog.records)
