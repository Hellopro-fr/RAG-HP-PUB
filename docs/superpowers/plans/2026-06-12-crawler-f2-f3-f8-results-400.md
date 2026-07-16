# Crawler F2/F3/F8 — /results 400-running, hygiène blob, compteurs stash — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kill the three crawler-side causes of the /results 400-running incident: the finalize/webhook race (F2), gen-1 blob/disk state leaking into re-crawls (F3), and counters reading 0 after stash (F8).

**Architecture:** All in `apps-microservices/crawler-service`. F2-A hardens `_monitor_process`'s terminal write (read-back verify); F2-B makes `get_results_archive` tolerate a stale `running` when the completion marker exists; F3 gates the `stashed_at` carry-over in `start_crawl` on the resume semantics and removes the stale completion marker; F8 persists final counters into the blob at finalize and serves them when local data is gone (disk counts are computed live — stash deletes the data, hence the zeros).

**Tech Stack:** Python 3 / FastAPI / Redis (fail-open `cache_service`). TDD with pytest — suite in `apps-microservices/crawler-service/tests/`, run from that directory: `python -m pytest tests/ -x -q`. Branch `features/poc`. Spec: `docs/superpowers/specs/2026-06-12-crawler-f2-f3-f8-results-400-design.md`.

**Key code facts (verified 2026-06-12):**
- `start_crawl` (crawler_manager.py:370) builds a FRESH `job_data` dict (L399-411) and wholesale-overwrites the blob (L485) → gen-1 counters/request_ids are already discarded on relaunch. The ONLY deliberately carried key is `stashed_at` (L417-418), consumed by the resume-on-start unstash block (~L522). Existing test: `tests/test_auto_stash_resume_on_start.py` — MUST stay green or be consciously amended.
- `/status` counters are DISK-DERIVED: `_count_files_in_dir(dataset_path)` (L1466-1468) → after a stash deletes local data, `/status` returns `urls_crawled=0`. That IS the F8 mechanism (no blob field is "zeroed" — the source of truth vanishes).
- `get_results_archive` (L1502): `status=="running"` → unconditional 400 (L1510-1511).
- `_monitor_process` terminal write: `job_info["status"]=final_status` … `set_json` (L1202-1211), marker write (L1217-1226), webhook task (L1231-1238). `cache_service.set_json` swallows exceptions (fail-open).

**Commits:** FR, short single-line `-m`.

---

### Task 1: F2-A — write-then-verify du statut terminal dans _monitor_process

**Goal:** A silently-lost finalize write is detected and rewritten before the webhook fires.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` — between the terminal `set_json` (~L1211) and the completion-marker block (~L1216)
- Test: `apps-microservices/crawler-service/tests/test_finalize_write_verify.py` (create)

**Acceptance Criteria:**
- [ ] After the terminal `set_json`, the blob is re-read; if `status != final_status` (or blob missing) → one rewrite + re-read; second mismatch → `logger.critical`, flow continues (webhook still fires — BO F1/F5 handle the 400)
- [ ] Happy path: exactly 1 extra `get_json`, no extra `set_json`
- [ ] Full suite green

**Verify:** `python -m pytest tests/test_finalize_write_verify.py -x -q` → pass; then `python -m pytest tests/ -x -q` → pass

**Steps:**

- [ ] **Step 1: Write the failing test.** Mirror the mocking style of `tests/test_crawler_manager_stash.py` (async tests, `cache_service` monkeypatched). Core cases:

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.core.crawler_manager import CrawlerManager

@pytest.mark.asyncio
async def test_finalize_rewrites_when_status_readback_mismatches():
    mgr = CrawlerManager()
    job_info = {"crawl_id": "42", "status": "running", "storage_path": "/tmp/x", "domain": "d"}
    # 1st read-back returns stale 'running' (lost write), 2nd returns 'finished'
    readbacks = [{"crawl_id": "42", "status": "running"}, {"crawl_id": "42", "status": "finished"}]
    with patch("app.core.crawler_manager.cache_service.get_json", AsyncMock(side_effect=readbacks)) as gj, \
         patch("app.core.crawler_manager.cache_service.set_json", AsyncMock()) as sj:
        await mgr._verify_terminal_status_persisted("crawl_job:42", job_info, "finished")
        assert sj.await_count == 1          # one rewrite
        assert gj.await_count == 2          # initial read-back + post-rewrite check

@pytest.mark.asyncio
async def test_finalize_no_rewrite_when_persisted():
    mgr = CrawlerManager()
    job_info = {"crawl_id": "42", "status": "finished"}
    with patch("app.core.crawler_manager.cache_service.get_json", AsyncMock(return_value={"status": "finished"})) as gj, \
         patch("app.core.crawler_manager.cache_service.set_json", AsyncMock()) as sj:
        await mgr._verify_terminal_status_persisted("crawl_job:42", job_info, "finished")
        assert sj.await_count == 0
        assert gj.await_count == 1
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_finalize_write_verify.py -x -q` → FAIL (`AttributeError: _verify_terminal_status_persisted`).

