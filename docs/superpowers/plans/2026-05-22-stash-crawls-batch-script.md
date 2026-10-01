# Stash Crawls Batch Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tools/stash_crawls_batch.py` — a punctual Python 3 script that stashes a list of terminal crawls to GCS sequentially, respecting `/mnt/data` disk pressure (95% used / 67 GB free), with resume-via-state-file and graceful abort on failures.

**Architecture:** Single-file script under `tools/`. Reads a tab-delimited input file (`<size>\t<id>[ → marker]`), skips marked lines, sorts ascending, then for each remaining crawl: pre-flight disk guard → POST `/crawler/stash/{id}` → poll until local tar absent + GCS tar present → append to state file → next. Strict serial. SIGINT/SIGTERM cause graceful exit between crawl boundaries.

**Tech Stack:** Python 3.10+ stdlib only (`urllib.request`, `shutil.disk_usage`, `subprocess` for `gcloud`, `signal`, `logging`, `argparse`). No third-party HTTP client to keep zero-pip-deps on the VM. Tests via `pytest` (already in repo for crawler-service).

**Spec:** `docs/superpowers/specs/2026-05-22-stash-crawls-batch-script-design.md`

---

## Graphify post-commit hook — EDITMSG amend recipe

The graphify post-commit hook occasionally clobbers the commit subject line (~5–10% of commits in this repo). After each commit, run `git log -1 --format="%s"` to verify. If clobbered, amend immediately:

```bash
# Save intended message to a temp file before committing:
cat > /tmp/EDITMSG <<'EOF'
<intended subject>

<intended body line 1>
<intended body line 2>
EOF
git commit -F /tmp/EDITMSG

# Verify:
git log -1 --format="%s"

# If subject was rewritten by the hook, amend in place:
git commit --amend -F /tmp/EDITMSG --no-edit-hook 2>/dev/null \
  || git commit --amend -F /tmp/EDITMSG
git log -1 --format="%s"   # should match intended subject
```

Apply this recipe to every task in this plan. Replace `<intended subject>` / `<intended body>` with each task's commit message verbatim.

---

## File structure (locked in before tasks)

Single script + single test file, both under `tools/`:

```
tools/
  stash_crawls_batch.py            # CLI entry + all logic, ~350 LOC
  test_stash_crawls_batch.py       # 9 pytest unit tests
```

Module layout inside `stash_crawls_batch.py`:

```
─ Imports + module docstring
─ Constants block: defaults for all env-configurable knobs (SAFETY_MARGIN_BYTES, DISK_WAIT_MAX_SECONDS, POLL_INTERVAL_SECONDS, HTTP_TIMEOUT_SECONDS, default URLs/paths)
─ Logger setup (lazy — main() configures handlers based on input path)
─ FatalError exception class
─ parse_size(s)                                   ─┐  T0
─ parse_line(raw)                                  │
─ load_work_list(input_path, done_set)             │
─ class BatchState                                ─┘
─ per_crawl_timeout(size_bytes)                   ─┐  T1
─ local_tar_exists(crawl_id, stash_local_dir)      │
─ dead_letter_exists(crawl_id, dead_letter_dir)    │
─ gcs_tar_exists(crawl_id, bucket, prefix)         │
─ wait_for_disk(needed_bytes, disk_target)        ─┘
─ http_post(url, timeout)                         ─┐  T2
─ process_crawl(size_bytes, crawl_id, state, cfg) │
─ install_signal_handlers()                       ─┘
─ print_dry_run(work_list, cfg, done_count, ...)  ─┐  T3
─ print_summary(state, started_at)                 │
─ main()                                          ─┘
```

`cfg` is a frozen dataclass populated from env vars in `main()` and passed down — keeps signatures explicit, avoids module-level mutable state.

---

## Configuration dataclass (referenced by every task)

