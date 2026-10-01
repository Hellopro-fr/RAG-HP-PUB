# Single-Loop Dedup Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one new pytest test `test_dedup_follower_strict_single_loop` to `tests/test_admission_carveout.py` that runs 5 concurrent `/detect` callers on a SINGLE asyncio loop via `httpx.AsyncClient` + `ASGITransport` + `asyncio.gather`. Proves strict leader-only dedup semantics: exactly 1 acquire, 1 release, 4 DEDUP_HITS, identical response bodies across all 5 callers.

**Architecture:** Single-file test addition. Diverges from the file's existing sync-TestClient pattern by using `async def` + `@pytest.mark.asyncio` + `httpx.AsyncClient(transport=ASGITransport(app=app))`. Closes a coverage gap that the existing `ThreadPoolExecutor`-based tests cannot fill (cross-thread futures are bound to different loops). Existing 2 ThreadPoolExecutor dedup tests stay as cross-loop sanity checks.

**Tech Stack:** Python 3.10, pytest, pytest-asyncio, httpx (with `ASGITransport`), FastAPI, prometheus_client.

**Spec:** `docs/superpowers/specs/2026-05-17-detection-dedup-test-single-loop-design.md` (commit `317895eb`).

**Branch:** `features/poc`.

---

## File Structure

| File | Disposition | Responsibility |
|---|---|---|
| `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py` | MOD (append) | One new test function `test_dedup_follower_strict_single_loop` appended after the existing 12 tests. ~50 lines added. |

No other files touched. No production code changes. No new dependencies (httpx is already a transitive dep via FastAPI; pytest-asyncio is already used in the project).

---

## Task 1: Add single-loop strict-dedup test

**Goal:** Append `test_dedup_follower_strict_single_loop` to `tests/test_admission_carveout.py`. Test runs 5 concurrent `/detect` callers on one asyncio loop, asserts strict invariants: 1 acquire, 1 release, 4 DEDUP_HITS, identical response bodies.

**Files:**
- Modify (append-only): `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py`

**Acceptance Criteria:**
- [ ] New function `test_dedup_follower_strict_single_loop(monkeypatch)` exists at the end of the file (after `test_admission_disabled_kill_switch_documents_contract`).
- [ ] Decorated with `@pytest.mark.asyncio`.
- [ ] Uses `async def` (the ONLY async test in this file — convention divergence is intentional for the single-loop case).
- [ ] Inline imports inside the test body for `asyncio`, `httpx`, `ASGITransport`, `_inflight_dedup`, `DEDUP_HITS`, `ScrapeResult`. `_prod_admission` is already imported at module top.
- [ ] Calls `_inflight_dedup.reset()` at test start (uses the public method added in Task 5 fix `2f75dae8`).
- [ ] Snapshots `DEDUP_HITS._value.get()` before the call burst.
- [ ] Monkey-patches `_prod_admission.acquire` with `counting_acquire` (returns True on first call only).
- [ ] Monkey-patches `_prod_admission.release` with `counting_release`.
- [ ] Monkey-patches `app.api.routes.fetch_html` with `slow_fetch` (gated by `asyncio.Event`, returns deterministic French ScrapeResult).
- [ ] Uses `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")` inside `async with`.
- [ ] Launches 5 concurrent `client.post("/api/v1/detect", ...)` via `asyncio.create_task` + `asyncio.gather`.
- [ ] `await asyncio.sleep(0.1)` between task creation and `fetch_event.set()` to let all 5 enter `coalesce`.
- [ ] All 5 assertions pass:
  - All responses status_code == 200
  - `acquire_calls["n"] == 1` (strict, NOT `< 5`)
  - `release_calls["n"] == 1`
  - `len(set(r.text for r in responses)) == 1` (identical bodies)
  - `DEDUP_HITS._value.get() - dedup_hits_before == 4` (4 follower hits)
- [ ] Existing 12 tests in the file still pass (no regression).

**Verify:** `pytest apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py -v` → 13/13 PASS.

**Steps:**

- [ ] **Step 1: Read the current test file**