- [ ] **Step 3: Implement.** New method on `CrawlerManager` (place near `_stamp_terminal_fields`):

```python
    async def _verify_terminal_status_persisted(self, job_key: str, job_info: dict, final_status: str):
        """F2-A (incident /results 400-running): set_json is fail-open — a lost terminal
        write leaves the blob 'running' and the BO's immediate GET /results gets a 400.
        Read back once; on mismatch rewrite once and re-check. Never raises."""
        persisted = await cache_service.get_json(job_key)
        if persisted and persisted.get("status") == final_status:
            return
        logger.error(
            f"Finalize write lost for '{job_info.get('crawl_id')}' "
            f"(read-back={persisted.get('status') if persisted else None}); rewriting."
        )
        await cache_service.set_json(job_key, job_info)
        persisted2 = await cache_service.get_json(job_key)
        if not persisted2 or persisted2.get("status") != final_status:
            logger.critical(
                f"Finalize write STILL lost for '{job_info.get('crawl_id')}' after rewrite — "
                f"/results will 400 until reconcile heals the blob."
            )
```

Call site in `_monitor_process`, immediately after the terminal `await cache_service.set_json(job_key, job_info)` (the one following `self._stamp_terminal_fields(job_info)`):

```python
            await self._verify_terminal_status_persisted(job_key, job_info, final_status)
```

- [ ] **Step 4: Run tests** — targeted then full suite. Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/core/crawler_manager.py tests/test_finalize_write_verify.py
git commit -m "fix(crawler): F2-A verification relecture du statut terminal avant webhook"
```

---

### Task 2: F2-B — tolérance marker dans get_results_archive

**Goal:** A stale `running` blob no longer 400s when the completion marker proves the crawl is done; the blob is healed at the point of consumption.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py:1510-1511` (`get_results_archive`)
- Test: `apps-microservices/crawler-service/tests/test_results_running_marker_tolerance.py` (create)

**Acceptance Criteria:**
- [ ] `status=='running'` + `_completion_marker.json` present in `storage_path` → no 400; status healed to `finished` in memory + persisted; flow continues to the normal serve path
- [ ] `status=='running'` + no marker → 400 unchanged (`"Cannot get results for a running crawl."`)
- [ ] Full suite green

**Verify:** `python -m pytest tests/test_results_running_marker_tolerance.py -x -q` → pass; full suite pass

**Steps:**

- [ ] **Step 1: Failing test** (marker via `tmp_path`; stop the flow right after the heal by stubbing `_generate_archive_sync`):

```python
import os, json, pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from app.core.crawler_manager import CrawlerManager

@pytest.mark.asyncio
async def test_running_with_marker_is_tolerated_and_healed(tmp_path):
    mgr = CrawlerManager()
    (tmp_path / "_completion_marker.json").write_text(json.dumps({"final_status": "finished", "exit_code": 2}))
    job = {"crawl_id": "42", "status": "running", "storage_path": str(tmp_path)}
    with patch("app.core.crawler_manager.cache_service.set_json", AsyncMock()) as sj, \
         patch.object(CrawlerManager, "_generate_archive_sync", return_value="/tmp/a.tar.gz"):
        path, is_tmp = await mgr.get_results_archive(job, include=[])
    assert path == "/tmp/a.tar.gz"
    assert job["status"] == "finished"
    assert sj.await_count == 1  # heal persisted

@pytest.mark.asyncio
async def test_running_without_marker_still_400(tmp_path):
    mgr = CrawlerManager()
    job = {"crawl_id": "42", "status": "running", "storage_path": str(tmp_path)}
    with pytest.raises(HTTPException) as exc:
        await mgr.get_results_archive(job, include=[])
    assert exc.value.status_code == 400
```

