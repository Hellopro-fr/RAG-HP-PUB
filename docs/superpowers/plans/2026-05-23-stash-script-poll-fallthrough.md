# Stash Batch Script — POST Poll Fall-Through Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `tools/stash_crawls_batch.py` survive long-running `POST /crawler/stash/{id}` calls by treating client-side timeout, persisted 5xx, and connection reset as "server may still be tarring; fall through to the existing completion poll" instead of `FatalError`. Also raise the per-crawl poll-deadline ceiling so the largest crawls (20 GB) fit within budget.

**Architecture:** Client-only change. `process_crawl` wraps `http_post` in a try/except that collapses `TimeoutError`, `socket.timeout`, `urllib.error.URLError`, and `OSError` into a fall-through marker. Persisted 5xx (after one 30s retry) is treated the same way. The pre-existing completion-poll loop becomes the sole authority on success/failure for every code path except true protocol violations (4xx, unexpected non-202 2xx, dead-letter present, poll deadline elapsed). Two timeout constants are recalibrated: `_TIMEOUT_MAX 3600 → 7200` (60→120 min), `_TIMEOUT_PER_GB 180 → 300` (3→5 min/GB).

**Tech Stack:** Python 3.10 stdlib (`urllib.request`, `socket`, `logging`, `time`), pytest, `monkeypatch`. No server-side change.

**Reference spec:** `docs/superpowers/specs/2026-05-23-stash-script-poll-fallthrough-design.md`

---

## File Structure

| Path | Role | Change |
|---|---|---|
| `tools/stash_crawls_batch.py` | Single-process operational script | Add `import socket` at top, raise two constants, restructure `process_crawl` POST/retry block to fall through on timeout / persisted-5xx, thread `fell_through` flag into poll-loop logging and the failed-state detail. |
| `tools/test_stash_crawls_batch.py` | Pytest unit tests (9 existing, all green) | Update `test_per_crawl_timeout_formula` assertions for new constants. Add 3 new tests (timeout fall-through → done, 5xx persisted fall-through → done, fall-through → poll timeout → failed). |

No new files. No server-side file. No CLAUDE.md update (single internal-script behavior change, not service-level).

---

### Task 1: Fall-through on POST timeout / persisted-5xx + constant bump + 4 tests

**Goal:** `process_crawl` no longer raises `FatalError` on POST `TimeoutError` / `URLError` / `OSError` or on persisted 5xx; it falls through to the existing completion poll. New timeout constants accommodate worst-case 20 GB crawl wall-clock. Test suite covers all three fall-through paths.

**Files:**
- Modify: `tools/stash_crawls_batch.py` (single file: imports, constants, `process_crawl`)
- Modify: `tools/test_stash_crawls_batch.py` (update 1 test, add 3 tests)

**Acceptance Criteria:**
- [ ] `tools/stash_crawls_batch.py` imports `socket` at module top.
- [ ] `_TIMEOUT_MAX` is `7200`. `_TIMEOUT_PER_GB` is `300`. `_TIMEOUT_MIN` unchanged at `600`.
- [ ] `process_crawl` catches `(TimeoutError, socket.timeout, urllib.error.URLError, OSError)` raised by the FIRST `http_post` call; logs a warning containing the exception class name; sets a local `fell_through = True` flag and continues.
- [ ] `process_crawl` retries 5xx once after `time.sleep(30)`; if the retry itself raises one of the same four exception types OR returns another 5xx, it falls through (`fell_through = True`) instead of raising `FatalError`.
- [ ] `process_crawl` still raises `FatalError` for: unexpected non-202 2xx response, dead-letter file present mid-poll, `_stop_requested` mid-poll, poll deadline elapsed.
- [ ] Poll log line includes `fell_through={bool}`; `DONE` info log includes `fell_through={bool}`; failed-state detail on poll-timeout includes `fell_through={bool}`.
- [ ] `test_per_crawl_timeout_formula` updated with new expected values and passes.
- [ ] 3 new tests added and all pass.
- [ ] All 13 tests in `tools/test_stash_crawls_batch.py` green (10 existing + 3 new).

