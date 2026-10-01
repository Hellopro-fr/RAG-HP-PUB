# Crawler Daemon Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a single interactive bash launcher (`tools/start-crawler-daemon.sh`) that manages all 4 crawler-service daemon variants (archive + stash, upload + download) via standardized screen session names, and document it in `docs/daemon_guide.md`.

**Architecture:** Pure bash script driven by a 4-entry table. Per-daemon detection via `screen -ls | grep`. Per-daemon prompt with safe ENTER defaults (`s`kip when running, `n`o when not running) and a `q`uit option. Idempotent stop via `screen -X -S NAME quit`. Start via `screen -dmS NAME bash -c "exports; ./script.sh | tee log"` with `is_running` re-check after 1s to catch early-exits.

**Tech Stack:** Bash, GNU screen, existing `tools/upload_daemon.sh` + `tools/download_daemon.sh`.

**Spec:** `docs/superpowers/specs/2026-05-20-crawler-daemon-launcher-design.md` (commit `cd2eaf1e`).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `tools/start-crawler-daemon.sh` | create + chmod +x | T0: interactive launcher script (helpers + main loop) |
| `docs/daemon_guide.md` | modify | T1: append "One-shot launcher" section before line 286 (BIND_MOUNT_MISSING) + two one-line cross-reference tips at lines 53 and 149 |

---

## Task Sequence

2 tasks. T0 standalone (script). T1 standalone (docs). Sequential because each is a single commit and we want T0 SHA referenced in T1's commit message body.

| Task | Touches | Depends on |
|---|---|---|
| T0 | `tools/start-crawler-daemon.sh` | — |
| T1 | `docs/daemon_guide.md` | T0 (for SHA reference) |

---

## Task 0: Create `tools/start-crawler-daemon.sh`

**Goal:** Ship the executable interactive launcher.

**Files:**
- Create: `D:\DevHellopro\Workspaces\RAG-HP-PUB\tools\start-crawler-daemon.sh`

**Acceptance Criteria:**
- [ ] File exists at `tools/start-crawler-daemon.sh` with mode +x (executable)
- [ ] `bash -n tools/start-crawler-daemon.sh` exits 0 (syntax OK)
- [ ] First line is `#!/bin/bash`
- [ ] Defines `DAEMONS` array with exactly 4 entries, pipe-delimited (name|screen|script|env_vars)
- [ ] Defines functions: `is_running`, `get_pid`, `stop_daemon`, `start_daemon`
- [ ] Main loop iterates `${DAEMONS[@]}` and prompts per-daemon
- [ ] `set -e` at the top so failed `start_daemon` propagates

**Verify:**
```bash
bash -n D:/DevHellopro/Workspaces/RAG-HP-PUB/tools/start-crawler-daemon.sh && echo "SYNTAX OK"
test -x D:/DevHellopro/Workspaces/RAG-HP-PUB/tools/start-crawler-daemon.sh && echo "EXEC OK"
```
Expected: both `SYNTAX OK` and `EXEC OK` print.

**Steps:**

- [ ] **Step 0.1: Create the script file**

Use the `Write` tool to write this exact content to `D:\DevHellopro\Workspaces\RAG-HP-PUB\tools\start-crawler-daemon.sh`:

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
#     docs/daemon_guide.md "Troubleshooting: 503 BIND_MOUNT_MISSING")
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

    # Build "export KEY=VAL; ..." prefix for env vars
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

- [ ] **Step 0.2: Make the script executable**

```bash
chmod +x D:/DevHellopro/Workspaces/RAG-HP-PUB/tools/start-crawler-daemon.sh
```

- [ ] **Step 0.3: Syntax check**

```bash
bash -n D:/DevHellopro/Workspaces/RAG-HP-PUB/tools/start-crawler-daemon.sh && echo "SYNTAX OK"
```

Expected: `SYNTAX OK`.

- [ ] **Step 0.4: Sanity check the executable bit**

```bash
test -x D:/DevHellopro/Workspaces/RAG-HP-PUB/tools/start-crawler-daemon.sh && echo "EXEC OK"
```

Expected: `EXEC OK`. (On Windows git this may differ — see Step 0.4b.)

- [ ] **Step 0.4b: If `test -x` fails on Windows, use git mode bit**

