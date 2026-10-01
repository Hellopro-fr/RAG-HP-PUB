# Stash Crawls Batch Script — Design

> **Status:** Approved 2026-05-22 — ready for implementation plan
> **Type:** Punctual operational script
> **Path:** `tools/stash_crawls_batch.py`

## 1. Problem

A list of 217 terminal crawls needs to be stashed to GCS to free local disk. 12 are already done (markers in the source list); 205 remain.

Operational constraints:
- `/mnt/data` is at **95% used** (67 GB free of 1.2 TB).
- Largest remaining crawls: 20 GB (6080), 17 GB (5621), 13 GB (6229), 9.7 GB (4803).
- Naively kicking POST /stash on 205 crawls in parallel would overflow disk: each in-flight stash creates a tar in `/app/stash/` that lingers until the upload daemon ships it to GCS.

The stash endpoint (`POST /crawler/stash/{crawl_id}`) is now production-ready (lock-heartbeat work landed 2026-05-22, commits `dace4e30..ff5fa217`). What is missing is a safe driver that:

1. Reads a source list of `<size>\t<id>[ → marker]` lines.
2. Skips lines with a marker (already done/deleted).
3. Stashes the rest sequentially, one at a time, waiting for the GCS upload daemon to free local disk before the next.
4. Survives interruption (resume via state file).
5. Aborts cleanly on disk pressure, 5xx, or upload failures rather than risking corruption.

## 2. Stash Endpoint Behaviour (recap)

`POST /crawler/stash/{crawl_id}` → 202 Accepted:

1. Validates `job_info`: status must be `failed`/`stopped`/`finished`, not already `stashed_at` set, not `archived`. Else 4xx.
2. Acquires ownership lock `stash_lock:{id}`.
3. Creates `/app/stash/{id}.tar.gz` via `shutil.make_archive`, lock TTL refreshed by `_LockHeartbeat`.
4. Sets `job_data["stashed_at"] = ISO timestamp` in Redis.
5. Deletes local source dir (`/app/storage/storages/<id>/`).
6. Releases lock. Endpoint returns 202 well before GCS upload starts.

The **upload daemon** (`tools/upload_daemon.sh`, configured with `UPLOAD_WATCH_DIR=stash/`, `UPLOAD_GCS_PREFIX=stash`) polls `/app/stash/`, uploads each tar to `gs://{bucket}/stash/`, then **deletes the local tar** on success or moves it to `crawler_archives/dead_letter/` on failure.

**Disk profile of a single stash on a crawl of size S:**

| Phase | Disk delta on `/mnt/data` |
|---|---|
| t0 (before POST) | source = S |
| t1 (tar created, source still on disk) | source + tar ≈ S + S′  (S′ ≈ 0.3 S to S) |
| t2 (source cleaned, before daemon picks up) | tar ≈ S′ |
| t3 (daemon shipped tar to GCS, local deleted) | 0 |

Peak local growth during the operation is **S′ + S** until t2, then **S′** until t3. With 67 GB free and a 20 GB crawl, the script must serialize and let the daemon drain between large crawls.

## 3. Architecture

Single Python 3 script run on the server VM where the crawler-service container runs.

```
┌────────────────────────────────────────────────────────────────┐
│ tools/stash_crawls_batch.py <input-file> [--dry-run]           │
└────────────────────────────────────────────────────────────────┘
        │
        ├─ Parse <input-file>: list of (size_bytes, crawl_id)
        │  • Lines with a marker (containing "→") are skipped silently.
        │  • Lines failing parse are logged and skipped.
        ├─ Read <input-file>.stash_done.txt; drop those IDs.
        ├─ Sort ascending by size_bytes.
        │
        └─ For each (size, crawl_id):
              ├─ [Disk guard] df free ≥ size + 10 GB? else wait 60 s, retry 30 min, then abort
              ├─ POST CRAWLER_BASE_URL/stash/{id} → expect 202
              │    ├─ 404 → log notfound, skip
              │    ├─ 409 → log skipped, skip
              │    ├─ 400 → log invalid, skip
              │    ├─ 5xx → retry once after 30 s, then ABORT
              │    └─ 2xx other → ABORT (unexpected)
              ├─ [Completion poll] every 10 s until:
              │    ├─ /app/stash/{id}.tar.gz absent on local disk
              │    └─ AND gs://{bucket}/stash/{id}.tar.gz exists
              │    Failure paths:
              │    ├─ crawler_archives/dead_letter/{id}.tar.gz appears → ABORT
              │    └─ Timeout = min(60min, max(10min, size_g*3min)) → ABORT
              └─ Append crawl_id to <input-file>.stash_done.txt
```

