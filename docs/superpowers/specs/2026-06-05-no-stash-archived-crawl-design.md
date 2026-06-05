# Design — Auto-stash must never stash an already-archived crawl

- **Date:** 2026-06-05
- **Status:** APPROVED (brainstorm) — ready for plan
- **Service:** `crawler-service` (Python orchestrator) + `tools/download_daemon.sh`
- **Origin:** crawl `5957` (pateer-france.fr) was archived, downloaded, then auto-stashed minutes later.

---

## 1. Problem & evidence

Crawl `5957`:
- BO: `est_archiver=1`, `statut_dspi=13`, finished `2026-02-26` (`domaine_scrapping_produit_ia`).
- Crawler `GET /status/5957`: `status="finished"`, `downloaded_at=2026-06-05T12:11:09`, `stashed_at=2026-06-05T13:16:46`, `finished_at=null`, `size_bytes=null`.

Δ(download → stash) ≈ **1h05m** > `STASH_GRACE_SECONDS` (default 3600s) → stashed via the **grace** branch.

## 2. Root cause — status disconnect

The crawl is archived (BO `est_archiver=1`; data in GCS `crawls/`), but its crawler-side Redis `status` is **`finished`**, not `archived`. This is the known legacy class (per crawler-service CLAUDE.md: *"crawls stuck at 'finished' due to a previous bug where `_mark_as_archived` was never called"*); these crawls also predate the auto-stash fields (`finished_at=null`).

Chain: old finished crawl still had local data → `GET /results` served it (local-generate path, `crawler_manager.py:1537`) and stamped `downloaded_at` (`router/crawler.py:23,342`, **no status guard**) → the auto-stash sweep saw `finished + downloaded_at + grace elapsed` → stashed it.

The existing "don't stash archived" guards — `_is_stash_eligible` (`crawler_manager.py:3061`, status must be `finished|failed|stopped`) and `stash_crawl`'s 409 (`:2428`, `:2476`) — **never fired, because the crawler didn't believe the crawl was archived.**

The current archived-detection that *would* heal status (`archive_crawl` GCS-fallback, `crawler_manager.py:2117-2134`) performs a **full GCS download** via `_retrieve_from_gcs_daemon` — fine for a one-shot archive call, far too heavy to run per-candidate in a periodic sweep.

## 3. Invariant (goal)

> The auto-stash sweep must never stash a crawl whose **current** data is already safely in the GCS archive (`crawls/{id}.tar.gz`). On confidently detecting one, heal `status='archived'`, free the redundant local data, and skip the stash.

"Confidently" = the GCS object exists **and** is large enough to not be truncated **and** is not older than the local data (guards in §6).

## 4. Non-goals (out of scope)