If running from Windows, `test -x` may not reflect the mode that will land on the Linux server. Force the executable bit in the git index so it propagates correctly on push:

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
git update-index --add --chmod=+x tools/start-crawler-daemon.sh
git ls-files --stage tools/start-crawler-daemon.sh
```

Expected output last line: starts with `100755` (executable mode), not `100644`.

- [ ] **Step 0.5: Commit (bilingual EN+FR via COMMIT_EDITMSG)**

Use the `Write` tool to write `D:/DevHellopro/Workspaces/RAG-HP-PUB/.git/COMMIT_EDITMSG` with this content:

```
feat(tools): interactive crawler daemon launcher

EN:
New tools/start-crawler-daemon.sh script that manages all 4
crawler-service daemon variants (archive + stash, upload + download)
via standardized screen session names:

- crawler-upload-archive
- crawler-upload-stash
- crawler-download-archive
- crawler-download-stash

For each daemon the script:
1. Detects existing screen session via `screen -ls | grep`
2. Prompts (s)kip/(r)estart/(q)uit when running [default: skip], or
   (s)tart/(n)o/(q)uit when not running [default: no]
3. On restart: `screen -X -S NAME quit` (idempotent) + start fresh
4. On start: `screen -dmS NAME bash -c "export VAR=val; script | tee log"`
5. Re-checks is_running after 1s to catch early-exits

After the loop prints a summary via `screen -ls | grep crawler-`.

Set -e propagates failures. Default ENTER on each prompt is safe
(skip-when-running, no-when-stopped). Type `q` to abort with exit 1.

Out of scope per spec: stop-all script, status subcommand, --all flag,
systemd migration, paths-with-spaces, host dir pre-create.

Spec: docs/superpowers/specs/2026-05-20-crawler-daemon-launcher-design.md

FR:
Nouveau script tools/start-crawler-daemon.sh qui gere les 4 variants
de daemon crawler-service (archive + stash, upload + download) via
des noms de session screen standardises :

- crawler-upload-archive
- crawler-upload-stash
- crawler-download-archive
- crawler-download-stash

Pour chaque daemon le script :
1. Detecte la session screen existante via `screen -ls | grep`
2. Prompt (s)kip/(r)estart/(q)uit si running [default: skip], ou
   (s)tart/(n)o/(q)uit si stopped [default: no]
3. Sur restart : `screen -X -S NAME quit` (idempotent) + start neuf
4. Sur start : `screen -dmS NAME bash -c "export VAR=val; script | tee log"`
5. Re-verifie is_running apres 1s pour attraper les early-exits

Apres la boucle affiche un summary via `screen -ls | grep crawler-`.

Set -e propage les echecs. ENTER par defaut sur chaque prompt est
sur (skip-when-running, no-when-stopped). Taper `q` pour aborter
avec exit 1.

Hors scope par spec : script stop-all, sous-commande status, flag
--all, migration systemd, paths avec espaces, pre-create des dirs
host.
```

Then commit:

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
git add tools/start-crawler-daemon.sh
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
git log -1 --format="%H %s"
```

**Hook clobber recipe:** if `git log -1 --format="%H %s"` shows a subject starting with `chore(graphify)` (the graphify post-commit hook re-wrote `.git/COMMIT_EDITMSG` between Write and commit), use the `Write` tool to re-write `.git/COMMIT_EDITMSG` with the **exact same content above**, then:

```bash
git -c commit.encoding=utf-8 commit --amend -F .git/COMMIT_EDITMSG
git log -1 --format="%H %s"
```

Verify the final subject is `feat(tools): interactive crawler daemon launcher`.

---

## Task 1: `docs/daemon_guide.md` runbook update

**Goal:** Append a new "One-shot launcher" section to `docs/daemon_guide.md` BEFORE the existing `## Troubleshooting: 503 BIND_MOUNT_MISSING` section (currently at line 286), and add one-line cross-reference tips at the top of the existing Upload Daemon (line 51) and Download Daemon (line 147) sections.

**Files:**
- Modify: `D:\DevHellopro\Workspaces\RAG-HP-PUB\docs\daemon_guide.md`

**Acceptance Criteria:**
- [ ] New `## One-shot launcher: \`tools/start-crawler-daemon.sh\`` section added BEFORE `## Troubleshooting: 503 \`BIND_MOUNT_MISSING\``
- [ ] Section contains the 4-row screen-session table with watches + uploads/downloads columns
- [ ] Section contains a `bash tools/start-crawler-daemon.sh` usage block
- [ ] Section contains attach/tail/stop command examples
- [ ] One-line "Tip:" cross-reference added at the top of the existing Upload Daemon section
- [ ] Same "Tip:" added at the top of the existing Download Daemon section
- [ ] `grep -c "One-shot launcher" docs/daemon_guide.md` returns 1 (heading), AND `grep -c "Prefer \`tools/start-crawler-daemon.sh\`" docs/daemon_guide.md` returns 2 (one per existing section)

