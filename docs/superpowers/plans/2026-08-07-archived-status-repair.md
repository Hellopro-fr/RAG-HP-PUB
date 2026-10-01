# Archived-Status Repair — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair `crawl_job:` blobs that say `finished` while their tar sits in GCS, so `GET /results` stops answering 404 on them — and keep repairing the residual flow automatically.

**Architecture:** A pure predicate module decides; a leader-only pass inside `_reconcile_locked` acts, gated on a default-off flag and on the host-generated GCS allowlist (fail-closed); a read-only admin endpoint exposes the same decision as a dry-run. Writes go through the existing `_mark_as_archived` — no new write path.

**Tech Stack:** Python 3.12, FastAPI, redis-py asyncio, pytest + pytest-asyncio. Repo: RAG-HP-PUB, service `apps-microservices/crawler-service`, branch `features/poc`.

**User decisions (already made):**
- Repair scope: "Ponctuel puis permanent" — one-shot drain AND a standing pass, not one or the other.
- Stashed stubs: "Hors périmètre, mais comptés et listés" — the dry-run counts them, nothing repairs them.
- Predicate scope: "Tout blob au statut menteur" — not only recovery stubs; the legacy `stuck at finished` population is in.
- Mechanism: approach 2 — reconciliation pass + read-only dry-run endpoint, over a host script.
- Spec approved as revised (`52854669`), including the six-condition predicate and the reordered deployment sequence.

**Spec:** `docs/superpowers/specs/2026-08-07-archived-status-repair-design.md`

**Out of scope for this plan:** deployment. §9 of the spec is the operator runbook; this plan ends at a merged, tested branch.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps-microservices/crawler-service/app/core/archived_status_repair.py` | **new** — pure predicate + rejection-bucket constants. No I/O, no framework imports. |
| `apps-microservices/crawler-service/tests/test_archived_status_repair.py` | **new** — table-driven predicate tests. |
| `apps-microservices/crawler-service/app/core/config.py` | **modify** — two settings, next to the `ARCHIVED_RECLEAN_*` block. |
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | **modify** — allowlist hoist, `finished_candidates` accumulator, `_mtime_or_none`, `_archive_lock_held`, `_repair_archived_status`, wiring. |
| `apps-microservices/crawler-service/tests/test_reconcile_status_repair.py` | **new** — pass behaviour + wiring regression locks. |
| `apps-microservices/crawler-service/app/router/admin.py` | **modify** — `GET /admin/archived-status-repair`. |
| `apps-microservices/crawler-service/tests/test_admin_status_repair_endpoint.py` | **new** — endpoint contract + read-only assertion. |
| `apps-microservices/crawler-service/CLAUDE.md` | **modify** — document the pass, the flags, the kill switch. |

All test commands run from `apps-microservices/crawler-service/`.

**Repo gotcha:** a `tdd-gate` hook fires if a source file is written before its test. Write the test file first in every task.

**Baseline:** the suite is at 360 passed / 1 failed. The failure is `tests/test_archive_mock_e2e.py::TestArchiveMockE2E::test_daemon_logic` — pre-existing, a bash subprocess that cannot run on Windows. Do not chase it.

---

### Task 1: Pure predicate module

**Goal:** A dependency-free function that returns either "repair this" or the name of the first condition the crawl fails.

**Files:**
- Create: `apps-microservices/crawler-service/app/core/archived_status_repair.py`
- Test: `apps-microservices/crawler-service/tests/test_archived_status_repair.py`

**Acceptance Criteria:**
- [ ] `classify()` returns `None` for a crawl meeting conditions 1–5, else the bucket name of the **first** failing condition
- [ ] Evaluation order is exactly: status → stashed → allowlist → snapshot → log/mtime
- [ ] `log_mtime is None` rejects (no `is None` escape hatch — this was the fail-open bug)
- [ ] `log_mtime >= snapshot_mtime` rejects
- [ ] Module imports nothing beyond `typing`
- [ ] Condition 6 (`archive_lock`) is deliberately NOT in this module, and the docstring says why

**Verify:** `python -m pytest tests/test_archived_status_repair.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `tests/test_archived_status_repair.py`:

```python
# tests/test_archived_status_repair.py
"""Predicate for the archived-status repair pass.

The evaluation ORDER is part of the contract: the dry-run endpoint reports the
first failing condition, so two implementations that disagree on order produce
different operator-facing counts for the same Redis state.

The log/snapshot comparison replaces an earlier marker-based check that was
fail-OPEN: _cleanup_stale_state_for_relaunch deletes _completion_marker.json on
every relaunch (crawler_manager.py:3494) and _monitor_process writes
status='finished' at :1284 but the marker only at :1298, swallowing failures at
:1301. A re-crawled id caught in that window would have been flipped to
'archived', making /results serve the previous generation's tar.
"""
import pytest

from app.core import archived_status_repair as asr

VERIFIED = {"6712", "6713"}


def _call(**over):
    kw = dict(
        crawl_id="6712",
        status="finished",
        stashed_at=None,
        verified_ids=VERIFIED,
        snapshot_mtime=200.0,
        log_mtime=100.0,
    )
    kw.update(over)
    return asr.classify(**kw)


def test_nominal_archived_crawl_is_a_candidate():
    assert _call() is None
    assert asr.is_status_repair_candidate(
        crawl_id="6712", status="finished", stashed_at=None,
        verified_ids=VERIFIED, snapshot_mtime=200.0, log_mtime=100.0) is True


@pytest.mark.parametrize("status", ["archived", "failed", "stopped", "running", None])
def test_condition_1_rejects_non_finished(status):
    assert _call(status=status) == asr.NOT_FINISHED


def test_condition_2_rejects_stashed():
    assert _call(stashed_at="2026-08-01T10:00:00") == asr.STASHED


def test_condition_3_rejects_id_absent_from_allowlist():
    assert _call(crawl_id="9999") == asr.NOT_IN_GCS_LIST


def test_condition_3_compares_as_string():
    # Redis blobs carry crawl_id as a string; the allowlist is parsed as strings.
    assert asr.classify(crawl_id=6712, status="finished", stashed_at=None,
                        verified_ids=VERIFIED, snapshot_mtime=200.0,
                        log_mtime=100.0) is None


def test_condition_4_rejects_missing_snapshot():
    assert _call(snapshot_mtime=None) == asr.NO_SNAPSHOT


def test_condition_5_rejects_missing_log():
    # THE regression this predicate exists for: absent evidence must never pass.
    assert _call(log_mtime=None) == asr.RUN_AFTER_ARCHIVE


def test_condition_5_rejects_log_newer_than_snapshot():
    assert _call(log_mtime=300.0, snapshot_mtime=200.0) == asr.RUN_AFTER_ARCHIVE


def test_condition_5_rejects_equal_mtimes():
    # Strictly-older only: equality is unresolvable, so it must not authorize a write.
    assert _call(log_mtime=200.0, snapshot_mtime=200.0) == asr.RUN_AFTER_ARCHIVE


def test_evaluation_order_is_first_failure_wins():
    # Stashed AND absent from the allowlist AND no snapshot: bucket must be the
    # earliest failing condition, or the dry-run's counts are not reproducible.
    assert _call(stashed_at="x", crawl_id="9999", snapshot_mtime=None) == asr.STASHED
    assert _call(status="archived", stashed_at="x") == asr.NOT_FINISHED


def test_module_is_pure():
    import inspect
    src = inspect.getsource(asr)
    for forbidden in ("import os", "import redis", "cache_service", "open("):
        assert forbidden not in src, f"pure predicate module must not reference {forbidden}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_archived_status_repair.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.archived_status_repair'`

- [ ] **Step 3: Write minimal implementation**

Create `app/core/archived_status_repair.py`:

```python
"""Predicate for the archived-status repair pass.

Pure by construction: no I/O, no framework imports, every input a primitive
gathered by the caller. The whole decision is therefore unit-testable without
Docker, Redis or a filesystem — which matters because the local environment has
neither.

Spec: docs/superpowers/specs/2026-08-07-archived-status-repair-design.md
"""
from typing import AbstractSet, Optional, Union

# Rejection buckets, in evaluation order. These strings are part of the
# GET /admin/archived-status-repair contract — a blob failing several conditions
# is counted in the FIRST one, so renaming or reordering changes what operators
# read.
NOT_FINISHED = "not_finished"
STASHED = "stashed"
NOT_IN_GCS_LIST = "not_in_gcs_list"
NO_SNAPSHOT = "no_snapshot"
RUN_AFTER_ARCHIVE = "run_after_archive"
# Condition 6 is NOT evaluated by classify(): it needs a Redis round trip, and the
# caller runs it LAST so the EXISTS is only paid for blobs that already passed 1-5.
# The constant lives here so both callers report the same bucket name.
ARCHIVE_IN_PROGRESS = "archive_in_progress"


def classify(
    crawl_id: Union[str, int],
    status: Optional[str],
    stashed_at: Optional[str],
    verified_ids: AbstractSet[str],
    snapshot_mtime: Optional[float],
    log_mtime: Optional[float],
) -> Optional[str]:
    """Return None when the crawl must be repaired to 'archived', else the name
    of the FIRST condition it fails.

    Args:
        crawl_id: coerced to str — Redis blobs and the allowlist both hold strings.
        status: the blob's status field.
        stashed_at: truthy means the tar is under stash/, not crawls/.
        verified_ids: ids listed by tools/verify_archives_in_gcs.sh. The container
            has no GCS access; this file is the only admissible evidence.
        snapshot_mtime: mtime of {storage_path}/_status_snapshot.json, or None when
            the file is absent. Any OTHER stat error must make the caller skip the
            crawl entirely rather than pass None here.
        log_mtime: mtime of {storage_path}/crawler.log, same rule.

    The log/snapshot comparison is what separates "archived and untouched since"
    from "archived, then re-crawled". crawler.log is appended for the whole run and
    _cleanup_local_data keeps it deliberately (crawler_manager.py:2637-2640), so
    nothing removes it — unlike _completion_marker.json, which
    _cleanup_stale_state_for_relaunch deletes on every relaunch.
    """
    if status != "finished":
        return NOT_FINISHED
    if stashed_at:
        return STASHED
    if str(crawl_id) not in verified_ids:
        return NOT_IN_GCS_LIST
    if snapshot_mtime is None:
        return NO_SNAPSHOT
    if log_mtime is None or log_mtime >= snapshot_mtime:
        return RUN_AFTER_ARCHIVE
    return None


def is_status_repair_candidate(**kwargs) -> bool:
    """Boolean form of classify(), for callers that don't need the bucket."""
    return classify(**kwargs) is None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_archived_status_repair.py -v`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/archived_status_repair.py \
        apps-microservices/crawler-service/tests/test_archived_status_repair.py