**Concurrency:** strictly 1. No threading. No async pool.

**Resumability:** state file is authoritative. On restart, the script re-parses the source, removes IDs present in `<input-file>.stash_done.txt`, and continues. IDs that were stashed but interrupted before being recorded (extremely rare — append happens immediately after GCS verification) will return 409 on re-POST and be moved to `stash_skipped.txt` — still safe.

## 4. Source File Format and Parser

Format (matches `temp/ids_dspi_9_trier_taille.txt`):

```
106M	6511 → Done
139M	6271
20G	6080
```

Each line: `<size>\t<crawl_id>[ <marker>]`. The arrow + marker (`→ Done`, `→ Supprimé`, etc.) indicates "do not stash". Lines may be blank.

Parser:

```python
def parse_line(raw: str) -> tuple[int, str] | None:
    line = raw.rstrip()
    if not line:
        return None
    parts = line.split("\t", 1)
    if len(parts) != 2:
        return None
    size_str, rest = parts
    if "→" in rest:                       # has skip marker
        return None
    crawl_id = rest.strip()
    if not crawl_id.isdigit():
        return None
    return (parse_size(size_str), crawl_id)


def parse_size(s: str) -> int:
    """'106M' -> 106*1024**2, '1.1G' -> 1.1*1024**3."""
    s = s.strip()
    unit = s[-1].upper()
    num = float(s[:-1])
    mult = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}[unit]
    return int(num * mult)
```

After parsing, deduplicate IDs (defensive — source should not contain duplicates, but parser MUST not silently drop them; raise on duplicate). Sort ascending by size.

## 5. Per-Crawl Processing

```python
def process_crawl(size_bytes: int, crawl_id: str, state: BatchState) -> None:
    # 1. Disk guard
    wait_for_disk(size_bytes)

    # 2. POST /stash/{id}
    url = f"{CRAWLER_BASE_URL}/stash/{crawl_id}"
    resp = http_post(url, timeout=30)

    if resp.status_code == 404:
        state.append("notfound", crawl_id); return
    if resp.status_code == 409:
        state.append("skipped", crawl_id, resp.text[:200]); return
    if resp.status_code == 400:
        state.append("invalid", crawl_id, resp.text[:200]); return
    if resp.status_code >= 500:
        logger.warning(f"5xx on {crawl_id}, retrying in 30s")
        time.sleep(30)
        resp = http_post(url, timeout=30)
        if resp.status_code >= 500:
            state.append("failed", crawl_id, f"5xx: {resp.text[:200]}")
            raise FatalError(f"5xx on {crawl_id}")
    if resp.status_code != 202:
        raise FatalError(f"Unexpected {resp.status_code} on {crawl_id}")

    # 3. Wait for upload completion
    deadline = time.time() + per_crawl_timeout(size_bytes)
    while time.time() < deadline:
        if dead_letter_exists(crawl_id):
            state.append("failed", crawl_id, "dead_letter")
            raise FatalError(f"Upload failed for {crawl_id}")
        if not local_tar_exists(crawl_id):
            if gcs_tar_exists(crawl_id):
                state.append("done", crawl_id)
                return
        time.sleep(10)

    state.append("failed", crawl_id, "timeout")
    raise FatalError(f"Timeout waiting for {crawl_id}")


def per_crawl_timeout(size_bytes: int) -> int:
    size_g = size_bytes / 1024**3
    return int(min(3600, max(600, size_g * 180)))  # 10 min – 60 min, 3 min/GB
```

GCS check: `gcloud storage ls gs://{bucket}/{prefix}/{crawl_id}.tar.gz`, exit 0 = exists.

Local-tar check: `os.path.exists(f"{STASH_LOCAL_DIR}/{crawl_id}.tar.gz")`.

Dead-letter check: `os.path.exists(f"{STASH_DEAD_LETTER_DIR}/{crawl_id}.tar.gz")`.

## 6. Disk Safety Guard