- [ ] **Step 2: Run to verify failure** — first test FAILS with HTTPException 400.

- [ ] **Step 3: Implement.** Replace:

```python
        if job_info["status"] == "running":
             raise HTTPException(status_code=400, detail="Cannot get results for a running crawl.")
```

with:

```python
        if job_info["status"] == "running":
            # F2-B (incident /results 400-running): the blob can read a stale 'running'
            # right after finalize (lost/raced Redis write). The completion marker is
            # written by _monitor_process BEFORE the webhook and is the disk source of
            # truth — a genuinely active crawl never has one. Heal at consumption.
            marker_path = os.path.join(job_info.get("storage_path", ""), "_completion_marker.json")
            if job_info.get("storage_path") and os.path.exists(marker_path):
                logger.warning(
                    f"/results for '{crawl_id}': blob says 'running' but completion marker "
                    f"exists — treating as finished and healing the blob (F2-B)."
                )
                job_info["status"] = "finished"
                await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)
            else:
                raise HTTPException(status_code=400, detail="Cannot get results for a running crawl.")
```

- [ ] **Step 4: Run tests** — targeted + full suite. Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/core/crawler_manager.py tests/test_results_running_marker_tolerance.py
git commit -m "fix(crawler): F2-B /results tolere running si completion marker present (heal du blob)"
```

---

### Task 3: F3 — hygiène gen-1 dans start_crawl (stashed_at + marker)

**Goal:** A fresh re-crawl (dropdata) never inherits the previous generation's `stashed_at` (stale-GCS-unstash data-overwrite risk) nor its completion marker (recovery/F2-B mistyping).

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` — the `stashed_at` carry block (L417-418) + marker cleanup nearby
- Test: `apps-microservices/crawler-service/tests/test_start_crawl_gen1_hygiene.py` (create)

**Acceptance Criteria:**
- [ ] `stashed_at` carried into the fresh blob ONLY when `params.get("dropdata") is False` (resume semantics — OOM relaunch path sets exactly that; `_relaunch_oom_crawl` sets `params["dropdata"] = False`)
- [ ] Fresh start (`dropdata` absent or truthy): `stashed_at` NOT carried; a log line records the dropped stale value
- [ ] Fresh start: stale `{storage_path}/_completion_marker.json` removed best-effort (try/except + log)
- [ ] `tests/test_auto_stash_resume_on_start.py` still green — if it starts a resume WITHOUT `dropdata=False`, STOP, report DONE_WITH_CONCERNS with the exact failing expectation (product arbitration: spec §6 says the gen-1 overwrite danger primes over silent resume)
- [ ] Full suite green

**Verify:** `python -m pytest tests/test_start_crawl_gen1_hygiene.py tests/test_auto_stash_resume_on_start.py -x -q` → pass; full suite pass

**Steps:**

- [ ] **Step 1: Read first** — `app/core/crawler_manager.py` L388-418 + the resume-on-start block (~L522) + `tests/test_auto_stash_resume_on_start.py` IN FULL. Establish what `params` the resume scenario actually passes. The criterion below assumes resume ⇔ `dropdata is False`; if the resume test contradicts this, stop per acceptance criterion 4.

- [ ] **Step 2: Failing tests:**

