# Crawler Daemon Launcher (`tools/start-crawler-daemon.sh`)

**Author:** Rindra ANDRIANJANAKA
**Date:** 2026-05-20
**Service:** `tools/` + `apps-microservices/crawler-service/`
**Status:** Design approved — pending implementation plan

---

## 1. Context

The crawler-service stash flow shipped on 2026-05-19 added two new daemon
variants alongside the existing archive flow:

| Variant | Script | Required env vars |
|---|---|---|
| Archive Upload | `tools/upload_daemon.sh` | (defaults) |
| Stash Upload | `tools/upload_daemon.sh` | `UPLOAD_WATCH_DIR`, `UPLOAD_GCS_PREFIX` |
| Archive Download | `tools/download_daemon.sh` | (defaults) |
| Stash Download | `tools/download_daemon.sh` | `DOWNLOAD_REQUESTS_PATH`, `DOWNLOAD_RESULTS_PATH`, `DOWNLOAD_GCS_PREFIX`, `DELETE_AFTER_DOWNLOAD` |

The user runs daemons via `screen` (not systemd). After the stash
feature landed they discovered the manual flow was error-prone:

- During the 2026-05-20 stash test of crawl 1958 the upload daemon
  appeared idle. Root cause was that only the default-env archive
  daemon was running — no second screen session was started for the
  stash variant. The tar was correctly written to `crawler_stash/` but
  the running daemon was watching `crawler_archives/` and ignored it.
- Remembering the 4 env-var combinations and standardized screen
  names is friction. Each setup cycle risks an inconsistency.

The launcher centralizes that flow into one interactive script with
per-daemon detection and prompts.

## 2. Scope

### In scope

- New script `tools/start-crawler-daemon.sh` that:
  - Defines a table of the 4 daemon variants with standardized screen
    session names, scripts, and env vars
  - For each variant: detects if a screen session of that name is
    already running and prompts the user with one of two menus:
    - **Running**: `(s)kip / (r)estart / (q)uit` (default: skip)
    - **Not running**: `(s)tart / (n)o / (q)uit` (default: no)
  - Stops via `screen -X -S <name> quit` (idempotent)
  - Starts via `screen -dmS <name> bash -c "export VAR=val; ./script.sh 2>&1 | tee -a logs/<name>.log"`
  - Prints a summary at the end (`screen -ls` filtered to crawler-*).
- Update `docs/daemon_guide.md` with a new section "One-shot launcher:
  `tools/start-crawler-daemon.sh`" documenting screen-session names,
  usage, attaching/inspecting/stopping, and prerequisites. Add cross-
  references from the existing Upload and Download daemon sections.

### Out of scope

- A separate `stop-crawler-daemon.sh` script. `screen -X -S NAME quit`
  is one line; YAGNI.
- A `status` subcommand. `screen -ls | grep crawler-` is one line.
- Automation of host bind-source dir creation + chown. That is a
  one-time setup, separate from daemon lifecycle. Already documented in
  the existing `## Troubleshooting: 503 BIND_MOUNT_MISSING` runbook
  section.
- Migration to systemd units (also out of scope — user has explicitly
  chosen the screen workflow).
- A non-interactive flag (`--start-all` / `--restart-all`). YAGNI; if
  needed later, can be added without breaking the interactive flow.
- Paths with spaces. Current deploy path
  (`/home/devhp/RAG-HP-PUB/...`) has no spaces; defer stronger
  quoting until needed.

## 3. Architecture

### Standardized screen session names

| Daemon | Screen name | Watches host dir | Uploads to / downloads from |
|---|---|---|---|
| Archive Upload | `crawler-upload-archive` | `crawler_archives/` | `gs://$BUCKET/crawls/` |
| Stash Upload | `crawler-upload-stash` | `crawler_stash/` | `gs://$BUCKET/stash/` |
| Archive Download | `crawler-download-archive` | `crawler_download_requests/` | `gs://$BUCKET/crawls/` |
| Stash Download | `crawler-download-stash` | `crawler_stash_download_requests/` | `gs://$BUCKET/stash/` + GCS delete after extract |

Per-daemon detection uses `screen -ls | grep -q "\.<name>[[:space:]]"`
(anchor on dot prefix + trailing whitespace).

### Per-daemon UX flow

