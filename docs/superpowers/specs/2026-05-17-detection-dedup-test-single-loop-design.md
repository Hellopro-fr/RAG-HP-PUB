# Single-Loop Dedup Test for `api-detection-langue-fr`

> **Date:** 2026-05-17
> **Status:** Approved — ready for plan writing
> **Repo:** `RAG-HP-PUB`
> **Branch:** `features/poc`
> **Companion:** `docs/superpowers/specs/2026-05-17-detection-langue-fr-crawler-admission-carveout-design.md` — produces the dedup-leader semantics this test verifies.

---

## 1. Problem

The crawler admission carve-out (commits `265c66dc..67280d11` on `features/poc`) introduced two integration tests covering the inflight-dedup behavior:

- `test_dedup_follower_no_admission_acquire`
- `test_dedup_follower_propagates_rejection`

Both use `concurrent.futures.ThreadPoolExecutor` because each `TestClient(app)` context manager creates its own short-lived asyncio loop. `_inflight_dedup` (and the `_prod_admission` controller) hold an `asyncio.Lock()` bound to the loop where the module was imported. When 5 worker threads each open their own `TestClient`, they each spin up a fresh loop and the dedup `_inflight` dict's `asyncio.Future` instances belong to different loops. Awaiting a leader's future from a follower's loop fails with `RuntimeError: ... attached to a different loop`.

The compromise documented in the existing tests is a relaxed assertion (`acquire_calls < 5`) plus a release-count check (`release_calls == 1`). These prove that *some* dedup occurred, but not the strict leader-only semantic the spec promises: "only the dedup leader acquires a slot; followers wait on the leader's future and do NOT acquire". They also cannot verify that followers receive the *same* response body as the leader, because the response-body identity check fails when 5 independent loops each fetch independently.

Final code review of the carve-out flagged this coverage gap as Important #I-2 and recommended a single-loop test using `httpx.AsyncClient` + `asyncio.gather` to prove strict leader-only semantics end-to-end.

## 2. Goals