```python
import pytest
from unittest.mock import AsyncMock, patch

# Reuse this module's existing start_crawl test fixtures from
# tests/test_start_crawl_capacity.py / test_auto_stash_resume_on_start.py
# (cache_service mock, local_processes empty, subprocess spawn stubbed).

@pytest.mark.asyncio
async def test_fresh_start_drops_gen1_stashed_at(start_crawl_harness):
    harness = start_crawl_harness(prior_blob={"crawl_id": "6430", "status": "finished",
                                              "stashed_at": "2026-05-23T10:00:00"})
    job_data = await harness.run(params={})  # dropdata absent => fresh
    assert "stashed_at" not in job_data

@pytest.mark.asyncio
async def test_resume_start_keeps_stashed_at(start_crawl_harness):
    harness = start_crawl_harness(prior_blob={"crawl_id": "6430", "status": "finished",
                                              "stashed_at": "2026-05-23T10:00:00"})
    job_data = await harness.run(params={"dropdata": False})
    assert job_data["stashed_at"] == "2026-05-23T10:00:00"

@pytest.mark.asyncio
async def test_fresh_start_removes_stale_marker(start_crawl_harness, tmp_path):
    marker = tmp_path / "_completion_marker.json"
    marker.write_text('{"final_status":"finished"}')
    harness = start_crawl_harness(storage_path=str(tmp_path), prior_blob={"crawl_id": "x", "status": "finished"})
    await harness.run(params={})
    assert not marker.exists()
```

(`start_crawl_harness` = small fixture to write in the test file, assembling the same mocks the existing start_crawl tests use; it returns the `job_data` actually passed to `set_json` for the job key.)

- [ ] **Step 3: Implement.** Replace L417-418:

```python
        if prior_job_info and prior_job_info.get("stashed_at"):
            job_data["stashed_at"] = prior_job_info["stashed_at"]
```

with:

```python
        # F3 — hygiène inter-générations : ne porter stashed_at dans le blob neuf QUE
        # pour une reprise explicite (dropdata=False, posé par le relaunch OOM / resume).
        # Un re-crawl frais qui hérite d'un stashed_at gen-1 fait dérouter /results vers
        # l'unstash d'un tar GCS obsolète qui ÉCRASE les données fraîches (incident
        # 2026-06-10, blobs 6430/6690 avec stashed_at du 23/05).
        if prior_job_info and prior_job_info.get("stashed_at"):
            if params.get("dropdata") is False:
                job_data["stashed_at"] = prior_job_info["stashed_at"]
            else:
                logger.warning(
                    f"start_crawl '{crawl_id}': dropping stale gen-1 stashed_at="
                    f"{prior_job_info['stashed_at']} (fresh start, dropdata!=False)."
                )

        # F3 — marker gen-1 : un _completion_marker.json résiduel ferait mal typer la
        # nouvelle génération (recovery disque + tolérance F2-B). Suppression best-effort.
        if prior_job_info and params.get("dropdata") is not False:
            stale_marker = os.path.join(job_storage_path, "_completion_marker.json")
            try:
                if os.path.exists(stale_marker):
                    os.remove(stale_marker)
                    logger.info(f"start_crawl '{crawl_id}': removed stale gen-1 completion marker.")
            except Exception as e:
                logger.warning(f"start_crawl '{crawl_id}': could not remove stale marker: {e}")
```

- [ ] **Step 4: Run tests** — new file + `test_auto_stash_resume_on_start.py` + full suite. Expected: pass (or STOP per criterion 4).

- [ ] **Step 5: Commit**

```bash
git add app/core/crawler_manager.py tests/test_start_crawl_gen1_hygiene.py
git commit -m "fix(crawler): F3 stashed_at et marker gen-1 purges au start frais (dropdata!=False)"
```

---

### Task 4: F8 — compteurs persistés au finalize, servis quand le disque est vide