```
=== Archive Upload ===
[Detection: screen -ls | grep -q "\.crawler-upload-archive\s"]

If running:
  "Already running in screen: crawler-upload-archive (PID 12345)"
  "(s)kip / (r)estart / (q)uit [s]: "
  - s (or ENTER): no-op, continue to next daemon
  - r: stop existing + start fresh
  - q: exit 1 immediately

If not running:
  "Not running."
  "(s)tart / (n)o / (q)uit [n]: "
  - s / y: start
  - n (or ENTER): no-op, continue to next daemon
  - q: exit 1 immediately
```

Loop through all 4 daemons sequentially. After loop print summary
(`screen -ls` filtered).

### Daemon start mechanism

```bash
exports="export UPLOAD_WATCH_DIR=$STASH_DIR; export UPLOAD_GCS_PREFIX=stash; "
log_file="logs/crawler-upload-stash.log"

screen -dmS "crawler-upload-stash" \
    bash -c "${exports}tools/upload_daemon.sh 2>&1 | tee -a '$log_file'"
```

- `-dmS NAME` creates a detached named session.
- `bash -c "..."` runs the daemon inside the new shell.
- Env exports prepended inline. Same `bash -c` body, no environment
  inheritance issues from the parent screen process.
- Log tee'd to per-daemon file in `logs/` for offline inspection.
- After `screen -dmS`, sleep 1s then re-check `is_running` to confirm
  start succeeded (catches early daemon-exits, e.g. missing
  `GCS_BUCKET_NAME`).

### Daemon stop mechanism

```bash
screen -X -S "<name>" quit 2>/dev/null || true
sleep 1
```

- `screen -X -S NAME quit` instructs the named session to terminate.
- Idempotent: exit 0 even if session doesn't exist.
- `sleep 1` allows the daemon process to die before the next start
  attempts to re-open the same screen name.

## 4. Components

| File | Action | Responsibility |
|---|---|---|
| `tools/start-crawler-daemon.sh` | create | The interactive launcher: helpers (`is_running`, `get_pid`, `stop_daemon`, `start_daemon`) + main loop over the 4-entry `DAEMONS` array |
| `docs/daemon_guide.md` | modify | Append "One-shot launcher" section + cross-references from existing Upload/Download sections |

## 5. Script skeleton