**Verify:**
```
python -m pytest tools/test_stash_crawls_batch.py -v
```
Expected: `13 passed` (10 existing + 3 new).

**Steps:**

- [ ] **Step 1: Write the 3 new failing tests + update the existing timeout-formula test**

Edit `tools/test_stash_crawls_batch.py`. Replace the existing `test_per_crawl_timeout_formula` body (currently lines 102–107) with the updated assertions, and append the three new tests at the end of the file.

Updated `test_per_crawl_timeout_formula`:

```python
def test_per_crawl_timeout_formula():
    # New formula: floor 10 min, ceiling 120 min, 5 min/GB.
    assert per_crawl_timeout(100 * 1024**2) == 600        # 0.1 GB → 30s < 600s → floor
    assert per_crawl_timeout(1 * 1024**3) == 600          # 1 GB → 300s < 600s → floor
    assert per_crawl_timeout(5 * 1024**3) == 1500         # 5 GB → 5*300 = 1500s
    assert per_crawl_timeout(20 * 1024**3) == 6000        # 20 GB → 20*300 = 6000s
    assert per_crawl_timeout(100 * 1024**3) == 7200       # 100 GB → ceiling 120 min
```

Append at the end of the file (after the existing `test_disk_guard_aborts_on_timeout`):

```python
# ============================================================
# T2: process_crawl fall-through tests (POST timeout / 5xx persisted / poll timeout)
# ============================================================
from unittest.mock import MagicMock  # noqa: E402

from stash_crawls_batch import (  # noqa: E402
    Config,
    HttpResponse,
    process_crawl,
)


def _cfg() -> Config:
    return Config(
        crawler_base_url="http://localhost:8500/crawler",
        stash_local_dir="/app/stash",
        stash_dead_letter_dir="/app/crawler_archives/dead_letter",
        stash_gcs_bucket="test-bucket",
        stash_gcs_prefix="stash",
        disk_target="/mnt/data",
        http_timeout_seconds=30,
        poll_interval_seconds=10,
    )


def test_process_crawl_post_timeout_falls_through_to_poll(monkeypatch, tmp_path):
    """POST raises TimeoutError → fall-through → poll sees GCS object → 'done'."""
    input_file = tmp_path / "ids.txt"
    input_file.write_text("139M\t6271\n", encoding="utf-8")
    state = BatchState(input_file)

    monkeypatch.setattr("stash_crawls_batch.wait_for_disk", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "stash_crawls_batch.http_post",
        MagicMock(side_effect=TimeoutError("timed out")),
    )
    monkeypatch.setattr("stash_crawls_batch.local_tar_exists", lambda *_a: False)
    monkeypatch.setattr("stash_crawls_batch.dead_letter_exists", lambda *_a: False)
    monkeypatch.setattr("stash_crawls_batch.gcs_tar_exists", lambda *_a: True)
    monkeypatch.setattr("stash_crawls_batch.time.sleep", lambda _s: None)

    process_crawl(139 * 1024**2, "6271", state, _cfg())

    assert "6271" in state.done
    done_lines = (tmp_path / "ids.txt.stash_done.txt").read_text().splitlines()
    assert done_lines == ["6271"]


def test_process_crawl_5xx_persisted_falls_through_to_poll(monkeypatch, tmp_path):
    """Both POST attempts return 503 → fall-through → poll sees GCS object → 'done'."""
    input_file = tmp_path / "ids.txt"
    input_file.write_text("139M\t6271\n", encoding="utf-8")
    state = BatchState(input_file)

    monkeypatch.setattr("stash_crawls_batch.wait_for_disk", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "stash_crawls_batch.http_post",
        MagicMock(return_value=HttpResponse(status_code=503, text="overloaded")),
    )
    monkeypatch.setattr("stash_crawls_batch.local_tar_exists", lambda *_a: False)
    monkeypatch.setattr("stash_crawls_batch.dead_letter_exists", lambda *_a: False)
    monkeypatch.setattr("stash_crawls_batch.gcs_tar_exists", lambda *_a: True)
    monkeypatch.setattr("stash_crawls_batch.time.sleep", lambda _s: None)

    process_crawl(139 * 1024**2, "6271", state, _cfg())

    assert "6271" in state.done


def test_process_crawl_fall_through_times_out_marks_failed(monkeypatch, tmp_path):
    """POST raises TimeoutError, GCS never appears → poll deadline elapses → 'failed' carries fell_through=True."""
    input_file = tmp_path / "ids.txt"
    input_file.write_text("139M\t6271\n", encoding="utf-8")
    state = BatchState(input_file)

    monkeypatch.setattr("stash_crawls_batch.wait_for_disk", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "stash_crawls_batch.http_post",
        MagicMock(side_effect=TimeoutError("timed out")),
    )
    monkeypatch.setattr("stash_crawls_batch.local_tar_exists", lambda *_a: True)
    monkeypatch.setattr("stash_crawls_batch.dead_letter_exists", lambda *_a: False)
    monkeypatch.setattr("stash_crawls_batch.gcs_tar_exists", lambda *_a: False)
    monkeypatch.setattr("stash_crawls_batch.time.sleep", lambda _s: None)

    # Fast-forward the clock so the poll-deadline elapses after one iteration.
    t = {"now": 0.0}

    def fake_time():
        return t["now"]

    def fake_advance(_s):
        t["now"] += 1_000_000

    monkeypatch.setattr("stash_crawls_batch.time.time", fake_time)
    monkeypatch.setattr("stash_crawls_batch.time.sleep", fake_advance)

    with pytest.raises(FatalError, match="Timeout waiting for 6271"):
        process_crawl(139 * 1024**2, "6271", state, _cfg())

    failed = (tmp_path / "ids.txt.stash_failed.txt").read_text()
    assert "6271" in failed
    assert "fell_through=True" in failed
```