```python
SAFETY_MARGIN_BYTES = 10 * 1024**3        # 10 GB
DISK_WAIT_MAX_SECONDS = 30 * 60           # 30 min
DISK_WAIT_INTERVAL = 60                   # poll every 60 s


def wait_for_disk(needed_bytes: int) -> None:
    threshold = needed_bytes + SAFETY_MARGIN_BYTES
    deadline = time.time() + DISK_WAIT_MAX_SECONDS
    while True:
        free = shutil.disk_usage(DISK_TARGET).free
        if free >= threshold:
            return
        if time.time() > deadline:
            raise FatalError(
                f"Disk free {free/1024**3:.1f} GB < needed "
                f"{threshold/1024**3:.1f} GB after {DISK_WAIT_MAX_SECONDS}s"
            )
        logger.warning(
            f"Disk free {free/1024**3:.1f} GB < needed "
            f"{threshold/1024**3:.1f} GB; sleeping {DISK_WAIT_INTERVAL}s"
        )
        time.sleep(DISK_WAIT_INTERVAL)
```

`shutil.disk_usage(path)` returns the same numbers as `df` for the mount containing `path`.

## 7. State Files

All files live next to the input file. Class-suffixed, append-only.

| File | Line format | Purpose |
|---|---|---|
| `<input>.stash_done.txt` | `<id>\n` | resume skip list |
| `<input>.stash_skipped.txt` | `<id>\t<reason>\t<timestamp>` | 409 — already stashed/archived |
| `<input>.stash_invalid.txt` | `<id>\t<reason>\t<timestamp>` | 400 — wrong status |
| `<input>.stash_notfound.txt` | `<id>\t<timestamp>` | 404 — Redis lost job |
| `<input>.stash_failed.txt` | `<id>\t<reason>\t<timestamp>` | fatal — investigate |
| `<input>.stash_run.log` | `%(asctime)s \| %(levelname)s \| %(message)s` | per-run log (append) |

```python
class BatchState:
    def __init__(self, input_path: Path):
        self.input_path = input_path
        self.done_path = Path(f"{input_path}.stash_done.txt")
        self.done = self._load_done()

    def _load_done(self) -> set[str]:
        if not self.done_path.exists():
            return set()
        return {l.strip() for l in self.done_path.read_text().splitlines() if l.strip()}

    def append(self, klass: str, crawl_id: str, detail: str = "") -> None:
        path = Path(f"{self.input_path}.stash_{klass}.txt")
        ts = datetime.utcnow().isoformat(timespec="seconds")
        if klass == "done":
            line = f"{crawl_id}\n"
        else:
            line = "\t".join([crawl_id, detail, ts]) + "\n"
        with path.open("a") as f:
            f.write(line)
        if klass == "done":
            self.done.add(crawl_id)
```

## 8. Configuration

All via environment variables. CLI accepts only `<input-file>` and `--dry-run`.

| Var | Default | Purpose |
|---|---|---|
| `CRAWLER_BASE_URL` | `http://localhost:8500/crawler` | api-gateway-go prefix to crawler-service (matches T4 nginx config) |
| `STASH_LOCAL_DIR` | `/app/stash` | path on VM where tars sit before upload (override if bind-mount source differs) |
| `STASH_DEAD_LETTER_DIR` | `crawler_archives/dead_letter` | upload daemon failure dir |
| `STASH_GCS_BUCKET` | *(required, no default)* | bucket name for `gs://{bucket}/stash/` |
| `STASH_GCS_PREFIX` | `stash` | matches `UPLOAD_GCS_PREFIX` in upload daemon |
| `DISK_TARGET` | `/mnt/data` | mount to monitor for free space |
| `HTTP_TIMEOUT_SECONDS` | `30` | per HTTP request |
| `POLL_INTERVAL_SECONDS` | `10` | completion-poll cadence |

Missing `STASH_GCS_BUCKET` → script exits with error before touching anything.

## 9. Signals and Graceful Shutdown

- `SIGINT` / `SIGTERM` set a `stop_requested` flag.
- The flag is checked at every loop boundary: between crawls, between completion polls, between disk-guard sleeps.
- On detection: the current crawl is allowed to finish its completion poll (the server already kicked the stash; the tar will ship regardless). Once the current iteration completes, the script writes a summary and exits with code 130 (SIGINT) or 143 (SIGTERM).
- Mid-POST or mid-`gcloud` shell-out: the underlying syscall returns; the script logs the interruption and exits as soon as the current step concludes. The server-side stash is unaffected — it runs to completion regardless of the client connection (per `_LockHeartbeat`).
- Re-running the script resumes from `stash_done.txt`. Any crawl partially recorded (extremely unlikely — append happens after GCS verification) re-POSTs and lands as 409 → `stash_skipped.txt`.