- Bulk migration of all `est_archiver=1` crawls (3925 today). The trigger is **download-driven** (legacy crawls have `finished_at=null`, so the safety-timeout branch can't fire on them — only `downloaded_at`+grace can). It bites only when a legacy archived crawl is accessed, so the per-stash guard self-heals on access. A bulk reconcile can be a separate operator job later.
- Deep archive **integrity** validation (checksums, tar verification) — that is `tools/gcs_archive_audit.py`'s job.
- Fixing the BO→crawler archive flow's status-setting for *new* archives (verify-only; the bug was historical).
- One-off cleanup of `5957`'s already-stashed copy (separate operator action).

## 5. Components

### C1 — Daemon: lightweight GCS metadata op (`tools/download_daemon.sh`)
A new **metadata-only** marker flow (no bytes transferred), reusing the existing `.request/.done/.error` convention and the existing `DOWNLOAD_*` env (watch dir `DOWNLOAD_REQUESTS_PATH`, results dir `DOWNLOAD_RESULTS_PATH`, `DOWNLOAD_GCS_PREFIX` default `crawls`):

- Consume `{id}.exists-request`.
- Run `gcloud storage ls -l gs://$BUCKET/$DOWNLOAD_GCS_PREFIX/{id}.tar.gz`.
- Write one of:
  - `{id}.exists-yes` — body = `<size_bytes>\t<iso8601_create_time>` parsed from `ls -l`.
  - `{id}.exists-no` — object absent (ls returns no match).
  - `{id}.exists-error` — transient gcloud failure (non-zero for reasons other than "not found").
- Idempotent (re-running on an existing marker is safe). Marker family: `.exists-request / .exists-yes / .exists-no / .exists-error`.

### C2 — Crawler: `_gcs_archive_info(crawl_id)` (`crawler_manager.py`)
Mirrors `_retrieve_from_gcs_daemon`'s marker pattern (`crawler_manager.py:1547`) but writes `.exists-request` and polls for the `.exists-*` markers, bounded by `GCS_EXISTS_TIMEOUT_SECONDS`. Returns a small structured result:

```
GcsArchiveInfo(exists: bool, size_bytes: Optional[int], created_at: Optional[datetime])
```

**Fail-safe:** timeout / `.exists-error` / unparseable marker → `GcsArchiveInfo(exists=False, …)`. A false "not archived" only causes a normal stash (benign — data preserved in `stash/`); a false "archived" could wrongly heal+delete (riskier). Conservative by construction.

### C3 — Wire into the sweep (`_auto_stash_one`, `crawler_manager.py:3018`)
Before calling `stash_crawl`, classify the candidate (decision table §6). Runs inside the existing per-candidate background task, bounded by `STASH_MAX_PER_SWEEP` (default 5) — never blocks the leader/sweep.

```
info = await self._gcs_archive_info(crawl_id)
if self._is_confidently_archived(info, local_mtime):
    await self._mark_as_archived(crawl_id)                 # heal status -> 'archived'
    logger.info(f"AUTO_STASH skip crawl_id={crawl_id} reason=already_archived")
    self._free_local_crawl_data(crawl_id)                  # reuse archive_crawl's local cleanup
    logger.info(f"AUTO_STASH local_freed crawl_id={crawl_id}")
    return                                                  # do NOT stash
# else: not confidently archived (absent / truncated / stale) -> stash normally (preserves local data)
await self.stash_crawl(job_data)
```

### C4 — Belt: don't start grace for correctly-archived crawls (`_record_downloaded_at`, `router/crawler.py:23`)
Skip stamping `downloaded_at` when the fresh `status == 'archived'`. Near-zero cost; prevents a *correctly*-archived crawl from ever entering the grace window. Complements C3 (which catches the `finished` legacy case).

## 6. Sweep decision table

Let `info = _gcs_archive_info(crawl_id)`, `floor = GCS_ARCHIVE_MIN_BYTES`, `local_mtime = mtime(dataset dir)`.

| Condition | Meaning | Action |
|---|---|---|
| `not info.exists` | no GCS archive | **stash normally** (unchanged behavior) |
| `info.exists` & `size < floor` | truncated/corrupt archive | **stash normally** (preserve good local data) |
| `info.exists` & `size ≥ floor` & (`created_at` or `local_mtime` missing) | can't prove freshness | **stash normally** (conservative) |
| `info.exists` & `size ≥ floor` & `created_at < local_mtime` | **stale** archive (local newer — e.g. re-crawl reused `crawl_id`, not yet re-archived) | **stash normally** (preserve newer local data) |
| `info.exists` & `size ≥ floor` & `created_at ≥ local_mtime` | confidently archived, current | **heal `archived` + free local + skip stash** |

Only the last row heals/deletes/skips. Every other row stashes, which always *preserves* data.

`crawl_id == id_domaine` for initial crawls (the BO `/start` payload sends `id = id_domaine`), so the same id is reused across re-crawls of a domain — that is exactly why the freshness (`created_at ≥ local_mtime`) guard is required, not YAGNI.

A byte-level `local == GCS` content compare is intentionally **not** done: a terminal crawl's dataset is immutable for its `crawl_id`, and a true compare would require downloading the full tar (defeating the lightweight check). The size+freshness guards off the same `ls -l` cover the realistic failure modes (truncation, staleness) cheaply.

## 7. Config (`app/core/config.py`)

| Setting | Default | Purpose |
|---|---|---|
| `GCS_EXISTS_TIMEOUT_SECONDS` | `30` | Max wait for the `.exists-*` marker before fail-safe False. |
| `GCS_ARCHIVE_MIN_BYTES` | `1024` | Size floor below which a GCS archive is treated as truncated/unsafe → not safe-to-delete. |

Bucket/prefix/paths reuse existing settings (`DOWNLOAD_GCS_PREFIX`, daemon `DOWNLOAD_REQUESTS_PATH`/`DOWNLOAD_RESULTS_PATH`).

## 8. Edge cases & fail-safes

- exists-op times out / errors → `exists=False` → stash normally. No heal, no delete.
- exists-op is **read-only** → no lock; `_mark_as_archived` is idempotent.
- Stale or truncated archive → stash normally (never delete local against a bad/old archive).
- Genuinely finished-not-archived crawl → `exists=False` → stashes exactly as today.
- C4 guard only short-circuits crawls already `status='archived'`; the `finished` legacy case is handled by C3.

## 9. Testing

- `_gcs_archive_info`: `.exists-yes` (parse size+time) → exists True with metadata; `.exists-no` → False; `.exists-error` → False; timeout → False; malformed `.exists-yes` body → False.
- `_is_confidently_archived` decision table: each of the 5 rows → correct verdict.
- `_auto_stash_one`: confidently-archived → `_mark_as_archived` called + local-free called + `stash_crawl` NOT called; every other row → `stash_crawl` called, no heal/delete.
- `_record_downloaded_at`: `status='archived'` → no stamp; `status='finished'` → stamps.
- Daemon op: integration/manual — `gcloud ls` present (with size/time) / absent / error → correct marker + body.

## 10. Files touched

- `tools/download_daemon.sh` — C1 (exists-op).
- `apps-microservices/crawler-service/app/core/crawler_manager.py` — C2 (`_gcs_archive_info`, `_is_confidently_archived`, local-free helper reuse), C3 (wire into `_auto_stash_one`).
- `apps-microservices/crawler-service/app/router/crawler.py` — C4 (`_record_downloaded_at` guard).
- `apps-microservices/crawler-service/app/core/config.py` — `GCS_EXISTS_TIMEOUT_SECONDS`, `GCS_ARCHIVE_MIN_BYTES`.
- Tests under `apps-microservices/crawler-service/tests/`.
- Docs: `tools/CLAUDE.md` (marker family) + `apps-microservices/crawler-service/CLAUDE.md` (auto-stash already-archived guard).

## 11. Open items to verify during implementation

- Exact `gcloud storage ls -l` output format → robust parse of size + create time (and the iso8601 conversion).
- The crawl's local dataset path used for `local_mtime` (the storage/dataset dir the stash would tar) — use the same path `stash_crawl` tars, so mtime reflects what's at risk.
- Confirm `crawl_id == id_domaine` reuse semantics for re-crawls (drives the freshness guard); if ids are in fact unique-per-run, the freshness guard is harmless but the stale row becomes unreachable.
- The local-data cleanup helper to reuse from `archive_crawl` (the post-archive delete) — confirm it's safely callable from the sweep path.

## 12. References

- `crawler_manager.py`: `_is_stash_eligible:3061`, `_select_stash_candidates:2992`, `_auto_stash_one:3018`, `stash_crawl:2411` (guards `:2428`,`:2476`), `get_results_archive:1500`, `_retrieve_from_gcs_daemon:1547`, archive GCS-fallback `:2117-2134`, `_mark_as_archived:2264`.
- `router/crawler.py`: `_record_downloaded_at:23` (called `:342`).
- `tools/download_daemon.sh`; `tools/CLAUDE.md` (daemon env + marker conventions); `tools/gcs_archive_audit.py` (deep integrity — out of scope).
- crawler-service CLAUDE.md "Auto-Stash Workflow" + "Archiving — GCS Fallback".
