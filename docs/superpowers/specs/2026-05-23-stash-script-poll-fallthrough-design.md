# Stash Batch Script — POST Poll Fall-Through — Design

> **Status:** Draft 2026-05-23 — pending user review
> **Type:** Operational script fix (client-only)
> **Path:** `tools/stash_crawls_batch.py`
> **Predecessor spec:** `docs/superpowers/specs/2026-05-22-stash-crawls-batch-script-design.md`

## 1. Problem

During the first real batch run on `tools/ids_dspi_9_trier_taille.txt`, the script aborted with `TimeoutError: timed out` while POSTing `/crawler/stash/2347` (a 0.28 GB compressed crawl). Server-side, the stash continued and completed normally — the upload daemon shipped the tar to GCS shortly after. Only the client gave up.

```
2026-05-23 10:27:27,481 | INFO | POST http://localhost:8500/crawling-service/stash/2347 (size=0.28G)
...
TimeoutError: timed out
=== Batch summary ===
Processed: 213
  Done     7
  Skipped  1
  Notfound 205
  Failed   0
```

Stopped after Crawl 7 actually succeeded. With 198 remaining (including ones up to 20 GB), the current behaviour would abort the batch on virtually every multi-GB crawl.

### Why POST blocks longer than 30s

The predecessor spec § 2 stated *"endpoint returns 202 well before GCS upload starts"*. That is correct as written — but the endpoint still performs **all local-disk work synchronously** before returning 202. Reading `crawler_manager.py:2198-2423`, every request blocks on:

1. Pre-condition Redis reads — milliseconds.
2. `SET NX` lock acquire — milliseconds.
3. TOCTOU re-validation (Redis read) — milliseconds.
4. Bind-mount stat check — milliseconds.
5. `_estimate_archive_required_bytes` — `os.walk` over the whole storage_path. Seconds to minutes on dirs with hundreds of thousands of small files.
6. **`shutil.make_archive('gztar', root_dir=...)`** — full tar + gzip pass. **Dominant cost.**
7. `tarfile.open(...).getnames()` integrity check — second full read pass over the tar.
8. `os.rename` from staging to target — milliseconds.
9. Redis `set_json` `stashed_at` — milliseconds.
10. `_cleanup_data_keep_logs` — `os.walk` + per-file `os.remove`. Seconds to minutes on large file counts.

Only after step 10 does the endpoint return 202. On `/mnt/data` at 95% used (slow IO), a 0.28 GB compressed crawl can take 15–100s wall-clock. Projection by source size:

| Compressed source | Tar create | Integrity | Cleanup | **Wall-clock** |
|---|---|---|---|---|
| 0.28G | 10–60s | 5–30s | 1–10s | **15–100s** |
| 1G | 30s–3min | 30s–2min | 5–30s | **1–6min** |
| 9.7G (4803) | 5–25min | 5–15min | 30s–3min | **10–45min** |
| 17G (5621) | 10–45min | 10–30min | 1–5min | **20–80min** |
| 20G (6080) | 12–60min | 12–35min | 1–5min | **25–100min** |

Current `HTTP_TIMEOUT_SECONDS=30` cannot survive even the smallest band. Server side, `_LockHeartbeat` refreshes the lock every 5 min for up to 4 h (`LOCK_HEARTBEAT_MAX_DURATION_SECONDS=14400`), and `STASH_LOCK_TTL_SECONDS=1800`. Server can survive 100 min easily; client cannot survive 30s. **The whole bug is this mismatch.**

### Why fixing it client-side is sufficient

The server does not depend on the client connection. Confirmed empirically (crawls 2347+ landed in GCS after the script aborted) and by design — see predecessor spec § 9 *"the server-side stash is unaffected — it runs to completion regardless of the client connection"* plus `_LockHeartbeat` semantics. So the client just needs to **stop treating POST timeout as terminal** and instead watch for the artifact the server is in the process of producing.

A pure server-side fix (move tar to `BackgroundTasks`, return 202 immediately) is a cleaner long-term shape but has higher blast radius — production stash endpoint, lock ownership transfer, error-reporting contract change. Deferred. See § 10.

## 2. Architecture

Single client-side change in `tools/stash_crawls_batch.py`. **No server change. No spec change to the predecessor.**

The completion-poll loop is already the source of truth for success:

- Local tar absent **and** GCS tar present → done.
- `dead_letter/{id}.tar.gz` appears → server-side failure → fatal.
- Per-crawl timeout deadline elapsed → fatal.