- [ ] **Step 2: Run tests to verify they fail (red)**

Run:
```
python -m pytest tools/test_stash_crawls_batch.py -v
```

Expected: `test_per_crawl_timeout_formula` FAILS (asserts new ceilings against old constants), the 3 new tests FAIL with `ImportError` (no `Config`/`HttpResponse`/`process_crawl` re-export problem? all three are already module-level — should fail instead on behaviour: `FatalError` raised by current `process_crawl` instead of falling through).

If `Config` / `HttpResponse` import fails, that's a real signal — they're defined at module level in `stash_crawls_batch.py` and importable. Verify with `python -c "from stash_crawls_batch import Config, HttpResponse, process_crawl"`.

- [ ] **Step 3: Add `import socket` to module imports**

Edit `tools/stash_crawls_batch.py`. The T2 import block currently sits at lines 206–209:

```python
import signal
import urllib.error
import urllib.request
from dataclasses import dataclass
```

Add `import socket` so it becomes:

```python
import signal
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
```

(Alphabetical order; matches stdlib convention used elsewhere in the file.)

- [ ] **Step 4: Bump the two timeout constants**

Edit `tools/stash_crawls_batch.py` lines 150–152:

```python
# Per-crawl timeout knobs (max 60 min, min 10 min, 3 min per GB)
_TIMEOUT_MIN = 600
_TIMEOUT_MAX = 3600
_TIMEOUT_PER_GB = 180
```

Replace with:

```python
# Per-crawl timeout knobs (max 120 min, min 10 min, 5 min per GB).
# Calibrated against worst-case server wall-clock for 20 GB crawl
# (tar + integrity + cleanup ~25-100 min on /mnt/data at 95% used).
# See docs/superpowers/specs/2026-05-23-stash-script-poll-fallthrough-design.md § 4.
_TIMEOUT_MIN = 600
_TIMEOUT_MAX = 7200
_TIMEOUT_PER_GB = 300
```