Read `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py` in full. Confirm:
- `_prod_admission` imported at module top (around line 16).
- `app` imported at module top.
- 12 existing tests, last one is `test_admission_disabled_kill_switch_documents_contract`.
- File uses sync `def test_xxx(...)` + `TestClient(app)` pattern throughout.
- `_inflight_dedup.reset()` is available (added in Task 5 fix `2f75dae8`).
- Existing tests `test_dedup_follower_no_admission_acquire` and `test_dedup_follower_propagates_rejection` use `ThreadPoolExecutor`.

- [ ] **Step 2: Verify `httpx.ASGITransport` is available**

Run from the repo root:
```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
python -c "from httpx import ASGITransport; print('ok', ASGITransport.__module__)"
```

Expected: `ok httpx._transports.asgi` (or similar — the import succeeds).

If `ImportError`: check `apps-microservices/api-detection-langue-fr/requirements.txt` for `httpx` version. Versions < 0.27 don't expose `ASGITransport` as a top-level import. Fallback: use `httpx.AsyncClient(app=app, base_url="http://test")` (deprecated since 0.27 but still works). Document the fallback in the test docstring.

Report which path you took (ASGITransport or deprecated `app=` kwarg).

- [ ] **Step 3: Verify `pytest-asyncio` is configured**

Run:
```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
python -m pytest --version
python -c "import pytest_asyncio; print('ok', pytest_asyncio.__version__)"
```

Confirm `pytest-asyncio` is installed. If not, run `pip install pytest-asyncio` (or check `requirements.txt`).

Check `apps-microservices/api-detection-langue-fr/pytest.ini` or `pyproject.toml` for `asyncio_mode` setting. If set to `auto`, the `@pytest.mark.asyncio` decorator is redundant but harmless. If set to `strict` (or unset), the decorator IS required.

Report the mode.

- [ ] **Step 4: Append the new test**

Append the following block at the END of `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py` (after the last existing test, `test_admission_disabled_kill_switch_documents_contract`):

```python


@pytest.mark.asyncio
async def test_dedup_follower_strict_single_loop(monkeypatch):
    """Strict leader-only dedup verified end-to-end on a single asyncio loop.

    Unlike test_dedup_follower_no_admission_acquire (ThreadPoolExecutor),
    this test runs all 5 callers on the SAME loop, so the leader's
    inflight-dedup future is awaitable by every follower. Proves the
    strict invariant: exactly 1 acquire, exactly 1 release, 4 DEDUP_HITS,
    identical response bodies across all 5 callers.

    Companion to the existing 2 ThreadPoolExecutor dedup tests, which
    stay in place as cross-loop sanity checks (a realistic deployment
    shape uvicorn workers each on their own loop).

    Spec: docs/superpowers/specs/2026-05-17-detection-dedup-test-single-loop-design.md
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
    assert all(r.status_code == 200 for r in responses), (
        f"Not all responses 200: {[r.status_code for r in responses]}"
    )
    assert acquire_calls["n"] == 1, (
        f"Expected exactly 1 acquire (leader only); got {acquire_calls['n']}"
    )
    assert release_calls["n"] == 1, (
        f"Expected exactly 1 release; got {release_calls['n']}"
    )
    bodies = [r.text for r in responses]
    assert len(set(bodies)) == 1, (
        f"Expected identical bodies (single fetch shared via dedup); "
        f"got {len(set(bodies))} distinct"
    )
    hits_delta = DEDUP_HITS._value.get() - dedup_hits_before
    assert hits_delta == 4, (
        f"Expected 4 follower dedup hits; got {hits_delta}"
    )
```

If Step 2 forced the deprecated fallback (`httpx.AsyncClient(app=app, ...)`), replace the two lines:

```python
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
```

with:

```python
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
```

And drop the `from httpx import ASGITransport` import.

- [ ] **Step 5: Run the new test**

Run:
```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
python -m pytest apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py::test_dedup_follower_strict_single_loop -v
```

Expected: 1 passed.

**Possible failure modes + diagnostics:**