- Add one new test that runs all 5 concurrent `/detect` callers on a **single asyncio loop**, so dedup futures live on the same loop they are awaited on.
- Prove **strict** leader-only acquire (`acquire_calls == 1`, not `< 5`).
- Prove **response-body identity** across all 5 callers (they all read the leader's `ScrapeResult`).
- Prove `DEDUP_HITS` Prometheus counter increments by exactly 4 (the four follower hits).
- Keep both existing `ThreadPoolExecutor`-based tests as cross-thread/cross-loop sanity checks — they exercise a realistic deployment shape (uvicorn workers each on their own loop) that the new single-loop test does not.

## 3. Non-Goals

- Rewriting the existing two dedup tests to use the single-loop approach. They serve a different purpose (cross-loop sanity check) and removing them shrinks the test surface.
- Refactoring `_inflight_dedup` or `_prod_admission` to be loop-aware. Production uses a single uvicorn loop per worker, so the constraint is a test-infrastructure issue, not a production bug.
- Adding a single-loop variant of `test_dedup_follower_propagates_rejection`. Could be a future follow-up if rejection propagation behavior needs the same strictness.
- Mocking `_inflight_dedup.coalesce` directly. The reviewer's recommendation is the full HTTP path; isolation-only would be a weaker test.

## 4. Architecture

`httpx.AsyncClient` paired with `httpx.ASGITransport` lets `pytest-asyncio` drive the FastAPI app in-process without spinning up a real HTTP server. All 5 concurrent calls share the test function's loop — the same loop that `_inflight_dedup` will see when `_prod_admission.acquire`, `fetch_html`, and `coalesce`'s internal `asyncio.Future` operate.

Test flow:

1. Reset `_inflight_dedup` and snapshot `DEDUP_HITS`.
2. Monkey-patch `_prod_admission.acquire` with a counting stub (first call returns True, rest return False — but only the leader reaches the stub since followers wait on the future).
3. Monkey-patch `_prod_admission.release` with a counting stub.
4. Monkey-patch `app.api.routes.fetch_html` with a slow fetcher gated by `asyncio.Event` — produces a deterministic French ScrapeResult after the event is set.
5. Launch 5 concurrent POSTs to `/api/v1/detect` for the same URL via `asyncio.gather` against `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`.
6. Small `await asyncio.sleep(0.1)` lets all 5 callers enter `coalesce` before releasing the fetch event.
7. Set the fetch event, await gather.
8. Assert.

## 5. The New Test

File: `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py`
Function: `test_dedup_follower_strict_single_loop`

```python
@pytest.mark.asyncio
async def test_dedup_follower_strict_single_loop(monkeypatch):
    """Strict leader-only dedup verified end-to-end on a single asyncio loop.

    Unlike test_dedup_follower_no_admission_acquire (ThreadPoolExecutor),
    this test runs all 5 callers on the SAME loop, so the leader's
    inflight-dedup future is awaitable by every follower. Proves the
    strict invariant: exactly 1 acquire, exactly 1 release, 4 DEDUP_HITS,
    identical response bodies across all 5 callers.
    """
    import asyncio
    import httpx
    from httpx import ASGITransport
    from app.api.routes import _inflight_dedup
    from app.core.metrics import DEDUP_HITS
    from app.services.scraper import ScrapeResult

    _inflight_dedup.reset()
    dedup_hits_before = DEDUP_HITS._value.get()

    acquire_calls = {"n": 0}
    release_calls = {"n": 0}

    async def counting_acquire():
        acquire_calls["n"] += 1
        return acquire_calls["n"] == 1

    async def counting_release():
        release_calls["n"] += 1

    fetch_event = asyncio.Event()

    async def slow_fetch(url, proxy_url):
        await fetch_event.wait()
        return ScrapeResult(
            html="<html lang='fr'><body>Bonjour</body></html>",
            final_url=url, status_code=200, content_type="text/html",
        )

    monkeypatch.setattr(_prod_admission, "acquire", counting_acquire)
    monkeypatch.setattr(_prod_admission, "release", counting_release)
    monkeypatch.setattr("app.api.routes.fetch_html", slow_fetch)

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async def call_detect():
            return await client.post(
                "/api/v1/detect",
                json={"url": "https://strict-same-loop.fr", "mode": "simple"},
            )

        tasks = [asyncio.create_task(call_detect()) for _ in range(5)]
        # Let all 5 enter coalesce before the leader's fetch completes.
        await asyncio.sleep(0.1)
        fetch_event.set()
        responses = await asyncio.gather(*tasks)

    # Strict assertions
    assert all(r.status_code == 200 for r in responses), \
        f"Not all responses 200: {[r.status_code for r in responses]}"
    assert acquire_calls["n"] == 1, \
        f"Expected exactly 1 acquire (leader only); got {acquire_calls['n']}"
    assert release_calls["n"] == 1, \
        f"Expected exactly 1 release; got {release_calls['n']}"
    bodies = [r.text for r in responses]
    assert len(set(bodies)) == 1, \
        f"Expected identical bodies (single fetch shared via dedup); got {len(set(bodies))} distinct"
    hits_delta = DEDUP_HITS._value.get() - dedup_hits_before
    assert hits_delta == 4, \
        f"Expected 4 follower dedup hits; got {hits_delta}"
```

Notes:

- Function uses `async def` + `@pytest.mark.asyncio` (the existing module-wide convention is sync TestClient with no marker — this test deliberately diverges; the convention divergence is intentional for the single-loop case and is the test's reason for existing).
- All inline imports stay inside the function body to match the existing pattern in `test_dedup_follower_no_admission_acquire`. `_prod_admission` is already imported at module scope.
- `DEDUP_HITS._value.get()` reads the underlying prometheus_client counter value. Convention used elsewhere in `tests/test_metrics.py`.
- The 0.1 s sleep before setting the fetch event is a deliberate scheduling fence to ensure all 5 callers reach `coalesce` before the leader returns. Fragile-looking, but the alternative (a per-follower barrier) requires production code to expose state hooks.

## 6. Dependency Check

| Dependency | Status |
|---|---|
| `httpx` | Already a transitive dep (FastAPI uses it for `TestClient`). Confirmed in `apps-microservices/api-detection-langue-fr/requirements.txt` indirectly via FastAPI. |
| `pytest-asyncio` | Already in use elsewhere in the project; existing tests use `@pytest.mark.asyncio` decorator on legacy tests. |
| `ASGITransport` | Available from `httpx` 0.27+. Verify the pinned version supports it. If not, fall back to `httpx.AsyncClient(app=app)` (deprecated form) and add a TODO. |

## 7. Testing

This spec adds one test. The "test for the test" is simply:

- Run `pytest apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py -v` — expect 13/13 PASS (existing 12 + new 1).
- Manually verify the assertions fail in expected ways under broken dedup:
  - If `coalesce` is bypassed: `acquire_calls["n"] == 5` → assertion 1 fails with informative message.
  - If `coalesce` works but futures cross-loop: would fail with `RuntimeError: ... attached to a different loop` BEFORE the assertions run.
  - If the leader's response body isn't shared: `len(set(bodies)) > 1` → assertion 4 fails.
  - If `release` is not paired with `acquire`: `release_calls["n"] != 1` → assertion 3 fails.

No automated regression check beyond the existing pytest run. The new test IS the regression check.

## 8. Rollout

Trivial — test-only change. No production code modified, no behavior change, no risk surface beyond the test suite itself.

1. Implement the new test on `features/poc` branch.
2. Run the full carve-out test suite. Expect 13/13.
3. Commit.
4. Operator side: nothing required.

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `httpx.ASGITransport` not available in pinned `httpx` version | Low | Fallback to `httpx.AsyncClient(app=app)` deprecated form. If neither works, escalate. |
| The 0.1 s scheduling sleep is flaky on slow CI | Low | If observed flake, bump to 0.5 s. The test is local-only today (no CI for this service per `~/.claude/primer.md`). |
| Cross-loop error if `_inflight_dedup` module-level state leaks from a prior test | Low | `_inflight_dedup.reset()` at test start clears `_inflight` dict. Each test's `asyncio.Lock` is re-bound when the loop is created. |
| `DEDUP_HITS` counter contamination from a prior test | Low | Snapshot `dedup_hits_before` and compare delta. |
| `_prod_admission` state leak | Low | Existing `reset_admission_counter` autouse fixture resets `_counter`. Monkeypatch on `acquire`/`release` is auto-reverted by `monkeypatch` fixture. |

## 10. Follow-Ups (Out of Scope)

- Single-loop variant of `test_dedup_follower_propagates_rejection` (apply the same pattern to leader-rejection propagation).
- Refactor existing two `ThreadPoolExecutor` dedup tests to drop their relaxed assertions if the new single-loop test proves sufficient — but only after multiple production runs confirm no value in the cross-thread variant.
- Per-loop `_inflight_dedup` factory if the team ever runs multi-loop workers (currently single-loop uvicorn — not warranted).