**Goal:** `/status` keeps reporting the real crawl counts after stash/archive — re-triggers stop downgrading healthy crawls to insufficientData.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` — `_monitor_process` terminal write (persist counts) + the status-stats block (~L1460-1500, serve persisted counts when local data absent)
- Test: `apps-microservices/crawler-service/tests/test_status_counters_survive_stash.py` (create)

**Acceptance Criteria:**
- [ ] At finalize, `job_info` gains `final_urls_crawled` / `final_error_urls_crawled` (disk counts at terminal time) persisted in the same terminal `set_json`
- [ ] Status stats: when the dataset dir is ABSENT (stashed/archived/cleaned) and `final_urls_crawled` exists in the blob → serve the persisted values instead of disk zeros
- [ ] When neither disk data nor persisted finals exist → omit/None, NEVER a fabricated 0 if the schema allows it; if the response model requires ints, keep 0 but log the degradation (decision recorded in commit message)
- [ ] Confirmed mechanism note: disk-derived counts (L1466-1468) are why stash "zeroes" counters — record this in the test file docstring (closes the F8 localization question)
- [ ] Full suite green

**Verify:** `python -m pytest tests/test_status_counters_survive_stash.py -x -q` → pass; full suite pass

**Steps:**

- [ ] **Step 1: Read first** — the stats block L1460-1500 (`_count_files_in_dir` usage, the response object it feeds) and the schema it returns (`app/schemas/...` status model) to fix the exact field names + whether None is allowed.

- [ ] **Step 2: Failing tests:**

```python
"""F8 — root cause: /status counters are computed live from disk
(_count_files_in_dir, crawler_manager.py ~L1466). Stash deletes local data,
so post-stash /status read 0 — nothing 'zeroes' the blob. Fix: persist final
counts at finalize, serve them when the dataset dir is gone."""
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_finalize_persists_final_counts(monitor_harness, tmp_path):
    # dataset dir with 3 files at terminal time
    ds = tmp_path / "storage" / "datasets" / "d"
    ds.mkdir(parents=True)
    for i in range(3): (ds / f"f{i}.json").write_text("{}")
    job_info = await monitor_harness.finalize(exit_code=0, storage_path=str(tmp_path), domain="d")
    assert job_info["final_urls_crawled"] == 3

@pytest.mark.asyncio
async def test_status_serves_persisted_counts_when_disk_gone(status_harness, tmp_path):
    # no dataset dir on disk; blob carries persisted finals
    stats = await status_harness.get_stats(job_info={
        "crawl_id": "42", "status": "finished", "storage_path": str(tmp_path),
        "stashed_at": "2026-06-12T10:00:00",
        "final_urls_crawled": 428, "final_error_urls_crawled": 9,
    })
    assert stats.urls_crawled == 428
    assert stats.error_urls_crawled == 9
```

(`monitor_harness`/`status_harness`: fixtures in the test file wrapping the real finalize block / stats block with mocked cache + no subprocess — follow `tests/test_get_status_is_error.py` patterns for the stats side.)

- [ ] **Step 3: Implement (finalize side).** In `_monitor_process`, just before `self._stamp_terminal_fields(job_info)`:

```python
            # F8 — persister les compteurs terminaux dans le blob : les compteurs /status
            # sont dérivés du disque ; après un stash (données locales supprimées) ils
            # retombent à 0 et tout re-trigger BO downgrade le crawl en insufficientData.
            try:
                ds_path = os.path.join(job_info["storage_path"], "storage", "datasets", job_info.get("domain", ""))
                if not os.path.isdir(ds_path):
                    ds_path = os.path.join(job_info["storage_path"], "storage", "datasets",
                                           job_info.get("domain", "").replace(".", "-"))
                err_path = os.path.join(job_info["storage_path"], "storage", "datasets",
                                        f"error-{job_info.get('domain', '')}")
                job_info["final_urls_crawled"] = _count_files_in_dir(ds_path)
                job_info["final_error_urls_crawled"] = _count_files_in_dir(err_path)
            except Exception as e:
                logger.warning(f"Could not persist final counters for '{crawl_id}': {e}")
```

- [ ] **Step 4: Implement (serve side).** In the stats block (~L1466), after computing the disk counts:

```python
        # F8 — données locales absentes (stash/archive/cleanup) : servir les compteurs
        # terminaux persistés au finalize plutôt que des zéros de disque vide.
        if urls_crawled == 0 and not os.path.isdir(dataset_path) and job_info.get("final_urls_crawled") is not None:
            urls_crawled = job_info["final_urls_crawled"]
            error_urls_crawled = job_info.get("final_error_urls_crawled", error_urls_crawled)
```

(Adapt variable names to the real block read in Step 1; keep the existing variables' types.)

- [ ] **Step 5: Run tests** — targeted + full suite. Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/core/crawler_manager.py tests/test_status_counters_survive_stash.py
git commit -m "fix(crawler): F8 compteurs terminaux persistes au finalize et servis quand le disque est vide"
```

---

## Deploy

Crawler pipeline (`features/poc`), order-free vs the BO plan. Post-deploy watch: no new `(HTTP 400, attempt …)` alert mails; `/status` of a stashed crawl shows real counts.