git commit -m "feat(crawler): pure predicate for the archived-status repair"
```

---

### Task 2: Hoist the allowlist, accumulate finished blobs

**Goal:** Make `_reconcile_locked` load the GCS allowlist once and collect `finished` blobs, so two consumers can share both. Behaviour-preserving refactor.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py:3650-3652` (accumulator), `:3899-3900` (call site), `:3959` (signature), `:3988-3990` (drop the internal load)
- Test: `apps-microservices/crawler-service/tests/test_reconcile_status_repair.py`

**Acceptance Criteria:**
- [ ] `_reclean_archived_leftovers` takes `verified` as a parameter and no longer calls `_load_reclean_allowlist()` itself
- [ ] It still returns 0 without deleting anything when `verified is None`
- [ ] `_reconcile_locked` builds `finished_candidates` from `status == 'finished'` blobs
- [ ] `_load_reclean_allowlist` is called at most once per tick
- [ ] Existing reclean tests still pass unchanged in behaviour

**Verify:** `python -m pytest tests/test_crawler_manager_reclean.py tests/test_reconcile_status_repair.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `tests/test_reconcile_status_repair.py`:

```python
# tests/test_reconcile_status_repair.py
"""Reconciliation-side wiring of the archived-status repair.

Task 2 covers the refactor (allowlist hoisted, finished blobs accumulated);
Task 3 adds the pass itself to this same file.
"""
import inspect

import pytest
from unittest.mock import AsyncMock, patch

from app.core.crawler_manager import CrawlerManager


def test_reclean_receives_the_allowlist_instead_of_loading_it():
    src = inspect.getsource(CrawlerManager._reclean_archived_leftovers)
    assert "_load_reclean_allowlist" not in src, (
        "the allowlist must be loaded once in _reconcile_locked and passed in, "
        "so the repair pass and the reclean share one read"
    )
    sig = inspect.signature(CrawlerManager._reclean_archived_leftovers)
    assert "verified" in sig.parameters


@pytest.mark.asyncio
async def test_reclean_still_deletes_nothing_without_an_allowlist():
    mgr = CrawlerManager()
    with patch.object(CrawlerManager, "_cleanup_local_data") as cleanup:
        actioned = await mgr._reclean_archived_leftovers(
            [{"crawl_id": "1", "storage_path": "/nope"}], set(), None)
    assert actioned == 0
    cleanup.assert_not_called()