These three signals remain meaningful regardless of how the POST resolved. So we change `process_crawl` to **treat POST timeout (and 5xx-after-retry) as "server may be processing; fall through to completion poll"** rather than `FatalError`.

```
POST /stash/{id} ──> server begins tar
                     ├─ 202 fast (small crawl)              → poll loop (existing)
                     ├─ 404                                 → notfound (existing)
                     ├─ 409                                 → skipped (existing)
                     ├─ 400                                 → invalid (existing)
                     ├─ TimeoutError / connection reset     → fall-through to poll (NEW)
                     ├─ 5xx after one retry                 → fall-through to poll (NEW)
                     └─ Other 2xx                           → fatal (existing)
```

## 3. Per-Crawl Processing — Changed Logic

```python
def process_crawl(size_bytes, crawl_id, state, cfg):
    wait_for_disk(size_bytes, cfg.disk_target)

    url = f"{cfg.crawler_base_url}/stash/{crawl_id}"
    logger.info("POST %s (size=%.2fG)", url, size_bytes / 1024**3)

    fell_through = False
    try:
        resp = http_post(url, cfg.http_timeout_seconds)
    except (TimeoutError, socket.timeout, urllib.error.URLError) as e:
        logger.warning(
            "POST %s did not return within %ds (%s). Server likely still tarring "
            "(see _LockHeartbeat). Falling through to completion poll.",
            crawl_id, cfg.http_timeout_seconds, e.__class__.__name__,
        )
        resp = None
        fell_through = True

    if resp is not None:
        if resp.status_code == 404:
            state.append("notfound", crawl_id); return
        if resp.status_code == 409:
            state.append("skipped", crawl_id, resp.text[:200].replace("\n", " ")); return
        if resp.status_code == 400:
            state.append("invalid", crawl_id, resp.text[:200].replace("\n", " ")); return
        if resp.status_code >= 500:
            logger.warning("5xx on %s — retrying in 30s", crawl_id)
            time.sleep(30)
            try:
                resp = http_post(url, cfg.http_timeout_seconds)
            except (TimeoutError, socket.timeout, urllib.error.URLError):
                resp = None
                fell_through = True
            if resp is not None and resp.status_code >= 500:
                logger.warning(
                    "5xx persisted on %s — falling through to poll; server may be processing",
                    crawl_id,
                )
                resp = None
                fell_through = True
        elif resp.status_code != 202:
            detail = f"unexpected {resp.status_code}: {resp.text[:200]}".replace("\n", " ")
            state.append("failed", crawl_id, detail)
            raise FatalError(f"Unexpected {resp.status_code} on {crawl_id}")

    # Completion poll — unchanged whether we got 202 or fell through.
    timeout_s = per_crawl_timeout(size_bytes)
    deadline = time.time() + timeout_s
    logger.info(
        "Polling completion for %s (timeout=%ds, fell_through=%s)",
        crawl_id, timeout_s, fell_through,
    )

    while time.time() < deadline:
        if _stop_requested:
            state.append("failed", crawl_id, "interrupted during poll")
            raise FatalError(f"Interrupted while polling {crawl_id}")
        if dead_letter_exists(crawl_id, cfg.stash_dead_letter_dir):
            state.append("failed", crawl_id, "dead_letter")
            raise FatalError(f"Upload daemon dead-lettered {crawl_id}")
        if not local_tar_exists(crawl_id, cfg.stash_local_dir):
            if gcs_tar_exists(crawl_id, cfg.stash_gcs_bucket, cfg.stash_gcs_prefix):
                state.append("done", crawl_id)
                logger.info("DONE %s (fell_through=%s)", crawl_id, fell_through)
                return
        time.sleep(cfg.poll_interval_seconds)

    state.append("failed", crawl_id, f"timeout after {timeout_s}s (fell_through={fell_through})")
    raise FatalError(f"Timeout waiting for {crawl_id} ({timeout_s}s)")
```

## 4. Timeout Constants — Recalibrated

Current values in `tools/stash_crawls_batch.py`:

```python
_TIMEOUT_MIN = 600          # 10 min
_TIMEOUT_MAX = 3600         # 60 min
_TIMEOUT_PER_GB = 180       # 3 min/GB
```

Calibrated against the wall-clock table in § 1 (worst-case bands):

```python
_TIMEOUT_MIN = 600          # 10 min   (unchanged)
_TIMEOUT_MAX = 7200         # 120 min  (was 60 min)
_TIMEOUT_PER_GB = 300       # 5 min/GB (was 3 min/GB)
```