Define once in T2 (since it's first needed by `process_crawl`), used unchanged by T3. Pasted here for reference so all tasks use identical field names:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    crawler_base_url: str
    stash_local_dir: str
    stash_dead_letter_dir: str
    stash_gcs_bucket: str
    stash_gcs_prefix: str
    disk_target: str
    http_timeout_seconds: int
    poll_interval_seconds: int
```

Defaults (referenced in T3's `main()`):

| Field | Env var | Default |
|---|---|---|
| `crawler_base_url` | `CRAWLER_BASE_URL` | `http://localhost:8500/crawler` |
| `stash_local_dir` | `STASH_LOCAL_DIR` | `/app/stash` |
| `stash_dead_letter_dir` | `STASH_DEAD_LETTER_DIR` | `crawler_archives/dead_letter` |
| `stash_gcs_bucket` | `STASH_GCS_BUCKET` | *(required)* |
| `stash_gcs_prefix` | `STASH_GCS_PREFIX` | `stash` |
| `disk_target` | `DISK_TARGET` | `/mnt/data` |
| `http_timeout_seconds` | `HTTP_TIMEOUT_SECONDS` | `30` |
| `poll_interval_seconds` | `POLL_INTERVAL_SECONDS` | `10` |

---

## Task 0: Parser, size, and state helpers

**Goal:** Implement the parsing layer (`parse_size`, `parse_line`, `load_work_list`) and the `BatchState` class. Ships 6 unit tests.

**Files:**
- Create: `tools/stash_crawls_batch.py`
- Create: `tools/test_stash_crawls_batch.py`

**Acceptance Criteria:**
- [ ] `parse_size("106M")` → `111149056`. `parse_size("1.1G")` → `1181116006`. `parse_size("21G")` → `22548578304`. K/M/G/T units supported, decimal sizes supported.
- [ ] `parse_line("106M\t6511 → Done")` → `None` (skipped marker). `parse_line("139M\t6271")` → `(145752064, "6271")`. Blank line and malformed lines return `None`.
- [ ] `load_work_list` raises `FatalError` on duplicate IDs across the file.
- [ ] `load_work_list` filters out IDs present in the supplied done set.
- [ ] `load_work_list` returns the work list sorted ascending by size.
- [ ] `BatchState.append("done", "123")` appends `"123\n"` to `<input>.stash_done.txt` and updates the in-memory `done` set.
- [ ] `BatchState.append("skipped", "456", "reason")` appends `"456\treason\t<iso-timestamp>\n"` to `<input>.stash_skipped.txt`.
- [ ] `BatchState(input_path)` loads existing `<input>.stash_done.txt` into `done` set if the file already exists.

**Verify:** `pytest tools/test_stash_crawls_batch.py -v -k "parse or batch_state"` → 6 PASS

**Steps:**

- [ ] **Step 1: Create `tools/test_stash_crawls_batch.py` with the 6 tests (failing)**

```python
# tools/test_stash_crawls_batch.py
"""Unit tests for tools/stash_crawls_batch.py."""
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from stash_crawls_batch import (  # noqa: E402
    BatchState,
    FatalError,
    load_work_list,
    parse_line,
    parse_size,
)


def test_parse_size_units():
    assert parse_size("106M") == 106 * 1024**2
    assert parse_size("1.1G") == int(1.1 * 1024**3)
    assert parse_size("21G") == 21 * 1024**3
    assert parse_size("500K") == 500 * 1024
    assert parse_size("2T") == 2 * 1024**4


def test_parse_line_skips_markers():
    assert parse_line("106M\t6511 → Done\n") is None
    assert parse_line("21G\t5821 → Supprimé\n") is None
    assert parse_line("5.2G\t6434 → Done") is None


def test_parse_line_handles_blank_and_malformed():
    assert parse_line("") is None
    assert parse_line("\n") is None
    assert parse_line("no-tab-here 6271\n") is None
    assert parse_line("106M\tabc\n") is None  # non-digit id
    # Valid:
    assert parse_line("139M\t6271\n") == (139 * 1024**2, "6271")


def test_load_work_list_rejects_duplicates(tmp_path):
    input_file = tmp_path / "ids.txt"
    input_file.write_text("139M\t6271\n142M\t6271\n", encoding="utf-8")
    with pytest.raises(FatalError, match="Duplicate"):
        load_work_list(input_file, done=set())


def test_load_work_list_filters_done_and_sorts(tmp_path):
    input_file = tmp_path / "ids.txt"
    input_file.write_text(
        "20G\t6080\n"
        "106M\t6511 → Done\n"
        "139M\t6271\n"
        "142M\t6299\n"
        "17G\t5621\n",
        encoding="utf-8",
    )
    work = load_work_list(input_file, done={"6299"})
    # 6511 skipped (marker), 6299 skipped (done), remaining sorted ascending:
    assert [crawl_id for _, crawl_id in work] == ["6271", "5621", "6080"]


def test_batch_state_append_done_and_classes(tmp_path):
    input_file = tmp_path / "ids.txt"
    input_file.write_text("139M\t6271\n", encoding="utf-8")
    state = BatchState(input_file)

    state.append("done", "6271")
    state.append("skipped", "6299", "409 already stashed")
    state.append("notfound", "9999")

    done_lines = (tmp_path / "ids.txt.stash_done.txt").read_text().splitlines()
    assert done_lines == ["6271"]
    assert "6271" in state.done

    skipped = (tmp_path / "ids.txt.stash_skipped.txt").read_text()
    assert skipped.startswith("6299\t409 already stashed\t")  # timestamp follows
    assert len(skipped.strip().split("\t")) == 3

    notfound = (tmp_path / "ids.txt.stash_notfound.txt").read_text()
    assert notfound.startswith("9999\t")


def test_batch_state_loads_existing_done(tmp_path):
    input_file = tmp_path / "ids.txt"
    input_file.write_text("139M\t6271\n", encoding="utf-8")
    (tmp_path / "ids.txt.stash_done.txt").write_text("100\n200\n300\n")

    state = BatchState(input_file)
    assert state.done == {"100", "200", "300"}
```

- [ ] **Step 2: Run tests — confirm failure**

Run: `pytest tools/test_stash_crawls_batch.py -v -k "parse or batch_state or load_work_list"`
Expected: ImportError (module doesn't exist yet) or `ModuleNotFoundError`.

- [ ] **Step 3: Create `tools/stash_crawls_batch.py` with parser + state**

```python
# tools/stash_crawls_batch.py
"""Sequentially stash a list of terminal crawls to GCS.

Reads an input file of the form:
    <size>\\t<crawl_id>[ → <marker>]

Lines with a marker (anything containing the "→" arrow) are skipped.
Remaining IDs are stashed one at a time via POST /crawler/stash/{id},
respecting disk-pressure on /mnt/data and verifying GCS arrival before
moving to the next crawl. Resume-safe via per-class state files written
next to the input file.

Usage:
    python tools/stash_crawls_batch.py <input-file> [--dry-run]
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stash_crawls_batch")


class FatalError(Exception):
    """Aborts the batch run; written to <input>.stash_failed.txt if attributable to a crawl."""


_SIZE_MULT = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


def parse_size(s: str) -> int:
    """Convert a human-readable size like '106M' or '1.1G' to bytes."""
    s = s.strip()
    if not s:
        raise ValueError("empty size string")
    unit = s[-1].upper()
    if unit not in _SIZE_MULT:
        raise ValueError(f"unknown size unit: {unit!r}")
    num = float(s[:-1])
    return int(num * _SIZE_MULT[unit])


def parse_line(raw: str) -> tuple[int, str] | None:
    """Parse one line of the input file.

    Returns (size_bytes, crawl_id) for processable lines, or None for:
    - blank lines
    - lines containing "→" (marker present, intentionally skipped)
    - malformed lines (no tab, non-digit id, unknown size unit)
    """
    line = raw.rstrip()
    if not line:
        return None
    parts = line.split("\t", 1)
    if len(parts) != 2:
        return None
    size_str, rest = parts
    if "→" in rest:
        return None
    crawl_id = rest.strip()
    if not crawl_id.isdigit():
        return None
    try:
        return parse_size(size_str), crawl_id
    except ValueError:
        return None


def load_work_list(input_path: Path, done: set[str]) -> list[tuple[int, str]]:
    """Parse the input file, drop markers, drop done IDs, sort ascending by size.

    Raises FatalError if duplicate IDs appear in the input.
    """
    text = input_path.read_text(encoding="utf-8")
    seen: dict[str, int] = {}
    for line_no, raw in enumerate(text.splitlines(keepends=True), start=1):
        result = parse_line(raw)
        if result is None:
            continue
        _, crawl_id = result
        if crawl_id in seen:
            raise FatalError(
                f"Duplicate crawl_id '{crawl_id}' at line {line_no} "
                f"(first seen at line {seen[crawl_id]})"
            )
        seen[crawl_id] = line_no

    work: list[tuple[int, str]] = []
    for raw in text.splitlines(keepends=True):
        result = parse_line(raw)
        if result is None:
            continue
        size_bytes, crawl_id = result
        if crawl_id in done:
            continue
        work.append((size_bytes, crawl_id))

    work.sort(key=lambda t: t[0])
    return work


class BatchState:
    """Append-only per-class state files next to the input file."""

    def __init__(self, input_path: Path) -> None:
        self.input_path = input_path
        self.done_path = Path(f"{input_path}.stash_done.txt")
        self.done: set[str] = self._load_done()

    def _load_done(self) -> set[str]:
        if not self.done_path.exists():
            return set()
        return {
            line.strip()
            for line in self.done_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    def append(self, klass: str, crawl_id: str, detail: str = "") -> None:
        path = Path(f"{self.input_path}.stash_{klass}.txt")
        if klass == "done":
            line = f"{crawl_id}\n"
        else:
            ts = datetime.utcnow().isoformat(timespec="seconds")
            if detail:
                line = f"{crawl_id}\t{detail}\t{ts}\n"
            else:
                line = f"{crawl_id}\t{ts}\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
        if klass == "done":
            self.done.add(crawl_id)
```

- [ ] **Step 4: Run tests — confirm pass**

Run: `pytest tools/test_stash_crawls_batch.py -v -k "parse or batch_state or load_work_list"`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
cat > /tmp/EDITMSG <<'EOF'
feat(tools): parser + state helpers for stash_crawls_batch script

[EN]
First slice of tools/stash_crawls_batch.py: parse_size for K/M/G/T
units, parse_line that drops blanks/markers/malformed entries,
load_work_list that rejects duplicate IDs and filters out already-
done crawls, and a BatchState class that appends to per-class state
files (stash_done.txt, stash_skipped.txt, etc.) next to the input
file. 6 unit tests under tools/test_stash_crawls_batch.py cover the
parser edge cases, duplicate rejection, ordering, and state-file
write + reload.

[FR]
Première tranche de tools/stash_crawls_batch.py : parse_size pour
les unités K/M/G/T, parse_line qui élimine les lignes vides/marquées
/mal formées, load_work_list qui rejette les ID en double et filtre
les crawls déjà traités, et une classe BatchState qui écrit en append
dans des fichiers d'état par classe (stash_done.txt, stash_skipped.txt,
etc.) à côté du fichier d'entrée. 6 tests unitaires dans
tools/test_stash_crawls_batch.py couvrent les cas limites du parseur,
le rejet des doublons, le tri, et l'écriture + rechargement du
fichier d'état.
EOF
git add tools/stash_crawls_batch.py tools/test_stash_crawls_batch.py
git commit -F /tmp/EDITMSG
git log -1 --format="%s"   # verify subject; if clobbered, see EDITMSG amend recipe at top
```

---

## Task 1: Disk guard, timeout, and existence checks

**Goal:** Add `per_crawl_timeout`, `local_tar_exists`, `dead_letter_exists`, `gcs_tar_exists`, and `wait_for_disk`. Ships 3 unit tests.

**Files:**
- Modify: `tools/stash_crawls_batch.py` (append after `BatchState`)
- Modify: `tools/test_stash_crawls_batch.py` (append 3 tests)

**Acceptance Criteria:**
- [ ] `per_crawl_timeout(100 * 1024**2)` → `600` (floor 10 min).
- [ ] `per_crawl_timeout(20 * 1024**3)` → `3600` (ceiling 60 min).
- [ ] `per_crawl_timeout(5 * 1024**3)` → `900` (3 min/GB middle).
- [ ] `wait_for_disk` returns when `shutil.disk_usage(target).free` ≥ `needed + 10 GB`.
- [ ] `wait_for_disk` raises `FatalError` when `DISK_WAIT_MAX_SECONDS` elapses with insufficient free.
- [ ] `local_tar_exists(crawl_id, dir)` proxies `os.path.exists(f"{dir}/{crawl_id}.tar.gz")`.
- [ ] `dead_letter_exists(crawl_id, dir)` proxies `os.path.exists(f"{dir}/{crawl_id}.tar.gz")`.
- [ ] `gcs_tar_exists(crawl_id, bucket, prefix)` returns True iff `gcloud storage ls gs://{bucket}/{prefix}/{crawl_id}.tar.gz` exits 0.

**Verify:** `pytest tools/test_stash_crawls_batch.py -v` → 9 PASS

**Steps:**

- [ ] **Step 1: Add 3 failing tests to `tools/test_stash_crawls_batch.py`**

```python
# (append to tools/test_stash_crawls_batch.py)
from unittest.mock import patch
from collections import namedtuple

from stash_crawls_batch import (  # noqa: E402
    per_crawl_timeout,
    wait_for_disk,
)


def test_per_crawl_timeout_formula():
    assert per_crawl_timeout(100 * 1024**2) == 600         # 0.1 GB → floor 10 min
    assert per_crawl_timeout(1 * 1024**3) == 600           # 1 GB → still floor (180s < 600s)
    assert per_crawl_timeout(5 * 1024**3) == 900           # 5 GB → 5*180 = 900s
    assert per_crawl_timeout(20 * 1024**3) == 3600         # 20 GB → ceiling 60 min
    assert per_crawl_timeout(100 * 1024**3) == 3600        # 100 GB → ceiling 60 min


_Usage = namedtuple("_Usage", ["total", "used", "free"])


def test_disk_guard_waits_then_passes(monkeypatch):
    calls = {"n": 0}

    def fake_usage(_target):
        calls["n"] += 1
        if calls["n"] < 3:
            return _Usage(0, 0, 5 * 1024**3)          # below threshold first 2 calls
        return _Usage(0, 0, 50 * 1024**3)             # passes on 3rd call

    monkeypatch.setattr("stash_crawls_batch.shutil.disk_usage", fake_usage)
    monkeypatch.setattr("stash_crawls_batch.time.sleep", lambda _s: None)

    wait_for_disk(needed_bytes=10 * 1024**3, disk_target="/mnt/data")
    assert calls["n"] == 3


def test_disk_guard_aborts_on_timeout(monkeypatch):
    monkeypatch.setattr(
        "stash_crawls_batch.shutil.disk_usage",
        lambda _t: _Usage(0, 0, 1 * 1024**3),         # always insufficient
    )
    # Make time appear to leap past the deadline on the first sleep:
    t = {"now": 0.0}

    def fake_time():
        return t["now"]

    def fake_sleep(_s):
        t["now"] += 10_000  # jump 10000s ahead of any deadline

    monkeypatch.setattr("stash_crawls_batch.time.time", fake_time)
    monkeypatch.setattr("stash_crawls_batch.time.sleep", fake_sleep)

    with pytest.raises(FatalError, match="Disk free"):
        wait_for_disk(needed_bytes=10 * 1024**3, disk_target="/mnt/data")
```

- [ ] **Step 2: Run tests — confirm failure**

Run: `pytest tools/test_stash_crawls_batch.py -v -k "per_crawl_timeout or disk_guard"`
Expected: ImportError on `per_crawl_timeout`, `wait_for_disk` (not defined yet).

- [ ] **Step 3: Append helpers to `tools/stash_crawls_batch.py`**

```python
# (append to tools/stash_crawls_batch.py after BatchState class)
import os
import shutil
import subprocess
import time

# Disk guard knobs
SAFETY_MARGIN_BYTES = 10 * 1024**3        # 10 GB headroom on top of source size
DISK_WAIT_MAX_SECONDS = 30 * 60           # 30 min total wait per crawl
DISK_WAIT_INTERVAL = 60                   # poll every 60s

# Per-crawl timeout knobs (max 60 min, min 10 min, 3 min per GB)
_TIMEOUT_MIN = 600
_TIMEOUT_MAX = 3600
_TIMEOUT_PER_GB = 180


def per_crawl_timeout(size_bytes: int) -> int:
    """Upload-completion timeout in seconds, scaled by source size."""
    size_g = size_bytes / 1024**3
    return int(min(_TIMEOUT_MAX, max(_TIMEOUT_MIN, size_g * _TIMEOUT_PER_GB)))


def local_tar_exists(crawl_id: str, stash_local_dir: str) -> bool:
    return os.path.exists(os.path.join(stash_local_dir, f"{crawl_id}.tar.gz"))


def dead_letter_exists(crawl_id: str, dead_letter_dir: str) -> bool:
    return os.path.exists(os.path.join(dead_letter_dir, f"{crawl_id}.tar.gz"))


def gcs_tar_exists(crawl_id: str, bucket: str, prefix: str) -> bool:
    """True iff `gcloud storage ls gs://{bucket}/{prefix}/{crawl_id}.tar.gz` exits 0."""
    uri = f"gs://{bucket}/{prefix}/{crawl_id}.tar.gz"
    result = subprocess.run(
        ["gcloud", "storage", "ls", uri],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def wait_for_disk(needed_bytes: int, disk_target: str) -> None:
    """Block until free space on `disk_target` ≥ needed_bytes + 10 GB, or raise."""
    threshold = needed_bytes + SAFETY_MARGIN_BYTES
    deadline = time.time() + DISK_WAIT_MAX_SECONDS
    while True:
        free = shutil.disk_usage(disk_target).free
        if free >= threshold:
            return
        if time.time() > deadline:
            raise FatalError(
                f"Disk free {free / 1024**3:.1f} GB < needed "
                f"{threshold / 1024**3:.1f} GB after {DISK_WAIT_MAX_SECONDS}s"
            )
        logger.warning(
            "Disk free %.1f GB < needed %.1f GB; sleeping %ds",
            free / 1024**3,
            threshold / 1024**3,
            DISK_WAIT_INTERVAL,
        )
        time.sleep(DISK_WAIT_INTERVAL)
```

- [ ] **Step 4: Run all tests**

Run: `pytest tools/test_stash_crawls_batch.py -v`
Expected: 9 PASS (6 from T0 + 3 from T1).

- [ ] **Step 5: Commit**

```bash
cat > /tmp/EDITMSG <<'EOF'
feat(tools): disk guard + timeout + existence checks for stash batch

[EN]
Adds the second helper layer to tools/stash_crawls_batch.py:
per_crawl_timeout (10-60 min, scaled at 3 min/GB), local_tar_exists
+ dead_letter_exists (os.path probes), gcs_tar_exists (gcloud storage
ls), and wait_for_disk which blocks until df free ≥ size + 10 GB
safety margin or aborts after 30 min. 3 new unit tests cover the
timeout formula and disk-guard wait-then-pass / timeout-then-abort
paths via monkeypatched shutil.disk_usage and time. 9/9 tests pass.

[FR]
Ajoute la deuxième couche de helpers à tools/stash_crawls_batch.py :
per_crawl_timeout (10-60 min, 3 min/Go), local_tar_exists +
dead_letter_exists (sondes os.path), gcs_tar_exists (gcloud storage
ls), et wait_for_disk qui bloque jusqu'à df libre ≥ taille + 10 Go
de marge ou abandonne après 30 min. 3 nouveaux tests unitaires
couvrent la formule de timeout et les chemins attente-puis-passage /
timeout-puis-abandon du garde-disque via monkeypatch sur
shutil.disk_usage et time. 9/9 tests passent.
EOF
git add tools/stash_crawls_batch.py tools/test_stash_crawls_batch.py
git commit -F /tmp/EDITMSG
git log -1 --format="%s"
```

---

## Task 2: HTTP post + per-crawl process loop + signals

**Goal:** Implement the `Config` dataclass, `http_post`, `process_crawl`, and signal handling. No new tests — this layer is exercised by manual smoke (Task 3 acceptance).

**Files:**
- Modify: `tools/stash_crawls_batch.py` (append after disk-guard helpers)

**Acceptance Criteria:**
- [ ] `Config` frozen dataclass with the 8 fields listed in the "Configuration dataclass" section above.
- [ ] `http_post(url, timeout)` uses `urllib.request` (no third-party deps), returns an object with `.status_code: int` and `.text: str`.
- [ ] `process_crawl` calls `wait_for_disk` → `http_post` → parses 202/400/404/409/5xx per spec → polls every `cfg.poll_interval_seconds` until `local_tar_exists` is False AND `gcs_tar_exists` is True → appends `("done", crawl_id)` to state.
- [ ] Dead-letter file detection during poll raises `FatalError`.
- [ ] 5xx response retries once after 30s, then raises `FatalError`.
- [ ] Per-crawl timeout from `per_crawl_timeout(size_bytes)` triggers `FatalError` with `"timeout"`.
- [ ] `install_signal_handlers()` registers SIGINT and SIGTERM to set a module-level `_stop_requested` flag; `process_crawl` checks the flag between poll iterations and raises `FatalError("interrupted")` cleanly when set.

**Verify:** `python -c "import tools.stash_crawls_batch as m; m.install_signal_handlers(); print('ok')"` → prints `ok`. And `pytest tools/test_stash_crawls_batch.py -v` → still 9 PASS (no regression).

**Steps:**

- [ ] **Step 1: Append code to `tools/stash_crawls_batch.py`**

```python
# (append to tools/stash_crawls_batch.py after wait_for_disk)
import signal
import urllib.error
import urllib.request
from dataclasses import dataclass

_stop_requested = False


def install_signal_handlers() -> None:
    """SIGINT/SIGTERM set _stop_requested; process_crawl checks it between polls."""
    def _handler(signum, _frame):
        global _stop_requested
        _stop_requested = True
        logger.warning("Signal %s received — will exit after current crawl boundary", signum)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


@dataclass(frozen=True)
class Config:
    crawler_base_url: str
    stash_local_dir: str
    stash_dead_letter_dir: str
    stash_gcs_bucket: str
    stash_gcs_prefix: str
    disk_target: str
    http_timeout_seconds: int
    poll_interval_seconds: int


@dataclass
class HttpResponse:
    status_code: int
    text: str


def http_post(url: str, timeout: int) -> HttpResponse:
    """POST with empty body. stdlib only — urllib.request.

    Returns HttpResponse with .status_code and .text. HTTP errors (4xx/5xx) are
    captured as HTTPError and converted into HttpResponse rather than raised.
    """
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return HttpResponse(status_code=resp.status, text=body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return HttpResponse(status_code=e.code, text=body)


def process_crawl(
    size_bytes: int,
    crawl_id: str,
    state: BatchState,
    cfg: Config,
) -> None:
    """Stash one crawl: disk-guard, POST, poll, record."""
    wait_for_disk(size_bytes, cfg.disk_target)

    url = f"{cfg.crawler_base_url}/stash/{crawl_id}"
    logger.info("POST %s (size=%.2fG)", url, size_bytes / 1024**3)
    resp = http_post(url, cfg.http_timeout_seconds)

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
        resp = http_post(url, cfg.http_timeout_seconds)
        if resp.status_code >= 500:
            detail = f"5xx persisted: {resp.text[:200]}".replace("\n", " ")
            state.append("failed", crawl_id, detail)
            raise FatalError(f"5xx persisted on {crawl_id}")
    if resp.status_code != 202:
        detail = f"unexpected {resp.status_code}: {resp.text[:200]}".replace("\n", " ")
        state.append("failed", crawl_id, detail)
        raise FatalError(f"Unexpected {resp.status_code} on {crawl_id}")

    timeout_s = per_crawl_timeout(size_bytes)
    deadline = time.time() + timeout_s
    logger.info("Polling completion for %s (timeout=%ds)", crawl_id, timeout_s)

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
                logger.info("DONE %s", crawl_id)
                return
        time.sleep(cfg.poll_interval_seconds)

    state.append("failed", crawl_id, f"timeout after {timeout_s}s")
    raise FatalError(f"Timeout waiting for {crawl_id} ({timeout_s}s)")
```

- [ ] **Step 2: Verify import + no test regression**

Run: `python -c "from tools.stash_crawls_batch import install_signal_handlers, process_crawl, Config, http_post; print('ok')"`
Expected: `ok`

Run: `pytest tools/test_stash_crawls_batch.py -v`
Expected: 9 PASS (unchanged from T1 — no new tests added by T2).

- [ ] **Step 3: Commit**

```bash
cat > /tmp/EDITMSG <<'EOF'
feat(tools): per-crawl process loop + http_post + signals for stash batch

[EN]
Adds the orchestration layer to tools/stash_crawls_batch.py: frozen
Config dataclass that captures all 8 env-driven knobs, an
urllib.request-based http_post (stdlib only, no pip deps), a
process_crawl function that runs the full per-crawl pipeline (disk
guard, POST, parse 202/400/404/409/5xx, poll until local tar absent
+ GCS tar present, abort on dead-letter or timeout), and signal
handlers that set a module-level flag checked between poll iterations
so SIGINT/SIGTERM produce a clean exit between crawl boundaries. No
new unit tests at this layer — exercised by the smoke run from T3.

[FR]
Ajoute la couche d'orchestration à tools/stash_crawls_batch.py :
dataclass Config frozen qui capture les 8 réglages env, un http_post
basé sur urllib.request (stdlib seulement, zéro dep pip), une
fonction process_crawl qui exécute le pipeline complet par crawl
(garde disque, POST, parsing 202/400/404/409/5xx, poll jusqu'à tar
local absent + tar GCS présent, abandon sur dead-letter ou timeout),
et des handlers de signaux qui activent un flag module vérifié entre
les itérations de poll afin que SIGINT/SIGTERM produisent une sortie
propre aux frontières des crawls. Pas de nouveau test unitaire à
cette couche — couverte par le smoke run de T3.
EOF
git add tools/stash_crawls_batch.py
git commit -F /tmp/EDITMSG
git log -1 --format="%s"
```

---

## Task 3: CLI entry + dry-run + summary

**Goal:** Wire up `main()` with argparse, env-var loading, dry-run rendering, real-run loop, and summary printout. Manual smoke validates the integration.

**Files:**
- Modify: `tools/stash_crawls_batch.py` (append `print_dry_run`, `print_summary`, `main`, and `if __name__ == "__main__"` guard)

**Acceptance Criteria:**
- [ ] `python tools/stash_crawls_batch.py --help` prints usage with `<input-file>` positional + `--dry-run` flag.
- [ ] Running without `STASH_GCS_BUCKET` env var exits with code 2 and the message `"STASH_GCS_BUCKET environment variable is required"` printed to stderr before any work.
- [ ] `--dry-run` prints the parsed plan (skipped count, resume count, work list with computed timeouts, config summary, current disk free) and exits 0 without making any HTTP or `gcloud` calls.
- [ ] Real run iterates the work list, calls `process_crawl` for each, catches `FatalError` to print the summary and exit 1, and exits 0 on full success.
- [ ] On any exit (success, fatal, signal), prints a summary block: processed count, per-class counts, elapsed time.
- [ ] Logger writes to stdout AND to `<input>.stash_run.log` (append mode).

**Verify:**

1. Help: `python tools/stash_crawls_batch.py --help` → exit 0.
2. Missing bucket: `STASH_GCS_BUCKET= python tools/stash_crawls_batch.py tools/test_stash_crawls_batch.py` → exit 2, stderr matches expected string.
3. Dry run on a 3-line fixture: `STASH_GCS_BUCKET=fake python tools/stash_crawls_batch.py /tmp/smoke.txt --dry-run` → exit 0, plan printed.
4. Unit tests still green: `pytest tools/test_stash_crawls_batch.py -v` → 9 PASS.

**Manual smoke (post-merge, on server VM):** Operator creates `temp/smoke.txt` with the 2 smallest pending IDs (`6271 139M`, `6299 142M` tab-separated), exports env vars, runs `python tools/stash_crawls_batch.py temp/smoke.txt`, verifies `temp/smoke.txt.stash_done.txt` contains both IDs and `gs://{bucket}/stash/{6271,6299}.tar.gz` exist.

**Steps:**

- [ ] **Step 1: Append `main` + dry-run + summary to `tools/stash_crawls_batch.py`**

```python
# (append to tools/stash_crawls_batch.py after process_crawl)
import argparse
import sys


def print_dry_run(
    work_list: list[tuple[int, str]],
    cfg: Config,
    input_path: Path,
    skipped_count: int,
    done_count: int,
) -> None:
    total_bytes = sum(s for s, _ in work_list)
    free_now = shutil.disk_usage(cfg.disk_target).free
    print("=== DRY RUN ===")
    print(f"Input:      {input_path}")
    print(f"Skipped:    {skipped_count} IDs with markers")
    print(f"Resume:     {done_count} IDs in stash_done.txt")
    print(f"To process: {len(work_list)} IDs, total ~{total_bytes / 1024**3:.1f} GB")
    print()
    print("Order (ascending by size):")
    for i, (size_bytes, crawl_id) in enumerate(work_list, start=1):
        size_h = (
            f"{size_bytes / 1024**3:.1f}G"
            if size_bytes >= 1024**3
            else f"{size_bytes / 1024**2:.0f}M"
        )
        print(f"  {i:>4}. {crawl_id:<10} {size_h:>7}    timeout={per_crawl_timeout(size_bytes)}s")
    print()
    print("Config:")
    print(f"  CRAWLER_BASE_URL:        {cfg.crawler_base_url}")
    print(f"  STASH_LOCAL_DIR:         {cfg.stash_local_dir}")
    print(f"  STASH_DEAD_LETTER_DIR:   {cfg.stash_dead_letter_dir}")
    print(f"  STASH_GCS_BUCKET:        {cfg.stash_gcs_bucket}")
    print(f"  STASH_GCS_PREFIX:        {cfg.stash_gcs_prefix}")
    print(f"  DISK_TARGET:             {cfg.disk_target} (free={free_now / 1024**3:.1f}G)")
    print(f"  HTTP_TIMEOUT_SECONDS:    {cfg.http_timeout_seconds}")
    print(f"  POLL_INTERVAL_SECONDS:   {cfg.poll_interval_seconds}")
    print()
    print("No requests will be sent.")


def print_summary(input_path: Path, started_at: float) -> None:
    classes = ["done", "skipped", "invalid", "notfound", "failed"]
    counts: dict[str, int] = {}
    for klass in classes:
        path = Path(f"{input_path}.stash_{klass}.txt")
        if path.exists():
            counts[klass] = sum(1 for _ in path.read_text(encoding="utf-8").splitlines() if _.strip())
        else:
            counts[klass] = 0
    elapsed = int(time.time() - started_at)
    h, rem = divmod(elapsed, 3600)
    m, s = divmod(rem, 60)
    total = sum(counts.values())
    print()
    print("=== Batch summary ===")
    print(f"Processed: {total}")
    for klass in classes:
        print(f"  {klass.capitalize():<9}{counts[klass]}")
    print(f"Elapsed: {h:02d}:{m:02d}:{s:02d}")


def _build_config_from_env() -> Config:
    bucket = os.environ.get("STASH_GCS_BUCKET", "")
    if not bucket:
        print("STASH_GCS_BUCKET environment variable is required", file=sys.stderr)
        sys.exit(2)
    return Config(
        crawler_base_url=os.environ.get("CRAWLER_BASE_URL", "http://localhost:8500/crawler"),
        stash_local_dir=os.environ.get("STASH_LOCAL_DIR", "/app/stash"),
        stash_dead_letter_dir=os.environ.get("STASH_DEAD_LETTER_DIR", "crawler_archives/dead_letter"),
        stash_gcs_bucket=bucket,
        stash_gcs_prefix=os.environ.get("STASH_GCS_PREFIX", "stash"),
        disk_target=os.environ.get("DISK_TARGET", "/mnt/data"),
        http_timeout_seconds=int(os.environ.get("HTTP_TIMEOUT_SECONDS", "30")),
        poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "10")),
    )


def _configure_logging(input_path: Path) -> None:
    log_path = Path(f"{input_path}.stash_run.log")
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    logger.setLevel(logging.INFO)
    stdout_h = logging.StreamHandler(sys.stdout)
    stdout_h.setFormatter(fmt)
    file_h = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_h.setFormatter(fmt)
    logger.addHandler(stdout_h)
    logger.addHandler(file_h)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sequentially stash a list of terminal crawls to GCS.",
    )
    parser.add_argument("input_file", help="Path to <size>\\t<id>[ → marker] input file")
    parser.add_argument("--dry-run", action="store_true", help="Print plan; make no requests.")
    args = parser.parse_args()

    input_path = Path(args.input_file).resolve()
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    cfg = _build_config_from_env()
    _configure_logging(input_path)

    # Count skipped (marker) lines for the dry-run header
    raw_text = input_path.read_text(encoding="utf-8")
    skipped_count = sum(
        1 for raw in raw_text.splitlines()
        if "\t" in raw and "→" in raw.split("\t", 1)[1]
    )

    state = BatchState(input_path)
    done_count = len(state.done)

    try:
        work_list = load_work_list(input_path, state.done)
    except FatalError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print_dry_run(work_list, cfg, input_path, skipped_count, done_count)
        return 0

    install_signal_handlers()
    started_at = time.time()
    exit_code = 0
    try:
        logger.info("Starting batch: %d crawls to process", len(work_list))
        for size_bytes, crawl_id in work_list:
            if _stop_requested:
                logger.warning("Stop requested — exiting before next crawl")
                break
            process_crawl(size_bytes, crawl_id, state, cfg)
        logger.info("Batch finished successfully")
    except FatalError as e:
        logger.error("FATAL: %s", e)
        exit_code = 1
    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt received")
        exit_code = 130
    finally:
        print_summary(input_path, started_at)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run acceptance checks**

```bash
# A. Help
python tools/stash_crawls_batch.py --help

# B. Missing bucket (Linux/macOS)
STASH_GCS_BUCKET= python tools/stash_crawls_batch.py tools/test_stash_crawls_batch.py; echo "exit=$?"

# B'. Missing bucket (Windows PowerShell)
$env:STASH_GCS_BUCKET=$null; python tools/stash_crawls_batch.py tools/test_stash_crawls_batch.py; echo "exit=$LASTEXITCODE"

# C. Dry run on a fixture
cat > /tmp/smoke.txt <<'EOF'
139M	6271
142M	6299
20G	6080
EOF
STASH_GCS_BUCKET=fake python tools/stash_crawls_batch.py /tmp/smoke.txt --dry-run
```

Expected:
- A: usage text printed, exit 0.
- B: stderr `"STASH_GCS_BUCKET environment variable is required"`, exit 2.
- C: dry-run plan printed with 3 IDs sorted ascending (6271, 6299, 6080), exit 0.

- [ ] **Step 3: Re-run unit tests — confirm no regression**

Run: `pytest tools/test_stash_crawls_batch.py -v`
Expected: 9 PASS.

- [ ] **Step 4: Commit**

```bash
cat > /tmp/EDITMSG <<'EOF'
feat(tools): CLI entry + dry-run + summary for stash_crawls_batch

[EN]
Wires up the runnable entry point of tools/stash_crawls_batch.py:
argparse with <input-file> positional and --dry-run flag, env-driven
Config builder that exits 2 with a clear stderr message if
STASH_GCS_BUCKET is missing, dual stdout + <input>.stash_run.log
logging, dry-run renderer that prints the parsed plan with per-crawl
computed timeouts + config summary + current disk free, and a main()
loop that iterates the work list under signal-guarded process_crawl
and always prints a per-class summary on exit (success, fatal, or
interrupt). 9/9 unit tests still green; manual smoke per T3
acceptance criteria validates the integration end-to-end on the
server VM.

[FR]
Câble le point d'entrée exécutable de tools/stash_crawls_batch.py :
argparse avec positionnel <input-file> et flag --dry-run, builder
Config piloté par env qui sort en code 2 avec un message stderr clair
si STASH_GCS_BUCKET manque, logging dual stdout + <input>.stash_run.log,
rendu --dry-run qui imprime le plan parsé avec timeouts calculés par
crawl + résumé config + disque libre actuel, et un main() qui itère
la work list sous process_crawl gardé par signaux et imprime toujours
un résumé par classe à la sortie (succès, fatal, ou interruption).
9/9 tests unitaires verts ; smoke manuel selon les critères
d'acceptation de T3 valide l'intégration de bout en bout sur la VM
serveur.
EOF
git add tools/stash_crawls_batch.py
git commit -F /tmp/EDITMSG
git log -1 --format="%s"
```

---

## Self-review notes

**Spec coverage (12 acceptance items from spec §13):**

| Spec item | Covered by |
|---|---|
| Reads `<size>\t<id>[ → marker]` input | T0 (`parse_line`, `load_work_list`) |
| Skips marked lines | T0 (`parse_line` returns None for `→` lines) |
| Sorts ascending by size | T0 (`load_work_list` sorts) |
| Resumes from `<input>.stash_done.txt` | T0 (`BatchState._load_done`) + T3 (`main` reads `state.done`) |
| Strict sequential, 1 in-flight | T3 (`main` for-loop, no threading) |
| Pre-flight disk guard | T1 (`wait_for_disk`) + T2 (`process_crawl` calls it first) |
| 202/400/404/409/5xx handling | T2 (`process_crawl`) |
| Poll local-absent + GCS-present, abort on dead-letter | T1 (helpers) + T2 (`process_crawl`) |
| Per-crawl timeout formula | T1 (`per_crawl_timeout`) |
| Class-segmented state files | T0 (`BatchState.append`) |
| SIGINT/SIGTERM graceful between crawls | T2 (`install_signal_handlers` + `_stop_requested` checks) |
| `--dry-run` no side effects | T3 (`print_dry_run`, branch in `main`) |
| 9 unit tests pass | T0 (6) + T1 (3) |
| Manual smoke on 2 smallest pending IDs | T3 (post-merge acceptance, operator runs) |

**Placeholder scan:** no TBD, no "implement later", every code step is complete and pasteable. Verify commands are exact.

**Type consistency:** `Config` field names appear identically across the structure diagram, the dedicated "Configuration dataclass" section, T2's definition, and T3's `_build_config_from_env`. `BatchState.append(klass, crawl_id, detail)` signature is identical between T0 definition and T2 callsites. `process_crawl(size_bytes, crawl_id, state, cfg)` signature identical between T2 definition and T3 callsite.