def test_reconcile_collects_finished_candidates():
    src = inspect.getsource(CrawlerManager._reconcile_locked)
    assert "finished_candidates" in src, (
        "the scan loop only collected status=='archived'; the repair pass needs "
        "the finished blobs from the same pass over the pipeline results"
    )
    assert src.count("_load_reclean_allowlist") == 1, (
        "exactly one allowlist read per tick"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reconcile_status_repair.py -v`
Expected: FAIL — `_load_reclean_allowlist` still appears in the reclean source; `verified` not in the signature.

- [ ] **Step 3: Write minimal implementation**

In `crawler_manager.py`, at the accumulator block (`:3650-3652`), add one line:

```python
        auto_stash_pool = []  # collected during scan; dispatched after the loop (auto-stash P2)
        archived_candidates = []  # status='archived' jobs — leftover storage/ reclean sweep
        finished_candidates = []  # status='finished' jobs — archived-status repair pass
        active_prev_ids = set()  # previous_crawl_id of in-flight jobs (update-restore guard)
```

In the scan loop, right after the `archived_candidates` collection (`:3666-3667`):

```python
                if status == "archived":
                    archived_candidates.append(job_data)

                if status == "finished":
                    finished_candidates.append(job_data)
```

At the reclean call site (`:3899-3900`), load the allowlist once and pass it down:

```python
        # One read per tick, shared by the repair pass (Task 3) and the reclean.
        verified_ids = self._load_reclean_allowlist()

        if settings.ARCHIVED_RECLEAN_ENABLED and archived_candidates:
            await self._reclean_archived_leftovers(archived_candidates, active_prev_ids, verified_ids)
```

Change the signature and drop the internal load (`:3959`, `:3988-3990`):

```python
    async def _reclean_archived_leftovers(self, jobs: list, active_prev_ids: set,
                                          verified: Optional[set]) -> int:
```

and replace

```python
        verified = self._load_reclean_allowlist()
        if verified is None:
            return 0  # fail-closed: no verified-in-GCS list -> no deletion at all
```

with

```python
        if verified is None:
            return 0  # fail-closed: no verified-in-GCS list -> no deletion at all
```

Update the docstring line that says the list is "written by tools/verify_archives_in_gcs.sh" to note it is now loaded by the caller:

```
        GCS-verified allowlist (ARCHIVED_RECLEAN_VERIFIED_LIST, written by
        tools/verify_archives_in_gcs.sh and loaded once per tick by
        _reconcile_locked, which passes it in). The list is the safety property —
```

Generalise the warning inside `_load_reclean_allowlist` (`:4041-4044`), now that it serves two consumers:

```python
            logger.warning(
                f"GCS-verified list '{path}' missing/empty — archived-leftover "
                f"reclean AND archived-status repair are both disabled "
                f"(fail-closed). Generate it host-side with "
                f"tools/verify_archives_in_gcs.sh")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_reconcile_status_repair.py tests/test_crawler_manager_reclean.py -v`
Expected: PASS. If a reclean test called `_reclean_archived_leftovers` with two arguments, add the third (`None` for the fail-closed cases, a real set otherwise) — that is the intended call-site update, not a behaviour change.

Run the whole suite: `python -m pytest tests/ -q`
Expected: only `test_archive_mock_e2e::test_daemon_logic` fails (pre-existing). Every other test passes.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py \
        apps-microservices/crawler-service/tests/test_reconcile_status_repair.py \
        apps-microservices/crawler-service/tests/test_crawler_manager_reclean.py
git commit -m "refactor(crawler): hoist the GCS allowlist read and collect finished blobs"
```

---

### Task 3: The repair pass

**Goal:** A leader-only, flag-gated, capped pass that flips proven-archived `finished` blobs to `archived` and hands them to the reclean in the same tick.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/config.py:110-120` (two settings)
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (imports, `_mtime_or_none`, `_archive_lock_held`, `_repair_archived_status`, call site before the reclean)
- Test: `apps-microservices/crawler-service/tests/test_reconcile_status_repair.py` (extend)

**Acceptance Criteria:**
- [ ] Flag off → zero Redis writes, zero `os.stat`
- [ ] `verified is None` → zero writes
- [ ] Repairs stop at `ARCHIVED_STATUS_REPAIR_MAX_PER_TICK`
- [ ] A repaired job is appended to `archived_candidates` so the reclean sees it this tick
- [ ] `archive_lock:{id}` held → skipped
- [ ] Redis error while probing the lock → skipped (fail-closed)
- [ ] `FileNotFoundError` on a sidecar → `None` mtime (a normal rejection); any other `OSError` → crawl skipped entirely
- [ ] Writes go through `_mark_as_archived`; the pass never builds a blob

**Verify:** `python -m pytest tests/test_reconcile_status_repair.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_reconcile_status_repair.py`:

```python
# --- Task 3: the pass itself ------------------------------------------------

import os

from app.core.config import settings


def _job(crawl_id="6712", status="finished", **over):
    j = {"crawl_id": crawl_id, "status": status, "storage_path": f"/app/storage/{crawl_id}"}
    j.update(over)
    return j


def _stat_map(snapshot=200.0, log=100.0):
    """os.path.getmtime side_effect: snapshot newer than log == archived, untouched."""
    def _getmtime(path):
        if path.endswith("_status_snapshot.json"):
            if snapshot is None:
                raise FileNotFoundError(path)
            return snapshot
        if path.endswith("crawler.log"):
            if log is None:
                raise FileNotFoundError(path)
            return log
        raise FileNotFoundError(path)
    return _getmtime


@pytest.fixture
def repair_on(monkeypatch):
    monkeypatch.setattr(settings, "ARCHIVED_STATUS_REPAIR_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ARCHIVED_STATUS_REPAIR_MAX_PER_TICK", 10, raising=False)


@pytest.mark.asyncio
async def test_flag_off_writes_nothing(monkeypatch):
    monkeypatch.setattr(settings, "ARCHIVED_STATUS_REPAIR_ENABLED", False, raising=False)
    mgr = CrawlerManager()
    archived = []
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch("app.core.crawler_manager.os.path.getmtime") as gm:
        n = await mgr._repair_archived_status([_job()], {"6712"}, archived)
    assert n == 0
    mark.assert_not_awaited()
    gm.assert_not_called()
    assert archived == []


@pytest.mark.asyncio
async def test_no_allowlist_writes_nothing(repair_on):
    mgr = CrawlerManager()
    archived = []
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark:
        n = await mgr._repair_archived_status([_job()], None, archived)
    assert n == 0
    mark.assert_not_awaited()


@pytest.mark.asyncio
async def test_repairs_and_hands_the_job_to_the_reclean(repair_on):
    mgr = CrawlerManager()
    archived = []
    job = _job()
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=False)), \
         patch("app.core.crawler_manager.os.path.getmtime", side_effect=_stat_map()):
        n = await mgr._repair_archived_status([job], {"6712"}, archived)
    assert n == 1
    mark.assert_awaited_once_with("6712")
    assert job["status"] == "archived"
    assert archived == [job], "a repaired job must be recleanable in the same tick"


@pytest.mark.asyncio
async def test_respects_the_per_tick_cap(repair_on, monkeypatch):
    monkeypatch.setattr(settings, "ARCHIVED_STATUS_REPAIR_MAX_PER_TICK", 2, raising=False)
    mgr = CrawlerManager()
    jobs = [_job(crawl_id=str(i)) for i in range(5)]
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=False)), \
         patch("app.core.crawler_manager.os.path.getmtime", side_effect=_stat_map()):
        n = await mgr._repair_archived_status(jobs, {str(i) for i in range(5)}, [])
    assert n == 2
    assert mark.await_count == 2


@pytest.mark.asyncio
async def test_archive_in_progress_is_skipped(repair_on):
    mgr = CrawlerManager()
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=True)), \
         patch("app.core.crawler_manager.os.path.getmtime", side_effect=_stat_map()):
        n = await mgr._repair_archived_status([_job()], {"6712"}, [])
    assert n == 0
    mark.assert_not_awaited()


@pytest.mark.asyncio
async def test_unreadable_sidecar_skips_the_crawl(repair_on):
    """PermissionError is not "file absent" — it must not become a rejection
    bucket, it must take the crawl out of consideration."""
    mgr = CrawlerManager()
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=False)), \
         patch("app.core.crawler_manager.os.path.getmtime",
               side_effect=PermissionError("EACCES")):
        n = await mgr._repair_archived_status([_job()], {"6712"}, [])
    assert n == 0
    mark.assert_not_awaited()