- [ ] **Step 5: Rewrite the `process_crawl` POST/retry/poll block**

The current `process_crawl` body lives at `tools/stash_crawls_batch.py:260-317`. Replace the entire function with the version below. Behavioural changes only: imports, constants, and the wait_for_disk + URL construction + final poll loop are unchanged from the current implementation; only the POST + retry block and the poll-log/done-log/failed-detail strings carry `fell_through`.

```python
def process_crawl(
    size_bytes: int,
    crawl_id: str,
    state: "BatchState",
    cfg: Config,
) -> None:
    """Stash one crawl: disk-guard, POST, poll, record.

    POST exception (timeout/URLError/OSError) is treated as "server may
    still be tarring (see _LockHeartbeat); fall through to completion
    poll". Persisted 5xx is treated the same way. The completion poll
    remains the source of truth — it decides done/failed via the
    local-tar-absent + GCS-present and dead-letter signals.
    """
    wait_for_disk(size_bytes, cfg.disk_target)

    url = f"{cfg.crawler_base_url}/stash/{crawl_id}"
    logger.info("POST %s (size=%.2fG)", url, size_bytes / 1024**3)

    fell_through = False
    try:
        resp = http_post(url, cfg.http_timeout_seconds)
    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as e:
        logger.warning(
            "POST %s did not return within %ds (%s). Server likely still tarring "
            "(see _LockHeartbeat). Falling through to completion poll.",
            crawl_id,
            cfg.http_timeout_seconds,
            e.__class__.__name__,
        )
        resp = None
        fell_through = True

    if resp is not None:
        if resp.status_code == 404:
            logger.warning("404 on %s — Redis lost job", crawl_id)
            state.append("notfound", crawl_id)
            return
        if resp.status_code == 409:
            logger.info("409 on %s — already stashed/archived", crawl_id)
            state.append("skipped", crawl_id, resp.text[:200].replace("\n", " "))
            return
        if resp.status_code == 400:
            logger.warning("400 on %s — wrong status", crawl_id)
            state.append("invalid", crawl_id, resp.text[:200].replace("\n", " "))
            return
        if resp.status_code >= 500:
            logger.warning("5xx on %s — retrying in 30s", crawl_id)
            time.sleep(30)
            try:
                resp = http_post(url, cfg.http_timeout_seconds)
            except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as e:
                logger.warning(
                    "Retry POST %s also did not return (%s). Falling through to completion poll.",
                    crawl_id,
                    e.__class__.__name__,
                )
                resp = None
                fell_through = True
            if resp is not None and resp.status_code >= 500:
                logger.warning(
                    "5xx persisted on %s — server may still be processing; "
                    "falling through to completion poll.",
                    crawl_id,
                )
                resp = None
                fell_through = True
        elif resp.status_code != 202:
            detail = f"unexpected {resp.status_code}: {resp.text[:200]}".replace("\n", " ")
            state.append("failed", crawl_id, detail)
            raise FatalError(f"Unexpected {resp.status_code} on {crawl_id}")

    timeout_s = per_crawl_timeout(size_bytes)
    deadline = time.time() + timeout_s
    logger.info(
        "Polling completion for %s (timeout=%ds, fell_through=%s)",
        crawl_id,
        timeout_s,
        fell_through,
    )

    while time.time() < deadline:
        if _stop_requested:
            state.append("failed", crawl_id, f"interrupted during poll (fell_through={fell_through})")
            raise FatalError(f"Interrupted while polling {crawl_id}")
        if dead_letter_exists(crawl_id, cfg.stash_dead_letter_dir):
            state.append("failed", crawl_id, f"dead_letter (fell_through={fell_through})")
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

- [ ] **Step 6: Run tests to verify they pass (green)**

Run:
```
python -m pytest tools/test_stash_crawls_batch.py -v
```

Expected output:
```
tools/test_stash_crawls_batch.py::test_parse_size_units PASSED
tools/test_stash_crawls_batch.py::test_parse_line_skips_markers PASSED
tools/test_stash_crawls_batch.py::test_parse_line_handles_blank_and_malformed PASSED
tools/test_stash_crawls_batch.py::test_load_work_list_rejects_duplicates PASSED
tools/test_stash_crawls_batch.py::test_load_work_list_filters_done_and_sorts PASSED
tools/test_stash_crawls_batch.py::test_batch_state_append_done_and_classes PASSED
tools/test_stash_crawls_batch.py::test_batch_state_loads_existing_done PASSED
tools/test_stash_crawls_batch.py::test_per_crawl_timeout_formula PASSED
tools/test_stash_crawls_batch.py::test_disk_guard_waits_then_passes PASSED
tools/test_stash_crawls_batch.py::test_disk_guard_aborts_on_timeout PASSED
tools/test_stash_crawls_batch.py::test_process_crawl_post_timeout_falls_through_to_poll PASSED
tools/test_stash_crawls_batch.py::test_process_crawl_5xx_persisted_falls_through_to_poll PASSED
tools/test_stash_crawls_batch.py::test_process_crawl_fall_through_times_out_marks_failed PASSED