| Failure | Likely cause | Fix |
|---|---|---|
| `RuntimeError: ... attached to a different loop` | `pytest-asyncio` configured with per-function loop instead of session loop, and `_prod_admission._lock` was created on the module-import loop | Add `@pytest.mark.asyncio(scope="session")` or check `asyncio_mode`. If neither works, the test infrastructure can't support this and we file a follow-up. |
| `acquire_calls["n"] > 1` | Dedup isn't coalescing — followers acquire on their own | Check `_inflight_dedup.reset()` ran before the test (state leak from prior test). |
| `len(set(bodies)) > 1` | Followers fetched independently — dedup broken | Same as above. |
| `hits_delta != 4` | DEDUP_HITS counter contaminated or not incremented | Inspect `_inflight_dedup.coalesce` — `self._hits += 1` should fire 4 times. |
| `release_calls["n"] != 1` | Leader didn't release, or followers also called release | Check `_fetch_with_admission` finally block. |
| ImportError on `ASGITransport` | `httpx` < 0.27 | Use deprecated fallback per Step 2/4. |

- [ ] **Step 6: Run the full carveout suite for regression check**

Run:
```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
python -m pytest apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py -v
```

Expected: 13 passed (12 existing + 1 new).

Run full directory minus pre-existing breakage:
```bash
python -m pytest apps-microservices/api-detection-langue-fr/tests/ -v --ignore=apps-microservices/api-detection-langue-fr/tests/test_api.py --ignore=apps-microservices/api-detection-langue-fr/tests/test_domain_fr.py
```

Expected: all green (acknowledging known fastText-flaky test per `~/.claude/primer.md`).

- [ ] **Step 7: Commit (bilingual EN+FR per session preference)**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py
```

Write `.git/COMMIT_EDITMSG` via Write tool (UTF-8, NOT shell heredoc — Windows cp1252 strips accents on heredoc):

```
test(api-detection-langue-fr): strict single-loop dedup follower test

EN: Add test_dedup_follower_strict_single_loop using httpx.AsyncClient
+ ASGITransport + asyncio.gather. Runs 5 concurrent /detect callers
on a single asyncio loop, so dedup futures are awaitable by every
follower. Proves strict leader-only invariants the existing
ThreadPoolExecutor tests cannot reach (cross-loop futures error out):
exactly 1 acquire, 1 release, 4 DEDUP_HITS, identical response bodies
across all 5 callers. Existing 2 ThreadPoolExecutor dedup tests stay
as cross-loop sanity checks. Closes Important #I-2 from carve-out
final code review.

FR: Ajoute test_dedup_follower_strict_single_loop utilisant
httpx.AsyncClient + ASGITransport + asyncio.gather. Lance 5 appels
concurrents /detect sur la MÊME boucle asyncio, ce qui rend les
futures dedup awaitables par chaque follower. Prouve les invariants
stricts leader-only que les tests ThreadPoolExecutor existants ne
peuvent pas couvrir (les futures cross-loop échouent) : exactement
1 acquire, 1 release, 4 DEDUP_HITS, corps de réponse identiques sur
les 5 appels. Les 2 tests ThreadPoolExecutor existants restent en
tant que sanity check cross-loop. Corrige Important #I-2 de la revue
de code finale de la carve-out.

Spec : docs/superpowers/specs/2026-05-17-detection-dedup-test-single-loop-design.md
```

Commit: `cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB && git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG`.

**Note on commit message file:** if Hellopro session left stale content in `.git/COMMIT_EDITMSG`, Write may fail with "file modified since read". In that case: read the existing content first, then write the new content, then commit. This is a recurring issue per Tasks 3/4/5 of the BO plan — defensive write-then-read-then-write is the workaround.

Verify accents: `git log -1 --format='%b' | grep -E "à|é|É|È"` should show matches.

---

## Self-Review Notes

| Spec section | Covered by |
|---|---|
| §1 Problem | Plan addresses the gap |
| §2 Goals (single-loop, strict acquire, body identity, DEDUP_HITS=4, keep existing tests) | Task 1 AC + Step 4 code |
| §3 Non-Goals | Plan touches NO production code, NO existing tests |
| §4 Architecture | Step 4 code follows the exact flow described in spec §4 |
| §5 The new test (full code block) | Step 4 verbatim |
| §6 Dependency Check | Step 2 (httpx) + Step 3 (pytest-asyncio) |
| §7 Testing | Steps 5–6 |
| §8 Rollout | One commit, no operator action |
| §9 Risks | Step 5 failure-mode table |
| §10 Follow-ups | Out of scope, listed in spec |