@pytest.mark.asyncio
async def test_recrawled_job_is_not_repaired(repair_on):
    """crawler.log newer than the snapshot: a run finished after the archive."""
    mgr = CrawlerManager()
    with patch.object(CrawlerManager, "_mark_as_archived", AsyncMock()) as mark, \
         patch.object(CrawlerManager, "_archive_lock_held", AsyncMock(return_value=False)), \
         patch("app.core.crawler_manager.os.path.getmtime",
               side_effect=_stat_map(snapshot=100.0, log=300.0)):
        n = await mgr._repair_archived_status([_job()], {"6712"}, [])
    assert n == 0
    mark.assert_not_awaited()


@pytest.mark.asyncio
async def test_archive_lock_probe_failure_is_fail_closed():
    mgr = CrawlerManager()
    fake = AsyncMock()
    fake.exists = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch("app.core.crawler_manager.cache_service.redis_client", fake):
        assert await mgr._archive_lock_held("6712") is True


def test_pass_never_builds_a_blob():
    src = inspect.getsource(CrawlerManager._repair_archived_status)
    assert "_mark_as_archived" in src
    assert "set_json" not in src, (
        "the repair must go through _mark_as_archived (fresh re-read, TTL cleared, "
        "publish), never write a blob of its own"
    )