13 passed
```


- [ ] **Step 7: Smoke-test manually (optional but recommended before live batch resume)**

Pick one already-failed crawl from `tools/ids_dspi_9_trier_taille.txt` (e.g. `2347` which timed out earlier — server-side state may already be `stashed`; expect 409 → `skipped`). With a short HTTP timeout to force fall-through:

```
set -a; source .env; set +a
STASH_GCS_BUCKET="$GCS_BUCKET_NAME" \
HTTP_TIMEOUT_SECONDS=1 \
python3 tools/stash_crawls_batch.py /tmp/smoke.txt
```

Where `/tmp/smoke.txt` contains a single line for one small pending ID. Expected log sequence:
1. `POST http://localhost:8500/.../stash/<id> (size=...)`
2. `POST <id> did not return within 1s (TimeoutError). Server likely still tarring …`
3. `Polling completion for <id> (timeout=...s, fell_through=True)`
4. Either: `DONE <id> (fell_through=True)` within ~10 min for a small crawl, OR `409` (if server already had it stashed) — both acceptable.

This is operator-side verification, not a unit-test gate; skip if the unit tests pass and you trust the diff.

- [ ] **Step 8: Commit**

Confirm changed files:
```
git status --short
```
Expected:
```
 M tools/stash_crawls_batch.py
 M tools/test_stash_crawls_batch.py
```

Write the commit message to `.git/COMMIT_EDITMSG` via the Write tool (UTF-8 — Windows shell heredoc strips accents) using the bilingual EN/FR template below, then commit:

```
git add tools/stash_crawls_batch.py tools/test_stash_crawls_batch.py
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

Commit message body:

```
fix(stash-batch): fall through to poll on POST timeout / 5xx; bump per-crawl ceiling

EN:
process_crawl now treats POST TimeoutError / URLError / OSError and
persisted 5xx as "server still tarring (per _LockHeartbeat); fall
through to completion poll" instead of raising FatalError. The poll
loop remains the source of truth via local-tar-absent + GCS-present
and dead-letter signals. Per-crawl deadline ceiling raised 60->120
min, per-GB factor 3->5 min/GB to fit observed 20 GB worst-case
(~25-100 min server wall-clock). fell_through flag threaded into
poll log, done log, and failed-state detail for operator audit. 3
new unit tests + 1 updated; total 13 tests green.