```bash
#!/bin/bash
# tools/start-crawler-daemon.sh
# Interactive launcher for the 4 crawler-service daemon variants
# (archive + stash, upload + download). Detects existing screen sessions
# and prompts per-daemon to skip/restart/start.
#
# Usage:
#   bash tools/start-crawler-daemon.sh
#
# Prerequisites:
#   - GNU screen installed
#   - GCS_BUCKET_NAME in .env at repo root
#   - Host stash bind-source dirs pre-created + chowned (see
#     docs/daemon_guide.md Troubleshooting section)
#
# Exit codes:
#   0 - completed (some daemons may have been skipped)
#   1 - aborted via 'q' or fatal error

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

LOGS_DIR="$REPO_ROOT/logs"
mkdir -p "$LOGS_DIR"

STASH_DIR="$REPO_ROOT/apps-microservices/crawler-service/crawler_stash"
STASH_REQ_DIR="$REPO_ROOT/apps-microservices/crawler-service/crawler_stash_download_requests"
STASH_RES_DIR="$REPO_ROOT/apps-microservices/crawler-service/crawler_stash_download_results"

# Daemon table: NAME|SCREEN|SCRIPT|ENV_VARS
DAEMONS=(
    "Archive Upload|crawler-upload-archive|tools/upload_daemon.sh|"
    "Stash Upload|crawler-upload-stash|tools/upload_daemon.sh|UPLOAD_WATCH_DIR=$STASH_DIR UPLOAD_GCS_PREFIX=stash"
    "Archive Download|crawler-download-archive|tools/download_daemon.sh|"
    "Stash Download|crawler-download-stash|tools/download_daemon.sh|DOWNLOAD_REQUESTS_PATH=$STASH_REQ_DIR DOWNLOAD_RESULTS_PATH=$STASH_RES_DIR DOWNLOAD_GCS_PREFIX=stash DELETE_AFTER_DOWNLOAD=true"
)

is_running() {
    screen -ls 2>/dev/null | grep -q "\.$1[[:space:]]"
}

get_pid() {
    screen -ls 2>/dev/null | grep "\.$1[[:space:]]" \
        | awk -F'.' '{print $1}' | tr -d ' \t'
}

stop_daemon() {
    local screen_name="$1"
    echo "  Stopping $screen_name..."
    screen -X -S "$screen_name" quit 2>/dev/null || true
    sleep 1
}

start_daemon() {
    local name="$1"
    local screen_name="$2"
    local script="$3"
    local env_vars="$4"
    local log_file="$LOGS_DIR/$screen_name.log"

    local exports=""
    if [ -n "$env_vars" ]; then
        for kv in $env_vars; do
            exports="${exports}export $kv; "
        done
    fi

    echo "  Starting $name (log: $log_file)..."
    screen -dmS "$screen_name" \
        bash -c "${exports}$script 2>&1 | tee -a '$log_file'"
    sleep 1

    if is_running "$screen_name"; then
        echo "  OK $name running in screen $screen_name (PID $(get_pid "$screen_name"))"
    else
        echo "  FAIL: $name not running. Check $log_file"
        return 1
    fi
}

echo "==================================="
echo "Crawler Daemon Launcher"
echo "==================================="

for entry in "${DAEMONS[@]}"; do
    IFS='|' read -r name screen_name script env_vars <<< "$entry"

    echo ""
    echo "=== $name ==="

    if is_running "$screen_name"; then
        echo "Already running in screen: $screen_name (PID $(get_pid "$screen_name"))"
        read -rp "(s)kip / (r)estart / (q)uit [s]: " choice
        choice="${choice:-s}"
        case "$choice" in
            r|R)
                stop_daemon "$screen_name"
                start_daemon "$name" "$screen_name" "$script" "$env_vars"
                ;;
            q|Q)
                echo "Aborted by user."
                exit 1
                ;;
            *)
                echo "  Skipped."
                ;;
        esac
    else
        echo "Not running."
        read -rp "(s)tart / (n)o / (q)uit [n]: " choice
        choice="${choice:-n}"
        case "$choice" in
            s|S|y|Y)
                start_daemon "$name" "$screen_name" "$script" "$env_vars"
                ;;
            q|Q)
                echo "Aborted by user."
                exit 1
                ;;
            *)
                echo "  Skipped."
                ;;
        esac
    fi
done

echo ""
echo "=== Summary ==="
running=$(screen -ls 2>/dev/null \
    | grep -E "\.crawler-(upload|download)-(archive|stash)" || true)
if [ -n "$running" ]; then
    echo "$running"
else
    echo "No crawler daemons running."
fi
```

## 6. Edge cases

| Case | Handling |
|---|---|
| Screen not installed | `screen -ls` errors; `is_running` returns False; `start_daemon` invocation also fails. Script exits with code 1 via `set -e` on first daemon start attempt. Acceptable — operator needs to install screen. |
| Default ENTER on prompt | Defaults to safe no-op: `s` (skip) when running, `n` (no) when not running. No accidental restarts on stray ENTER. |
| `q` at any prompt | `exit 1` immediately. Previously-started daemons in this run remain running. |
| Daemon dies between `screen -dmS` and `is_running` check | `is_running` returns False after the 1s sleep; `start_daemon` returns 1; `set -e` propagates to script exit. Operator inspects the per-daemon log. |
| `screen -X quit` on non-existent session | Returns non-zero stderr but `2>/dev/null \|\| true` swallows. |
| Stop+restart race (daemon takes >1s to die) | A second `screen -dmS NAME` while the previous is dying could fail with "Name already in use". Acceptable for now — operator re-runs the script. YAGNI to add poll loop. |
| Paths with spaces in `STASH_DIR` etc. | Inline exports in `bash -c` body break with unquoted spaces. Current deploy paths have no spaces. Deferred. |
| `GCS_BUCKET_NAME` not set | Each daemon script aborts on its own (`exit 1` line 22 of upload_daemon.sh). `start_daemon` detects via `is_running` returning False after 1s. Surfaces as "FAIL" with log pointer. |
| `apps-microservices/crawler-service/crawler_stash/` missing | Upload daemon does `mkdir -p` (line 31) on its own watch dir. Download daemon does `mkdir -p` for both requests + results (line 65). Both ALSO do chown for upload (lines 36-37). Download does NOT chown (separate concern, deferred). Operator should pre-create + chown all 3 stash dirs at initial setup per existing runbook section. |

## 7. `docs/daemon_guide.md` runbook update

Add new section near existing daemon sections, BEFORE
`## Troubleshooting: 503 BIND_MOUNT_MISSING`:

```markdown
## One-shot launcher: `tools/start-crawler-daemon.sh`

The codebase ships a single interactive script that manages all 4
daemon variants (archive + stash, upload + download). Use it instead
of opening 4 manual screen sessions with env vars.

### What it does

For each of the 4 daemons it:
1. Detects if a screen session with the standard name already exists
2. Prompts per-daemon:
   - **Running**: `(s)kip / (r)estart / (q)uit` [default: skip]
   - **Not running**: `(s)tart / (n)o / (q)uit` [default: no]
3. On `r` or `s`(tart): launches via `screen -dmS` with env vars baked
   in + logs to `logs/<screen-name>.log`

### Screen session names

| Daemon | Screen name | Watches | Uploads to / downloads from |
|---|---|---|---|
| Archive Upload | `crawler-upload-archive` | `crawler_archives/` | `gs://$BUCKET/crawls/` |
| Stash Upload | `crawler-upload-stash` | `crawler_stash/` | `gs://$BUCKET/stash/` |
| Archive Download | `crawler-download-archive` | `crawler_download_requests/` | `gs://$BUCKET/crawls/` |
| Stash Download | `crawler-download-stash` | `crawler_stash_download_requests/` | `gs://$BUCKET/stash/` + GCS delete after extract |

### Usage

```bash
cd /home/devhp/RAG-HP-PUB
bash tools/start-crawler-daemon.sh
```

Walk through the 4 prompts. Default ENTER is safe
(skip-when-running, no-when-stopped). Type `q` at any prompt to abort.

### Inspecting / attaching / stopping

```bash
# List sessions
screen -ls

# Attach to a specific daemon (Ctrl+A then D to detach)
screen -r crawler-upload-stash

# Tail a daemon's log without attaching
tail -f logs/crawler-upload-stash.log

# Stop a specific daemon
screen -X -S crawler-upload-stash quit
```

### Prerequisites

The script does NOT pre-create host bind-source dirs. Do that once
during initial setup (see `## Troubleshooting: 503 BIND_MOUNT_MISSING`
section below for the `mkdir + sudo chown` block).
```

Plus a one-line cross-reference at the top of each existing daemon
section (Upload + Download):

> **Tip:** Prefer `tools/start-crawler-daemon.sh` over manual screen
> setup. See § One-shot launcher.

## 8. Tests

Pure bash + screen dependency — no practical automated unit tests.
Verification = manual smoke tests on the server:

1. **Fresh state** — no daemons running. Run script. Choose `s`
   (start) for all 4. Verify `screen -ls` shows 4 sessions and 4
   `logs/<name>.log` files exist.
2. **Idempotent skip** — all 4 running. Re-run script. Press ENTER
   on all 4 (skip default). Verify PIDs unchanged.
3. **Selective restart** — all 4 running. Choose `r` for stash
   upload only; ENTER on the other 3. Verify only the stash-upload
   PID changed (`get_pid crawler-upload-stash`).
4. **Quit mid-loop** — fresh state. Choose `s` for first daemon,
   then `q` on second. Verify exit 1 + first daemon still running.
5. **Env propagation** — stash upload running. Inspect process env:
   ```bash
   cat /proc/$(pgrep -af "tools/upload_daemon.sh" | grep stash | awk '{print $1}')/environ | tr '\0' '\n' | grep UPLOAD_
   ```
   Expected: `UPLOAD_WATCH_DIR=…/crawler_stash` + `UPLOAD_GCS_PREFIX=stash`.

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Screen session name collision with a non-crawler workload | Names are prefixed `crawler-` and the launcher only touches its known 4. Unlikely. |
| Operator interrupts (Ctrl+C) mid-prompt | `set -e` propagates the SIGINT; script exits non-zero. Any started daemons in the run remain running (they're detached). |
| Hook clobbers `.git/COMMIT_EDITMSG` during commit (known issue) | Documented amend recipe in plan/runbook. |
| Default ENTER changes between menu types confuses operators | The default is shown in brackets `[s]` / `[n]` so it's explicit. |

## 10. Out of scope (deferred follow-ups)

- `stop-crawler-daemon.sh` — separate script for explicit "kill all"
  flow. Defer until needed.
- Status subcommand inside this script.
- Non-interactive `--all` flag.
- Adding chown to `download_daemon.sh` for symmetry with upload daemon.
- Migration to systemd (operator preference).