| Compressed size | Old timeout | New timeout | Worst-case wall-clock | Margin |
|---|---|---|---|---|
| 0.28G | 600s | 600s | 100s | 6× |
| 1G | 600s | 600s | 360s | 1.7× |
| 9.7G (4803) | 1746s | 2910s | 2700s | 1.08× |
| 17G (5621) | 3060s | 5100s | 4800s | 1.06× |
| 20G (6080) | 3600s | 6000s | 6000s | 1.0× |

Worst-case margin on the largest crawl is tight (1.0×). Acceptable because (a) the table is the upper bound of empirical bands, (b) the server's own `LOCK_HEARTBEAT_MAX_DURATION_SECONDS=14400` (4 h) bounds the absolute ceiling — past that the lock heartbeat stops renewing and the tar will fail/dead-letter regardless. Aligning the client timeout to a hard 4 h would risk multi-hour client hangs on a genuinely stuck server; 2 h keeps the worst case bounded while still covering observed server performance.

`HTTP_TIMEOUT_SECONDS` default unchanged at **30s**. The POST is now allowed to time out at 30s — that is the trigger for fall-through. Operators can override via env if they want faster failure detection on dead servers.

## 5. HTTP Exception Surface

`urllib.request.urlopen(req, timeout=timeout)` may raise:

| Exception | Cause | Behaviour |
|---|---|---|
| `socket.timeout` (also `TimeoutError` on 3.10+) | server didn't send response headers within `timeout` | fall-through |
| `urllib.error.URLError` wrapping `ConnectionResetError` | server reset mid-response | fall-through |
| `urllib.error.URLError` wrapping `ConnectionRefusedError` | server not listening | fall-through (poll will time out) |
| `urllib.error.HTTPError` | server returned 4xx/5xx with body | caught inside `http_post`, returns `HttpResponse` |
| `OSError` (broken pipe, ENOTCONN) | rare; transient | fall-through |

We collapse `(TimeoutError, socket.timeout, urllib.error.URLError, OSError)` into the fall-through branch. `HTTPError` continues flowing through the existing 4xx/5xx logic via `http_post`'s own except.

`socket.timeout` is an alias for `TimeoutError` on Python 3.10+ but importing `socket` and listing it explicitly keeps the code self-documenting and survives older Python.

## 6. Idempotency & Resume Behaviour

Three new edge cases the predecessor spec did not cover:

**a) POST timed out, server actually completed.** Poll detects `local_tar absent + GCS present` → `done`. Indistinguishable from happy path.

**b) POST timed out, server actually failed (rare — only if a non-`_LockHeartbeat` failure landed mid-tar).** Poll detects `dead_letter` or hits per-crawl timeout → `failed`. Operator investigates.

**c) POST never reached server (network).** Poll loop sits idle until per-crawl timeout → `failed`. Next run re-POSTs:
- If server happened to receive and complete a stale request: `409 ALREADY_STASHED` → `skipped`.
- Else: fresh POST processes normally.

Both branches are safe because the server endpoint is **fully idempotent on `stashed_at`**: 409 short-circuits if the marker is set.

No new state class needed. The existing five (`done`, `skipped`, `invalid`, `notfound`, `failed`) cover all outcomes.

## 7. Edge Cases

| Case | Behaviour |
|---|---|
| POST timed out but `local_tar` still present after 60s | Server still tarring. Poll keeps looping. |
| POST timed out, `dead_letter` already there before POST | Detected first iteration of poll → fatal. (Stale dead-letter from a prior run would corrupt; operator must clear before re-run.) |
| POST returned 202 fast, GCS upload daemon down | Poll sees `local_tar` linger past per-crawl timeout → fatal. Operator restarts daemon. |
| `_stop_requested` (SIGINT) during fall-through poll | Same as existing — checked every iteration, exits at boundary. |
| 5xx persisted after retry → fall-through → poll times out | Lands in `failed` with `"timeout after Xs (fell_through=True)"`. Operator sees both signals. |
| POST returned 202, then network died before poll | Poll's GCS check via subprocess `gcloud storage ls` will return non-zero exit; poll keeps retrying until network back or deadline. |
| Crawl-folder is a sparse 20 GB volume that compresses to 100 MB | `_TIMEOUT_PER_GB` is keyed off **input file's compressed size**, not real source size. Underestimates → timeout. Acceptable: source list was generated from on-disk `du -sh`. If discrepancy observed, raise `_TIMEOUT_PER_GB` further or extend the input format to carry raw size. |

## 8. Logging

Added/changed lines:

- `WARNING POST {id} did not return within {N}s ({exc_class}). Server likely still tarring. Falling through to completion poll.` — every fall-through.
- `INFO Polling completion for {id} (timeout={s}s, fell_through={bool})` — extends existing poll log with fall-through flag.
- `INFO DONE {id} (fell_through={bool})` — extends existing done log.
- `state.append("failed", ..., f"timeout after {s}s (fell_through={bool})")` — carries fall-through context into the failed state file.

`fell_through=True` in the success log lets operators audit how often the POST timed out vs returned 202 — useful for sizing future server-side changes.

## 9. Testing Strategy

Three new unit tests in `tests/test_stash_crawls_batch.py` (additive — keep the 9 existing ones unchanged):

| # | Test | What it verifies |
|---|---|---|
| 10 | `test_process_crawl_post_timeout_falls_through_to_poll` | `http_post` raises `TimeoutError`. Mock `local_tar_exists` returns False, `gcs_tar_exists` returns True. Expects `state.append("done", ...)`. |
| 11 | `test_process_crawl_5xx_persisted_falls_through_to_poll` | Both POSTs return 503. Same poll-success mocks. Expects `state.append("done", ...)`. |
| 12 | `test_process_crawl_fall_through_times_out_marks_failed` | `http_post` raises `TimeoutError`. Mock `gcs_tar_exists` always False, `local_tar_exists` always True. Expects `state.append("failed", id, detail)` where `detail` contains `"fell_through=True"`, then `FatalError`. |

Existing tests adjusted:

- `test_per_crawl_timeout_formula` — updated assertions for new constants (`_TIMEOUT_MAX=7200`, `_TIMEOUT_PER_GB=300`).

No integration test. Same rationale as predecessor spec: punctual operational script.

**Manual smoke before re-running the full batch:**

1. Pick one small remaining crawl (e.g. next-smallest pending in `tools/ids_dspi_9_trier_taille.txt`).
2. Force a short POST timeout: `HTTP_TIMEOUT_SECONDS=1 python3 tools/stash_crawls_batch.py temp/smoke.txt`.
3. Expect: POST log → fall-through warning → poll log with `fell_through=True` → `DONE` log within ~3–10 min.
4. Verify `temp/smoke.txt.stash_done.txt` contains the ID, GCS object exists.
5. Reset `HTTP_TIMEOUT_SECONDS` and resume full batch.

## 10. Out of Scope (Deferred Follow-Ups)

- **Server-side `BackgroundTasks` migration of `stash_crawl`** so the endpoint returns 202 immediately after lock acquisition + bind-mount check. Aligns server with the spirit of predecessor spec § 2. Higher blast radius; document as deferred. Tracked in `/loop` follow-up list.
- **Pre-flight `_estimate_archive_required_bytes` optimisation** — uses `os.walk` which traverses every file. Could short-circuit via `du -sb` shell-out on Linux, or cache mtime-keyed estimates. Not blocking.
- **POST `Retry-After` header semantics on 5xx** — if/when server side adds the header (not currently), client could honour it instead of the fixed 30s wait. Cross-spec.
- **`Notfound 205` investigation** — orthogonal to this fix. Most input IDs not in Redis. Either Redis state was lost or those crawls predate the current job_data schema. Separate brainstorm.
- **`Failed 0` despite traceback** — the original `TimeoutError` path crashed before any `state.append`. Implicitly fixed by this spec since fall-through prevents the unrecorded crash, but worth noting: after this change, every POST outcome (success, fall-through, fatal) produces a state-file marker.

## 11. Acceptance

- [ ] `process_crawl` catches `(TimeoutError, socket.timeout, urllib.error.URLError, OSError)` from `http_post` and falls through to the completion poll.
- [ ] `process_crawl` falls through to poll on persisted 5xx (after one 30s retry), not `FatalError`.
- [ ] `process_crawl` still raises `FatalError` on: unexpected `2xx != 202`, dead-letter file present, poll deadline elapsed, `_stop_requested` mid-poll.
- [ ] `_TIMEOUT_MAX` raised to `7200` (120 min).
- [ ] `_TIMEOUT_PER_GB` raised to `300` (5 min/GB).
- [ ] `fell_through` flag threaded into poll log, done log, and failed-state detail.
- [ ] 3 new unit tests green.
- [ ] Updated `test_per_crawl_timeout_formula` green with new constants.
- [ ] Manual smoke on one small crawl with `HTTP_TIMEOUT_SECONDS=1` succeeds end-to-end.
- [ ] No server-side code change.