**Verify:**
```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
grep -c "One-shot launcher: \`tools/start-crawler-daemon.sh\`" docs/daemon_guide.md
grep -c "Prefer \`tools/start-crawler-daemon.sh\`" docs/daemon_guide.md
grep -c "crawler-upload-archive" docs/daemon_guide.md
grep -c "crawler-download-stash" docs/daemon_guide.md
```
Expected: first → 1, second → 2, third → ≥1, fourth → ≥1.

**Steps:**

- [ ] **Step 1.1: Insert the cross-reference at the top of the Upload Daemon section**

Use the `Edit` tool on `docs/daemon_guide.md`. Find this exact block (lines 51-53):

```markdown
## Upload Daemon (`upload_daemon.sh`)

Automatically uploads archived crawl jobs to GCS. The crawler service places `.tar.gz` archives in the shared `crawler_archives/` directory, and this daemon uploads them to `gs://{bucket}/crawls/` then deletes the local file.
```

Replace with:

```markdown
## Upload Daemon (`upload_daemon.sh`)

> **Tip:** Prefer `tools/start-crawler-daemon.sh` over manual screen setup. See § One-shot launcher.

Automatically uploads archived crawl jobs to GCS. The crawler service places `.tar.gz` archives in the shared `crawler_archives/` directory, and this daemon uploads them to `gs://{bucket}/crawls/` then deletes the local file.
```

- [ ] **Step 1.2: Insert the cross-reference at the top of the Download Daemon section**

Find this exact block (lines 147-149):

```markdown
## Download Daemon (`download_daemon.sh`)

Downloads archived crawl data from GCS on demand. When a user requests results for an archived crawl (via `GET /results/{crawl_id}`), the crawler service writes a `.request` file to the shared `crawler_download_requests/` directory. This daemon picks it up, downloads the archive from GCS, and places it in `crawler_download_results/` with a `.done` marker. The service then streams the file to the client and cleans up.
```

Replace with:

```markdown
## Download Daemon (`download_daemon.sh`)

> **Tip:** Prefer `tools/start-crawler-daemon.sh` over manual screen setup. See § One-shot launcher.

Downloads archived crawl data from GCS on demand. When a user requests results for an archived crawl (via `GET /results/{crawl_id}`), the crawler service writes a `.request` file to the shared `crawler_download_requests/` directory. This daemon picks it up, downloads the archive from GCS, and places it in `crawler_download_results/` with a `.done` marker. The service then streams the file to the client and cleans up.
```

- [ ] **Step 1.3: Insert the new "One-shot launcher" section BEFORE the BIND_MOUNT_MISSING section**

Find this exact block (around line 283-286):

```markdown
The `dead_letter/` directory is **never** auto-cleaned — it requires manual investigation.


## Troubleshooting: 503 `BIND_MOUNT_MISSING`
```

Replace with:

```markdown
The `dead_letter/` directory is **never** auto-cleaned — it requires manual investigation.


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


## Troubleshooting: 503 `BIND_MOUNT_MISSING`
```

- [ ] **Step 1.4: Verify the docs**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
grep -c "One-shot launcher: \`tools/start-crawler-daemon.sh\`" docs/daemon_guide.md
grep -c "Prefer \`tools/start-crawler-daemon.sh\`" docs/daemon_guide.md
grep -c "crawler-upload-archive" docs/daemon_guide.md
grep -c "crawler-download-stash" docs/daemon_guide.md
```

Expected output (4 numbers, in order):
```
1
2
≥1
≥1
```

- [ ] **Step 1.5: Commit (bilingual EN+FR via COMMIT_EDITMSG)**

Use the `Write` tool to write `D:/DevHellopro/Workspaces/RAG-HP-PUB/.git/COMMIT_EDITMSG` with:

```
docs(daemon-guide): document start-crawler-daemon.sh launcher

EN:
Append a new "## One-shot launcher: tools/start-crawler-daemon.sh"
section to docs/daemon_guide.md BEFORE the existing
"## Troubleshooting: 503 BIND_MOUNT_MISSING" section. Documents:

- What the launcher does (per-daemon detect + prompt loop)
- Screen session names table (4 rows)
- Usage one-liner
- Inspecting / attaching / stopping commands (screen -ls / -r / -X)
- Prerequisites pointing at the existing BIND_MOUNT_MISSING runbook
  for the one-time mkdir+chown setup

Plus one-line "Tip:" cross-references at the top of the existing
Upload Daemon and Download Daemon sections, redirecting operators to
the launcher first.

Launcher script shipped in the previous commit (see spec
docs/superpowers/specs/2026-05-20-crawler-daemon-launcher-design.md).

FR:
Ajout d'une section « ## One-shot launcher: tools/start-crawler-daemon.sh »
a docs/daemon_guide.md AVANT la section existante
« ## Troubleshooting: 503 BIND_MOUNT_MISSING ». Documente :

- Ce que fait le launcher (loop de detect + prompt par daemon)
- Table des noms de session screen (4 lignes)
- Usage one-liner
- Commandes inspect / attach / stop (screen -ls / -r / -X)
- Prerequis pointant vers le runbook BIND_MOUNT_MISSING existant pour
  le setup one-time mkdir+chown

Plus des cross-references « Tip: » d'une ligne au top des sections
Upload Daemon et Download Daemon existantes, redirigeant les
operateurs vers le launcher en premier.

Script du launcher livre dans le commit precedent (voir spec
docs/superpowers/specs/2026-05-20-crawler-daemon-launcher-design.md).
```

Then commit:

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
git add docs/daemon_guide.md
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
git log -1 --format="%H %s"
```

**Hook clobber recipe:** if subject becomes `chore(graphify) ...`, use `Write` to re-write `.git/COMMIT_EDITMSG` with the exact same content above, then:

```bash
git -c commit.encoding=utf-8 commit --amend -F .git/COMMIT_EDITMSG
git log -1 --format="%H %s"
```

Verify the final subject is `docs(daemon-guide): document start-crawler-daemon.sh launcher`.

---

## Post-Plan Verification

After both tasks land:

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB

# Script in place + executable + syntax-clean
test -f tools/start-crawler-daemon.sh && bash -n tools/start-crawler-daemon.sh && echo "SCRIPT OK"
git ls-files --stage tools/start-crawler-daemon.sh | awk '{print $1}'   # expect 100755

# Docs reference launcher (1 heading + 2 cross-refs)
grep -c "One-shot launcher: \`tools/start-crawler-daemon.sh\`" docs/daemon_guide.md
grep -c "Prefer \`tools/start-crawler-daemon.sh\`" docs/daemon_guide.md

# Commit log
git log --oneline cd2eaf1e..HEAD
```

Expected:
- `SCRIPT OK`
- `100755`
- `1`
- `2`
- 2 commits since the spec, subjects:
  - `feat(tools): interactive crawler daemon launcher`
  - `docs(daemon-guide): document start-crawler-daemon.sh launcher`

---

## Self-Review

**1. Spec coverage:**

| Spec section | Plan task | Notes |
|---|---|---|
| §3 Architecture (screen names + UX flow) | T0 (script comments + DAEMONS array) | one row per variant |
| §4 Components (script file + docs file) | T0 + T1 | exact mapping |
| §5 Script skeleton | T0 Step 0.1 | full code embedded |
| §6 Edge cases | T0 Step 0.1 (handled inline) + commit body | documented in spec, behavior in code |
| §7 Runbook (new section + cross-refs) | T1 Steps 1.1 - 1.3 | section + 2 tips |
| §8 Tests (5 manual smoke scenarios) | post-plan verification + spec §8 | no automated framework; smoke = manual |
| §9 Risks | implicit in code (sleep + idempotent quit) | no separate task |
| §10 Out of scope | preserved in commit body | declared explicitly |

All spec sections accounted for.

**2. Placeholder scan:** no TBD/TODO/"implement later". Every step shows exact code or commands. Verify outputs given.

**3. Type/name consistency:**
- Script path `tools/start-crawler-daemon.sh` — used identically in T0 + T1 + commit messages.
- Screen names `crawler-upload-archive` / `crawler-upload-stash` / `crawler-download-archive` / `crawler-download-stash` — same across DAEMONS array (T0), docs table (T1), and verify command grep patterns.
- Helper function names `is_running` / `get_pid` / `stop_daemon` / `start_daemon` — used identically across the embedded script and the acceptance criteria.

---

## Task ID Mapping

This plan creates 2 native tasks. After the plan write, native tasks will be created with the metadata fence pattern:

| Plan Task | Native Task |
|---|---|
| T0 — script | (to be created) |
| T1 — runbook | (to be created, depends on T0) |