def test_pass_runs_before_the_reclean():
    src = inspect.getsource(CrawlerManager._reconcile_locked)
    assert src.index("_repair_archived_status") < src.index("_reclean_archived_leftovers"), (
        "repair must run first, or a repaired job waits a whole tick for cleanup"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_reconcile_status_repair.py -v`
Expected: FAIL — `AttributeError: 'CrawlerManager' object has no attribute '_repair_archived_status'`

- [ ] **Step 3: Write the implementation**

In `app/core/config.py`, after `ARCHIVED_RECLEAN_VERIFIED_LIST` (`:120`):

```python
    # --- Archived-status repair (spec 2026-08-07) ---
    # Flips 'finished' blobs whose tar is listed in the GCS allowlist back to
    # 'archived', so GET /results stops 404-ing on them. Default off: deploy
    # inert, read the dry-run, then flip.
    ARCHIVED_STATUS_REPAIR_ENABLED: bool = False
    # Redis writes per tick. Starts low: reconcile_leader_lock has a 600s TTL and
    # NO heartbeat (crawler_manager.py:3350), so a tick that outlives it would let
    # a second leader in. Raise only after watching the "Reconciliation complete"
    # timing.
    ARCHIVED_STATUS_REPAIR_MAX_PER_TICK: int = 10
```

In `crawler_manager.py`, add the import next to the other `app.core` imports:

```python
from app.core import archived_status_repair
```

Add the module-level helper next to `_with_retry` (after `:80`):

```python
def _mtime_or_none(path: str) -> Optional[float]:
    """mtime of `path`, or None when it does not exist.

    Any OTHER OSError propagates on purpose: "unreadable" is not "absent", and a
    caller that conflated the two would treat a permissions problem as evidence.
    """
    try:
        return os.path.getmtime(path)
    except FileNotFoundError:
        return None
```

Add both methods to `CrawlerManager`, immediately before `_reclean_archived_leftovers`:

```python
    async def _archive_lock_held(self, crawl_id: str) -> bool:
        """True when archive_lock:{crawl_id} is held.

        Fail-closed: an unknown lock state returns True. archive_crawl writes
        _status_snapshot.json at :2550 but only marks the blob at :2605, after a
        tar that can run for minutes — during that window conditions 1-5 hold by
        construction, and repairing would strand the crawl as 'archived' if the
        tar then fails (:2622).
        """
        try:
            if cache_service.redis_client is None:
                return True
            return bool(await cache_service.redis_client.exists(f"archive_lock:{crawl_id}"))
        except Exception as e:
            logger.warning(
                f"status-repair: archive_lock probe failed for '{crawl_id}' "
                f"({e}) — treating as held.")
            return True

    async def _repair_archived_status(self, finished_candidates: list,
                                      verified: Optional[set],
                                      archived_candidates: list) -> int:
        """Flips 'finished' blobs whose tar is listed in GCS back to 'archived'.

        Called once per reconcile tick, leader-only, immediately before
        _reclean_archived_leftovers so a repaired crawl is recleanable in the same
        tick. Deletion is not this method's business — it only corrects a status
        the disk cannot express (the completion marker carries
        finished/failed/stopped, never 'archived').

        Requires BOTH the flag and the GCS-verified allowlist. No list => nothing
        (fail-closed), same property as the reclean.

        Never raises (reconcile-loop protection). Returns the count repaired.

        Spec: docs/superpowers/specs/2026-08-07-archived-status-repair-design.md
        """
        if not settings.ARCHIVED_STATUS_REPAIR_ENABLED:
            return 0
        if verified is None:
            return 0
        repaired = 0
        for job_data in finished_candidates:
            if repaired >= settings.ARCHIVED_STATUS_REPAIR_MAX_PER_TICK:
                break
            crawl_id = job_data.get("crawl_id")
            try:
                if not crawl_id:
                    continue
                storage_path = job_data.get("storage_path") or os.path.join(
                    settings.CRAWLER_STORAGE_PATH, str(crawl_id))
                try:
                    snapshot_mtime = _mtime_or_none(
                        os.path.join(storage_path, '_status_snapshot.json'))
                    log_mtime = _mtime_or_none(os.path.join(storage_path, 'crawler.log'))
                except OSError as e:
                    logger.warning(
                        f"status-repair: cannot stat sidecars of '{crawl_id}' "
                        f"({e}) — skipping, not rejecting.")
                    continue

                if archived_status_repair.classify(
                    crawl_id=crawl_id,
                    status=job_data.get("status"),
                    stashed_at=job_data.get("stashed_at"),
                    verified_ids=verified,
                    snapshot_mtime=snapshot_mtime,
                    log_mtime=log_mtime,
                ) is not None:
                    continue

                if await self._archive_lock_held(crawl_id):
                    logger.info(
                        f"status-repair: '{crawl_id}' skipped — archive in progress.")
                    continue

                logger.info(
                    f"ARCHIVED_STATUS_REPAIR crawl_id={crawl_id} finished->archived")
                await self._mark_as_archived(crawl_id)
                # Mirror the write locally so the reclean, which runs next on this
                # same list, sees an 'archived' job.
                job_data["status"] = "archived"
                archived_candidates.append(job_data)
                repaired += 1
            except Exception as e:
                logger.warning(f"status-repair failed for '{crawl_id}': {e}")
        return repaired
```

Wire it in `_reconcile_locked`, replacing the block written in Task 2:

```python
        # One read per tick, shared by the repair pass and the reclean.
        verified_ids = self._load_reclean_allowlist()

        # Repair BEFORE the reclean: a crawl whose status is corrected here is
        # appended to archived_candidates and cleaned in this same tick.
        if settings.ARCHIVED_STATUS_REPAIR_ENABLED and finished_candidates:
            await self._repair_archived_status(
                finished_candidates, verified_ids, archived_candidates)

        if settings.ARCHIVED_RECLEAN_ENABLED and archived_candidates:
            await self._reclean_archived_leftovers(
                archived_candidates, active_prev_ids, verified_ids)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_reconcile_status_repair.py -v`
Expected: PASS

Run: `python -m pytest tests/ -q`
Expected: only the pre-existing `test_archive_mock_e2e` failure remains.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/config.py \
        apps-microservices/crawler-service/app/core/crawler_manager.py \
        apps-microservices/crawler-service/tests/test_reconcile_status_repair.py
git commit -m "feat(crawler): repair archived status in reconciliation, gated and capped"
```

---

### Task 4: Read-only dry-run endpoint

**Goal:** `GET /admin/archived-status-repair` reports what the pass would do, with a rejection bucket per blob, and writes nothing.

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/admin.py` (new route at the end of the file)
- Test: `apps-microservices/crawler-service/tests/test_admin_status_repair_endpoint.py`

**Acceptance Criteria:**
- [ ] Returns `verified_list_present`, `verified_ids_count`, `scanned`, `truncated`, `candidates`, `candidates_count`, `rejected` (six buckets), `stash_only_hint`
- [ ] Rejection buckets follow the predicate's evaluation order, first failure wins
- [ ] `limit` bounds the number of keys scanned; `truncated` says whether it bit
- [ ] Does NOT depend on `get_job_or_recover`
- [ ] Writes nothing — no `set_json`, no `_mark_as_archived`
- [ ] 503 when Redis is unavailable
- [ ] Works with no allowlist: `verified_list_present: false`, zero candidates

**Verify:** `python -m pytest tests/test_admin_status_repair_endpoint.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `tests/test_admin_status_repair_endpoint.py`:

```python
# tests/test_admin_status_repair_endpoint.py
"""GET /admin/archived-status-repair — the dry-run for the repair pass.

Read-only by construction. The four existing /admin/* routes that take
Depends(get_job_or_recover) can write through its recovery path; this one must
not, so the contract is asserted rather than assumed.
"""
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

BLOBS = {
    # candidate: finished, not stashed, in the list, snapshot newer than log
    "crawl_job:6712": {"crawl_id": "6712", "status": "finished",
                       "storage_path": "/app/storage/6712"},
    # rejected by condition 1
    "crawl_job:6713": {"crawl_id": "6713", "status": "archived",
                       "storage_path": "/app/storage/6713"},
    # rejected by condition 2
    "crawl_job:6714": {"crawl_id": "6714", "status": "finished",
                       "stashed_at": "2026-08-01T00:00:00",
                       "storage_path": "/app/storage/6714"},
    # rejected by condition 3 -> also the stash_only_hint population
    "crawl_job:6715": {"crawl_id": "6715", "status": "finished",
                       "storage_path": "/app/storage/6715"},
}


def _getmtime(path):
    if path.endswith("_status_snapshot.json"):
        return 200.0
    if path.endswith("crawler.log"):
        return 100.0
    raise FileNotFoundError(path)


@pytest.fixture
def client(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)

    fake = MagicMock()

    async def _scan_iter(match=None, count=None):
        for k in BLOBS:
            yield k

    fake.scan_iter = _scan_iter
    pipe = MagicMock()
    pipe.get = MagicMock()
    pipe.execute = AsyncMock(return_value=[json.dumps(b) for b in BLOBS.values()])
    fake.pipeline = MagicMock(return_value=pipe)
    fake.exists = AsyncMock(return_value=0)

    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)
    return TestClient(app)


def test_reports_candidates_and_buckets(client):
    from app.core.crawler_manager import crawler_manager
    with patch.object(type(crawler_manager), "_load_reclean_allowlist",
                      return_value={"6712", "6713", "6714"}), \
         patch("app.router.admin.os.path.getmtime", side_effect=_getmtime):
        body = client.get("/admin/archived-status-repair").json()

    assert body["verified_list_present"] is True
    assert body["verified_ids_count"] == 3
    assert body["scanned"] == 4
    assert body["candidates"] == ["6712"]
    assert body["candidates_count"] == 1
    assert body["rejected"]["not_finished"] == 1      # 6713
    assert body["rejected"]["stashed"] == 1           # 6714
    assert body["rejected"]["not_in_gcs_list"] == 1   # 6715
    assert body["stash_only_hint"] == 1               # 6715 fails only condition 3


def test_no_allowlist_yields_no_candidates(client):
    from app.core.crawler_manager import crawler_manager
    with patch.object(type(crawler_manager), "_load_reclean_allowlist",
                      return_value=None), \
         patch("app.router.admin.os.path.getmtime", side_effect=_getmtime):
        body = client.get("/admin/archived-status-repair").json()
    assert body["verified_list_present"] is False
    assert body["candidates_count"] == 0


def test_limit_truncates(client):
    from app.core.crawler_manager import crawler_manager
    with patch.object(type(crawler_manager), "_load_reclean_allowlist",
                      return_value={"6712"}), \
         patch("app.router.admin.os.path.getmtime", side_effect=_getmtime):
        body = client.get("/admin/archived-status-repair?limit=2").json()
    assert body["scanned"] == 2
    assert body["truncated"] is True


def test_endpoint_writes_nothing(client):
    from app.core.crawler_manager import crawler_manager
    from common_utils.redis import cache_service
    with patch.object(type(crawler_manager), "_load_reclean_allowlist",
                      return_value={"6712"}), \
         patch("app.router.admin.os.path.getmtime", side_effect=_getmtime), \
         patch.object(cache_service, "set_json", AsyncMock()) as sj, \
         patch.object(type(crawler_manager), "_mark_as_archived", AsyncMock()) as mark:
        client.get("/admin/archived-status-repair")
    sj.assert_not_awaited()
    mark.assert_not_awaited()


def test_503_when_redis_down(client, monkeypatch):
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", None, raising=False)
    assert client.get("/admin/archived-status-repair").status_code == 503


def test_does_not_depend_on_get_job_or_recover():
    import inspect
    from app.router import admin
    src = inspect.getsource(admin.archived_status_repair_dry_run)
    assert "get_job_or_recover" not in src, (
        "the dry-run must not route through the dependency whose recovery path "
        "writes — that is the very bug being repaired"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_admin_status_repair_endpoint.py -v`
Expected: FAIL — 404 on the route / `AttributeError: module 'app.router.admin' has no attribute 'archived_status_repair_dry_run'`

- [ ] **Step 3: Write the implementation**

Append to `app/router/admin.py` (the module already imports `os`, `json`, `logging`, `Query`, `Depends`, `HTTPException`, `verify_api_key`, `cache_service`, `settings`; add the two below if absent):

```python
from app.core import archived_status_repair
from app.core.crawler_manager import crawler_manager, CRAWL_JOB_PREFIX, _mtime_or_none


@router.get("/archived-status-repair", dependencies=[Depends(verify_api_key)])
async def archived_status_repair_dry_run(
    limit: int = Query(2000, ge=1, le=20000,
                       description="Max crawl_job keys to scan. Counts below "
                                   "describe the scanned subset only."),
):
    """Dry-run of the archived-status repair pass: what it WOULD flip, and why
    each finished blob was rejected.

    Read-only. Deliberately does not take Depends(get_job_or_recover) — that
    dependency's recovery path writes, which is the defect this repairs.

    Spec: docs/superpowers/specs/2026-08-07-archived-status-repair-design.md
    """
    client = cache_service.redis_client
    if client is None:
        raise HTTPException(status_code=503, detail="Redis not connected")

    verified = crawler_manager._load_reclean_allowlist()

    keys = []
    truncated = False
    async for key in client.scan_iter(match=f"{CRAWL_JOB_PREFIX}*", count=500):
        keys.append(key)
        if len(keys) >= limit:
            truncated = True
            break

    blobs = []
    if keys:
        pipe = client.pipeline()
        for key in keys:
            pipe.get(key)
        for raw in await pipe.execute():
            if not raw:
                continue
            try:
                blobs.append(json.loads(raw))
            except (TypeError, ValueError):
                continue

    buckets = {
        archived_status_repair.NOT_FINISHED: 0,
        archived_status_repair.STASHED: 0,
        archived_status_repair.NOT_IN_GCS_LIST: 0,
        archived_status_repair.NO_SNAPSHOT: 0,
        archived_status_repair.RUN_AFTER_ARCHIVE: 0,
        archived_status_repair.ARCHIVE_IN_PROGRESS: 0,
    }
    candidates = []
    stash_only_hint = 0
    unreadable = 0

    for blob in blobs:
        crawl_id = blob.get("crawl_id")
        if not crawl_id:
            continue
        storage_path = blob.get("storage_path") or os.path.join(
            settings.CRAWLER_STORAGE_PATH, str(crawl_id))
        try:
            snapshot_mtime = _mtime_or_none(
                os.path.join(storage_path, '_status_snapshot.json'))
            log_mtime = _mtime_or_none(os.path.join(storage_path, 'crawler.log'))
        except OSError:
            unreadable += 1
            continue

        reason = archived_status_repair.classify(
            crawl_id=crawl_id,
            status=blob.get("status"),
            stashed_at=blob.get("stashed_at"),
            verified_ids=verified or set(),
            snapshot_mtime=snapshot_mtime,
            log_mtime=log_mtime,
        )
        if reason == archived_status_repair.NOT_IN_GCS_LIST:
            # Fails ONLY condition 3 => would be repairable if its tar were in
            # crawls/. Mostly stash-origin crawls (spec §7), majorated by crawls
            # whose tar exists nowhere.
            stash_only_hint += 1
        if reason is not None:
            buckets[reason] += 1
            continue
        if verified is None:
            buckets[archived_status_repair.NOT_IN_GCS_LIST] += 1
            continue
        if await crawler_manager._archive_lock_held(crawl_id):
            buckets[archived_status_repair.ARCHIVE_IN_PROGRESS] += 1
            continue
        candidates.append(str(crawl_id))

    return {
        "verified_list_present": verified is not None,
        "verified_ids_count": len(verified) if verified else 0,
        "scanned": len(keys),
        "truncated": truncated,
        "unreadable_sidecars": unreadable,
        "candidates": candidates,
        "candidates_count": len(candidates),
        "rejected": buckets,
        "stash_only_hint": stash_only_hint,
    }

```

`_mtime_or_none` is imported from `crawler_manager` rather than redefined — one contract, one implementation.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_status_repair_endpoint.py -v`
Expected: PASS

Run: `python -m pytest tests/ -q`
Expected: only the pre-existing `test_archive_mock_e2e` failure remains.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/router/admin.py \
        apps-microservices/crawler-service/tests/test_admin_status_repair_endpoint.py
git commit -m "feat(crawler): read-only dry-run endpoint for the archived-status repair"
```

---

### Task 5: Document the pass in CLAUDE.md

**Goal:** The service's own doc carries the flags, the predicate's reasoning, and — above all — the kill switch, so an operator does not learn it from the spec.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md` (the "Redis Connection Leak Prevention" section already carries the SET NX subsection added by `2a12a098`; the new subsection goes after it)

**Acceptance Criteria:**
- [ ] Both settings documented with defaults and the reason the cap starts at 10
- [ ] The kill switch is named explicitly: `rm /app/archives/verified_in_gcs.list`, and the fact that the repair flag is NOT it
- [ ] Says that generating the allowlist arms `_reclean_archived_leftovers` for ~2398 already-`archived` crawls
- [ ] Points to the spec

**Verify:** `grep -c "verified_in_gcs.list" apps-microservices/crawler-service/CLAUDE.md` → ≥ 2

**Steps:**

- [ ] **Step 1: Add the subsection**

After the "Disk recovery must not clobber (2026-08-07)" subsection, insert:

```markdown
#### Archived-status repair (2026-08-07)

`_repair_archived_status`, in `_reconcile_locked` just before the reclean, flips
`finished` blobs back to `archived` when their tar is listed in the GCS allowlist.
It exists because `get_results_archive` branches on `status == 'archived'`
(`:1638`), so a blob that lost that status 404s forever on `/results`. Two
populations: the recovery stubs fixed forward by `2a12a098`, and the pre-existing
"legacy stuck at finished" of `:2503-2505`.

| setting | default | note |
|---|---|---|
| `ARCHIVED_STATUS_REPAIR_ENABLED` | `false` | deploy inert, read the dry-run, then flip |
| `ARCHIVED_STATUS_REPAIR_MAX_PER_TICK` | `10` | low on purpose: `reconcile_leader_lock` has a 600s TTL and **no** heartbeat (`:3350`) |

Six conditions, evaluated in order — `finished`, not stashed, id in the allowlist,
`_status_snapshot.json` present, `crawler.log` **older** than the snapshot, and
`archive_lock:{id}` free. The freshness check is anchored on `crawler.log` and not
on `_completion_marker.json`: `_cleanup_stale_state_for_relaunch` deletes the
marker on every relaunch (`:3494`) while `_cleanup_local_data` keeps the log
deliberately (`:2637-2640`). Anchoring on the marker was fail-open on re-crawled
ids and would have made `/results` serve the previous generation's tar.

Dry-run: `GET /admin/archived-status-repair` — read-only, does not take
`Depends(get_job_or_recover)`.

**Kill switch.** `rm /app/archives/verified_in_gcs.list` — the file is re-read
every tick, so it disarms in ≤ 300s with no restart. Turning
`ARCHIVED_STATUS_REPAIR_ENABLED` off does **not** stop `_reclean_archived_leftovers`;
they are disjoint settings. And note that merely *creating* that allowlist arms the
reclean for the ~2398 already-`archived` crawls that still carry a `storage/`
subtree — set `ARCHIVED_RECLEAN_ENABLED=false` first if that is not wanted yet.
Neither the status flip nor the `rmtree` has a reverse.

Spec: `docs/superpowers/specs/2026-08-07-archived-status-repair-design.md`.
Plan: `docs/superpowers/plans/2026-08-07-archived-status-repair.md`.
```

- [ ] **Step 2: Verify**

Run: `grep -c "verified_in_gcs.list" apps-microservices/crawler-service/CLAUDE.md`
Expected: ≥ 2

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-service/CLAUDE.md
git commit -m "docs(crawler): document the archived-status repair pass and its kill switch"
```

---

## Merge

```bash
git checkout features/poc
git merge --no-ff <branch> -m "merge(crawler): reparation du statut des crawls archives"
python -m pytest apps-microservices/crawler-service/tests/ -q   # only the pre-existing test_archive_mock_e2e failure
```

Do **not** push and do **not** deploy — the operator owns both. §9 of the spec is the runbook, and its step 4 (`ARCHIVED_RECLEAN_ENABLED=false`) must happen before the allowlist file exists.