FR:
process_crawl traite maintenant les erreurs TimeoutError / URLError /
OSError du POST et les 5xx persistants comme "le serveur est encore
en train de creer l'archive (cf. _LockHeartbeat); basculer vers le
sondage de completion" au lieu de lever FatalError. La boucle de
sondage reste l'autorite via les signaux archive-locale-absente +
GCS-presente et dead-letter. Plafond du deadline par crawl releve
60->120 min, facteur par Go 3->5 min/Go pour couvrir le pire cas
observe a 20 Go (~25-100 min cote serveur). Indicateur fell_through
propage dans le log de sondage, le log DONE, et le detail d'etat
failed pour audit operateur. 3 nouveaux tests unitaires + 1 mis a
jour ; 13 tests verts au total.
```

Verify:
```
git log -1 --oneline
```

```json:metadata
{"files":["tools/stash_crawls_batch.py","tools/test_stash_crawls_batch.py"],"verifyCommand":"python -m pytest tools/test_stash_crawls_batch.py -v","acceptanceCriteria":["socket imported","_TIMEOUT_MAX=7200","_TIMEOUT_PER_GB=300","process_crawl catches TimeoutError/socket.timeout/URLError/OSError on first POST","process_crawl falls through on persisted 5xx after one 30s retry","FatalError still raised on unexpected non-202 2xx / dead-letter / stop / poll deadline","fell_through threaded into poll/done/failed-state strings","test_per_crawl_timeout_formula updated for new constants","3 new tests added","13 tests green"]}
```

---

## Self-Review

**1. Spec coverage:**

| Spec § acceptance item | Plan task covering it |
|---|---|
| § 11 catches `(TimeoutError, socket.timeout, urllib.error.URLError, OSError)` from http_post | Task 1, Step 5 (first try/except) + acceptance criterion |
| § 11 falls through on persisted 5xx after one 30s retry | Task 1, Step 5 (5xx branch) + acceptance criterion |
| § 11 still raises FatalError on unexpected 2xx / dead-letter / poll deadline / SIGINT mid-poll | Task 1, Step 5 (last `elif` + poll-loop branches) + acceptance criterion |
| § 11 `_TIMEOUT_MAX=7200` | Task 1, Step 4 |
| § 11 `_TIMEOUT_PER_GB=300` | Task 1, Step 4 |
| § 11 `fell_through` flag threaded into logs + failed-state detail | Task 1, Step 5 (every log/state.append site uses the flag) |
| § 11 3 new unit tests green | Task 1, Step 1 (the three appended tests) |
| § 11 updated `test_per_crawl_timeout_formula` green | Task 1, Step 1 (rewritten body) |
| § 11 manual smoke succeeds | Task 1, Step 7 (operator-side, optional) |
| § 11 no server-side code change | Confirmed: Files table lists only `tools/` files |

All 10 acceptance items mapped.

**2. Placeholder scan:** No `TBD`, no `TODO`, no `similar to`, no "implement later". Every code step shows the actual code. Verify commands are concrete. Manual smoke step is explicitly marked optional.

**3. Type consistency:**
- `process_crawl` signature matches existing: `(size_bytes: int, crawl_id: str, state: "BatchState", cfg: Config) -> None`. Same as line 260 of the current file.
- `Config` dataclass fields used in `_cfg()` test helper match the dataclass definition at lines 226–235 of the current file: `crawler_base_url`, `stash_local_dir`, `stash_dead_letter_dir`, `stash_gcs_bucket`, `stash_gcs_prefix`, `disk_target`, `http_timeout_seconds`, `poll_interval_seconds`.
- `HttpResponse(status_code=..., text=...)` matches the dataclass at lines 238–241.
- `state.append("done"|"failed"|"skipped"|"invalid"|"notfound", crawl_id, [detail])` matches `BatchState.append` signature at line 120.
- `local_tar_exists / dead_letter_exists / gcs_tar_exists` signatures match lines 161–177.

**4. Internal test-count consistency:** Acceptance criteria, Step 6 expected output, and the verify command all reference 13 tests (10 existing + 3 new). Plan internally consistent.

---

## Task Persistence

Task persistence file written to `docs/superpowers/plans/2026-05-23-stash-script-poll-fallthrough.md.tasks.json` co-located with this plan.