## 10. Dry-Run Output

`python tools/stash_crawls_batch.py temp/ids_dspi_9_trier_taille.txt --dry-run`:

```
=== DRY RUN ===
Input:      temp/ids_dspi_9_trier_taille.txt
Skipped:    12 IDs with markers
Resume:     0 IDs in stash_done.txt
To process: 205 IDs, total ~210 GB

Order (ascending by size):
   1. 6271       139M    timeout=600s
   2. 6299       142M    timeout=600s
   ...
 204. 5621       17G     timeout=3060s
 205. 6080       20G     timeout=3600s

Config:
  CRAWLER_BASE_URL:      http://localhost:8500/crawler
  STASH_LOCAL_DIR:       /app/stash
  STASH_GCS_BUCKET:      <bucket-from-env>
  STASH_GCS_PREFIX:      stash
  DISK_TARGET:           /mnt/data (free=67G now)
  Disk threshold per crawl: 10G + size

No requests will be sent.
```

## 11. Testing Strategy

Unit tests in `tests/test_stash_crawls_batch.py`:

| # | Test | What it verifies |
|---|---|---|
| 1 | `test_parse_size_units` | K/M/G/T multipliers, decimal sizes |
| 2 | `test_parse_line_skips_markers` | `"→ Done"`, `"→ Supprimé"`, custom markers |
| 3 | `test_parse_line_handles_blank_and_malformed` | empty line, missing tab, non-digit ID |
| 4 | `test_parse_line_rejects_duplicates` | raises on duplicate ID across the file |
| 5 | `test_per_crawl_timeout_formula` | floor 10 min, ceiling 60 min, 3 min/GB middle |
| 6 | `test_batch_state_resume` | done IDs filtered on next run |
| 7 | `test_batch_state_append_classes` | each class writes correct file/format |
| 8 | `test_disk_guard_waits_then_passes` | monkeypatch `shutil.disk_usage`, verify wait + return |
| 9 | `test_disk_guard_aborts_on_timeout` | raises `FatalError` after `DISK_WAIT_MAX_SECONDS` |

Manual smoke before full run: create `temp/smoke.txt` with the 2 smallest pending IDs (`6271`, `6299`). Run the script for real. Inspect:
- `temp/smoke.txt.stash_done.txt` has both IDs.
- `/app/stash/` is empty.
- `gs://{bucket}/stash/6271.tar.gz` and `6299.tar.gz` exist.
- Crawler-service log shows `Stashed crawl '6271'` and `Stashed crawl '6299'`, no error.

No integration test — punctual script, mocked stash endpoint not worth maintaining.

## 12. Out of Scope

- Multi-VM/multi-host orchestration. Single VM, single process.
- Unstash. Restoration is operator-initiated, separate flow.
- Bandwidth throttling on GCS upload. Daemon handles.
- Notifications (Slack/email). Run output and state files are sufficient.
- Dynamic ordering (e.g., interleave large/small). Pure ascending size is sufficient.
- Automatic deletion or archive of completed source list. Operator keeps the source file.

## 13. Acceptance

- [ ] `tools/stash_crawls_batch.py` reads any `<size>\t<id>[ → marker]` input file.
- [ ] Skips marked lines without error.
- [ ] Sorts ascending by size before processing.
- [ ] Resumes from `<input>.stash_done.txt` on restart.
- [ ] Strict sequential: at most one in-flight stash + upload at any time.
- [ ] Pre-flight disk guard: `df` free ≥ size + 10 GB; waits up to 30 min if insufficient; aborts otherwise.
- [ ] Handles 202/400/404/409/5xx response codes per spec.
- [ ] Polls until local tar absent AND GCS tar present; aborts on dead-letter file appearance.
- [ ] Per-crawl timeout: `min(60 min, max(10 min, size_g × 3 min))`.
- [ ] Writes class-segmented state files (`stash_done`, `stash_skipped`, `stash_invalid`, `stash_notfound`, `stash_failed`).
- [ ] SIGINT/SIGTERM cause graceful exit between crawl boundaries.
- [ ] `--dry-run` prints plan without side effects.
- [ ] 9 unit tests pass.
- [ ] Manual smoke on 2 smallest pending IDs succeeds end-to-end.
