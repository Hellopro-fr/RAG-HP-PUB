# Auto-Stash/Unstash Follow-Up — Design

- **Date:** 2026-06-02
- **Status:** Design — approved in brainstorming, pending implementation plan
- **Service:** `crawler-service` (Python orchestrator). No BO change.
- **Branch:** `features/poc`
- **Parent spec:** `docs/superpowers/specs/2026-06-01-auto-stash-unstash-workflow-design.md`

> Line numbers are indicative (captured during brainstorming on `features/poc`); the plan re-pins them.

## 1. Motivation

Operator feedback on the shipped auto-stash/unstash workflow surfaced four items. Investigation (5-agent read-only sweep over the shipped code + BO launch flow) resolved them to **two code fixes + two doc/runbook notes**:

| # | Feedback | Verdict | Action |
|---|---|---|---|
| ② | Started an already-stashed crawl → got a **fresh crawl** instead of fetch-from-GCS + resume | **Real bug** | **Fix A** (code) |
| ③ | Cannot **see** `stashed_at` / `downloaded_at` | Confirmed — not exposed anywhere | **Fix B** (code) |
| ① | What about **existing data** (pre-feature crawls)? | Real gap, but covered operationally | Runbook note |
| ④ | Webhook error → no download → **no stashing**? | **False premise** | Doc clarification |

## 2. Fix A — Unstash-on-start (the retrieve bug)

### Root cause (verified)
`start_crawl` (`crawler_manager.py:368`) checks `stashed_at` **only on `previous_crawl_id`** — the update-mode diff target (`:548-551` → `_restore_previous_crawl` → `unstash_crawl`). It **never checks `stashed_at` on the crawl's own `crawl_id` being launched.** So when `/start` is called on an id whose own data is stashed (a `stopped`/`failed`/`finished` crawl that the sweep auto-stashed, then relaunched), the STORAGE SETUP block (`:507-520`) `makedirs` an empty dir and spawns Node against it → **fresh crawl, GCS stash orphaned, local disk wasted.** The gap is **mode-independent** (standard mode never even runs the update block).

Last session's "same-ID restart does not exist" premise was correct *for the update→previous mapping* (`shell.php:140-142` sends a new started id + a separate previous id) but **missed the relaunch-of-a-stashed-id path** — which is the reported bug.

### Design
In `start_crawl`, **after** the capacity claim + crawl-lock are held, **before** the STORAGE SETUP block (`:507`): read the started crawl's existing Redis record (`existing_job_info = await cache_service.get_json(job_key)` — add this read if `start_crawl` doesn't already hold the prior record at this point; for a fresh crawl it is `None`). If it has `stashed_at` set, unstash it inline.

```python
# --- AUTO-STASH: resume-on-start ---
# If this crawl's own data is stashed in GCS, restore it before spawning so the
# crawl resumes from its request_queue instead of starting fresh (which would
# orphan the GCS stash + waste local disk). Mirrors the previous_crawl_id restore
# below and the /results inline-unstash. is_restart (OOM relaunch) never stashes
# (the crawl was running, not terminal) → guard naturally skips it.
if not is_restart and existing_job_info and existing_job_info.get("stashed_at"):
    try:
        await self.unstash_crawl(existing_job_info)     # restore storage from gs://stash/, clear stashed_at, 2-phase GCS delete
    except HTTPException:
        await _rollback_claim(decrement_counter=True)
        raise
    except Exception as e:
        await _rollback_claim(decrement_counter=True)
        logger.error(f"Failed to unstash crawl '{crawl_id}' on start: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to unstash crawl '{crawl_id}' from GCS: {str(e)}",
        )
```

### Verified-safe ordering (was the open caveat)
`_cleanup_stale_state_for_relaunch` (`:2899-2935`) **only unlinks `_completion_marker.json`** — it does NOT touch `datasets/` or `request_queues/`. So the sequence unstash → `makedirs` (dir already exists, no-op) → cleanup → spawn is correct:
- unstash restores `datasets/` + `request_queues/` (the resume data) + the stale `_completion_marker.json` from when it was stashed;
- cleanup strips that stale terminal marker (desired — a resuming crawl must not carry a prior terminal marker, or the reconciler would mis-declare it finished);
- Node spawns against the restored `request_queue` → Crawlee **resumes** from pending requests.

### Semantics
- `stopped` crawl → resumes from remaining queued URLs (the user's intent).
- `failed` crawl → resumes from its queue state.
- `finished` crawl → empty queue → resumes to a quick no-op. **Correct** — the goal is "no fresh crawl, no orphaned stash," not forcing work.
- Applies to **standard and update mode** (the started id, regardless of mode). Independent of the existing `previous_crawl_id` restore — both can fire in one start (started id first).

### Error handling
On unstash failure (502/504 from `unstash_crawl`) → `_rollback_claim(decrement_counter=True)` + raise (releases the slot + lock, mirrors the update-mode restore error path at `:552-561`).

### Edge cases
- **OOM relaunch** (`is_restart=True`): an OOM crawl is `restarting_oom` (slot held, never terminal), so `stashed_at` is never set; the `not is_restart` guard is belt-and-suspenders.
- **Fresh crawl** (id never run): no existing Redis record / no `stashed_at` → guard skips.
- **Stash↔unstash churn:** a `stopped` crawl auto-stashes only after `STASH_SAFETY_TIMEOUT_SECONDS` (48h). A relaunch within 48h finds it not-yet-stashed → no churn. Relaunch after 48h → stash-then-unstash once (acceptable; user declined a sweep relaunch-guard).

## 3. Fix B — Status visibility

### Design
Expose the four auto-stash metadata fields (already in Redis `job_data`, currently invisible) on the status response.

- `CrawlStatus` (`schemas/crawler.py:140-158`): add four optional, nullable fields:
  ```python
  stashed_at: Optional[str] = Field(None, description="ISO ts when data was moved to GCS stash; null if local.")
  downloaded_at: Optional[str] = Field(None, description="ISO ts of the last successful /results download (auto-stash grace start).")
  finished_at: Optional[str] = Field(None, description="ISO ts of the terminal transition (auto-stash safety-timeout start).")
  size_bytes: Optional[int] = Field(None, description="Estimated archive size (auto-stash disk-pressure ordering).")
  ```
- `get_status` (`crawler_manager.py:1365-1452`): map the four from `job_info` (`job_info.get("stashed_at")`, etc.) into the `CrawlStatus` construction.

### Properties
- **Backward-compatible:** optional/nullable → legacy crawls + crawls lacking a field return `null`; the BO and existing callers are unaffected (no contract break, no required-field addition).
- **No extra Redis read:** the fields are already in the `job_info` dict `get_status` receives.
- Visible via `GET /status/{id}` and the list endpoint; the BO dashboard can later surface them if desired (out of scope here).

## 4. Existing data (item ①) — operator runbook, no code

Pre-feature terminal crawls lack `finished_at`/`downloaded_at`/`size_bytes`, so the sweep's grace + timeout branches never fire for them (only disk-pressure, which sorts them last at `size_bytes`=0). **Steady-state is already covered:** an existing crawl re-downloaded after deploy gets `downloaded_at` stamped → auto-stashes via grace; new crawls flow normally. The only true gap is **old terminal crawls that will never be re-downloaded.**

**Resolution (no code):** run the existing `tools/stash_crawls_batch.py` once post-deploy to bulk-stash current on-disk crawls. `stash_crawl`'s preconditions (terminal status, not stashed, not archived) do **not** require `finished_at`, so it works on legacy crawls. This is a one-time disk drain; the auto-sweep + download-grace handle everything thereafter. (Rejected alternatives: a backfill endpoint stamping `finished_at`/`size_bytes`, and an eligibility fallback reading disk in the sweep — both add code for what a one-time batch run already achieves.)

## 5. Webhook-error stashing (item ④) — false premise, doc only

A failed/never-downloaded crawl **does** auto-stash — via the 48h safety-timeout, not the download-grace path. `finished_at` is stamped at the terminal transition (`_stamp_terminal_fields`) **before** the failure webhook is dispatched (verified ordering: monitor-exit `:1173`→`:1200`; OOM `:661`→`:666`; OOM-relaunch-fail `:726`→`:730`; stale-detection `:3232`→`:3240`). A failed webhook is queued in `FAILED_CALLBACKS_KEY` for replay and never alters Redis status. So webhook delivery failure **cannot** block stashing. The only "no `finished_at`" case is a never-exiting zombie, which stale-detection catches (and itself stamps `finished_at`).

**Resolution (no code):** document this in `crawler-service/CLAUDE.md`. The 48h wait (which doubles as the operator investigation window) is kept as-is per the decision; tune `STASH_SAFETY_TIMEOUT_SECONDS` if 48h proves long.

## 6. Documentation

`apps-microservices/crawler-service/CLAUDE.md` (Auto-Stash Workflow section): add notes that
1. `start_crawl` unstashes a stashed started id inline before spawning (resume-on-start) — not just the update-mode `previous_crawl_id`;
2. failed/never-downloaded crawls auto-stash via the 48h safety-timeout regardless of webhook delivery;
3. `GET /status` now exposes `stashed_at`/`downloaded_at`/`finished_at`/`size_bytes`;
4. existing-data drain is a one-time `tools/stash_crawls_batch.py` run.

## 7. Testing

- **Fix A:** `start_crawl` on a stashed started id calls `unstash_crawl` then proceeds (mock `unstash_crawl`; assert called once + Node spawn reached); unstash failure → `_rollback_claim` + `HTTPException`. `is_restart=True` or no `stashed_at` → `unstash_crawl` not called. Reuse the `manager_with_mocks` fixture (`test_start_crawl_capacity.py`) + the routing pattern from `test_auto_stash_update_restore.py`.
- **Fix B:** `get_status` maps the four fields when present in `job_info`; returns `null` when absent. Unit test on the `CrawlStatus` mapping.

## 8. Decisions Log

| # | Decision | Choice |
|---|---|---|
| D1 | Retrieve-bug fix owner | Service-side inline unstash-on-start (mirrors `previous_crawl_id` restore + `/results`) |
| D2 | Unstash timing | Inline (consistent with the existing update-mode restore holding the slot) |
| D3 | Existing data | One-time `stash_crawls_batch.py` drain (no backfill code) |
| D4 | Visibility surface | Four optional fields on `CrawlStatus` / `get_status` (not a separate admin endpoint) |
| D5 | Failed-crawl stash | Keep 48h safety-timeout (false-premise concern; no code) |

## 9. Out of Scope / Deferred

- Sweep guard against stashing a relaunch-pending `stopped`/`failed` crawl (user chose service-side fix alone; churn is negligible given the 48h timeout).
- Backfill endpoint / eligibility-fallback for legacy `finished_at` (superseded by the one-time batch drain).
- BO dashboard surfacing the four new `/status` fields.
- Separate/shorter `STASH_FAILED_TIMEOUT` for failed crawls.
- Operator-only `/admin/job-metadata/{id}` endpoint.

## 10. Verification Provenance

Grounded by a 4-investigator + synthesis read-only workflow over `crawler-service` + Hellopro BO. Decisive findings: (1) root cause = missing `stashed_at` guard on the started id in `start_crawl` (`:507-568`), confirmed against `shell.php:140-142`; (2) `_cleanup_stale_state_for_relaunch` only removes the completion marker (ordering safe); (3) the four fields absent from `CrawlStatus` (`:140-158`) + `get_status`; (4) `finished_at` stamped before every webhook → timeout-stash unaffected by webhook delivery.
