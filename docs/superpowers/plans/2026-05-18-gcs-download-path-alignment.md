# GCS Download Path Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore 3-way alignment of GCS download IPC paths across `crawler-service` config, docker-compose bind targets, and the host-side `download_daemon.sh` — broken by regression `29918f83` (2026-03-31).

**Architecture:** Two-file string-rename pass restoring the original `1bb288a7` paths and unifying env var names (`DOWNLOAD_REQUESTS_PATH` / `DOWNLOAD_RESULTS_PATH`) across Python and the daemon. A regression test asserts the three layers stay aligned end-to-end. No architectural change; no compose change.

**Tech Stack:** Python 3.10, FastAPI, `pydantic_settings.BaseSettings`, bash, pytest.

**Spec:** `docs/superpowers/specs/2026-05-18-gcs-download-path-alignment-design.md` (commit `99c1d0a8`).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `apps-microservices/crawler-service/tests/test_config_paths.py` | Create | Regression test: assert `settings.DOWNLOAD_REQUESTS_PATH` and `DOWNLOAD_RESULTS_PATH` match compose bind target; assert daemon reads canonical env var names. |
| `apps-microservices/crawler-service/app/core/config.py` | Modify (lines 33-35) | Restore `DOWNLOAD_REQUESTS_PATH` / `DOWNLOAD_RESULTS_PATH` defaults from `/app/gcs-requests` / `/app/gcs-downloads` to `/app/download_requests` / `/app/download_results`. |
| `tools/download_daemon.sh` | Modify (lines 17-21) | Rename env var read from `DOWNLOAD_REQUESTS_DIR` / `DOWNLOAD_RESULTS_DIR` to `DOWNLOAD_REQUESTS_PATH` / `DOWNLOAD_RESULTS_PATH`. |
| `docker-compose.yml` | No change | Bind target already `/app/download_requests` and `/app/download_results`. |

---

## Task Sequence

Three tasks, executed in TDD order: failing test first (T1), then minimal fix in Python (T2 — 2 of 3 assertions pass), then daemon fix (T3 — all green). Each task is one committable change.

---

### Task 1: Add regression test asserting 3-way path alignment

**Goal:** Land a failing test that captures the alignment invariant so the next two tasks have a green-bar target.

**Files:**
- Create: `apps-microservices/crawler-service/tests/test_config_paths.py`

**Acceptance Criteria:**
- [ ] New test file exists with three test functions: `test_download_requests_path_matches_compose_bind_target`, `test_download_results_path_matches_compose_bind_target`, `test_download_daemon_uses_canonical_env_var_names`.
- [ ] Running the suite shows all three failing with current code (defaults at `/app/gcs-requests` / `/app/gcs-downloads`, daemon reading `DOWNLOAD_REQUESTS_DIR` / `DOWNLOAD_RESULTS_DIR`).
- [ ] Each test has a docstring explaining the failure mode it catches.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_config_paths.py -v` → 3 FAIL.

**Steps:**

- [ ] **Step 1.1: Create the test file with all three failing assertions**

Create `apps-microservices/crawler-service/tests/test_config_paths.py`:

```python
"""Regression tests for GCS download path alignment.

These three tests pin the contract between three layers of the GCS download
pipeline:
  1. Python container default (settings.DOWNLOAD_REQUESTS_PATH / _RESULTS_PATH)
  2. docker-compose bind target (/app/download_requests, /app/download_results)
  3. Host-side daemon env var read (DOWNLOAD_REQUESTS_PATH / DOWNLOAD_RESULTS_PATH)

If any layer drifts, the FastAPI service writes .request files into a
non-mounted directory and every GCS download times out at 504.

Regression history: introduced by commit 29918f83 (2026-03-31) when the
pydantic-settings refactor silently renamed Python defaults. See
docs/superpowers/specs/2026-05-18-gcs-download-path-alignment-design.md.
"""

from pathlib import Path


def test_download_requests_path_matches_compose_bind_target():
    """settings.DOWNLOAD_REQUESTS_PATH must equal the compose bind target.

    Compose binds host crawler_download_requests/ -> container
    /app/download_requests (docker-compose.yml:1348). If this default
    drifts, the FastAPI side writes .request files into a non-mounted
    directory and the host daemon never sees them — every GCS download
    504s.
    """
    from app.core.config import settings
    assert settings.DOWNLOAD_REQUESTS_PATH == "/app/download_requests"


def test_download_results_path_matches_compose_bind_target():
    """settings.DOWNLOAD_RESULTS_PATH must equal the compose bind target.

    Compose binds host crawler_download_results/ -> container
    /app/download_results (docker-compose.yml:1349). Same reasoning as
    DOWNLOAD_REQUESTS_PATH: drift here means the FastAPI poller watches
    a non-mounted directory and 504s on every download.
    """
    from app.core.config import settings
    assert settings.DOWNLOAD_RESULTS_PATH == "/app/download_results"


def test_download_daemon_uses_canonical_env_var_names():
    """tools/download_daemon.sh must read the same env var names as Python.

    Historic daemon names DOWNLOAD_REQUESTS_DIR / DOWNLOAD_RESULTS_DIR
    diverged from the Python side (DOWNLOAD_REQUESTS_PATH /
    DOWNLOAD_RESULTS_PATH). After the alignment fix the daemon and Python
    both read the same env vars; this test catches a future regression
    back to the legacy _DIR names.
    """
    daemon = Path(__file__).resolve().parents[3] / "tools" / "download_daemon.sh"
    content = daemon.read_text(encoding="utf-8")

    assert "DOWNLOAD_REQUESTS_PATH" in content, (
        "Daemon must read DOWNLOAD_REQUESTS_PATH env var (canonical name)"
    )
    assert "DOWNLOAD_RESULTS_PATH" in content, (
        "Daemon must read DOWNLOAD_RESULTS_PATH env var (canonical name)"
    )
    assert "DOWNLOAD_REQUESTS_DIR" not in content, (
        "Daemon must not read the legacy DOWNLOAD_REQUESTS_DIR var name"
    )
    assert "DOWNLOAD_RESULTS_DIR" not in content, (
        "Daemon must not read the legacy DOWNLOAD_RESULTS_DIR var name"
    )
```

- [ ] **Step 1.2: Run test to confirm all three fail**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_config_paths.py -v`

Expected: 3 FAILED.
- `test_download_requests_path_matches_compose_bind_target` — `AssertionError: assert '/app/gcs-requests' == '/app/download_requests'`
- `test_download_results_path_matches_compose_bind_target` — `AssertionError: assert '/app/gcs-downloads' == '/app/download_results'`
- `test_download_daemon_uses_canonical_env_var_names` — `AssertionError: Daemon must read DOWNLOAD_REQUESTS_PATH env var (canonical name)` (substring missing in daemon source).

- [ ] **Step 1.3: Commit the failing test**

Generate bilingual commit message in `.git/COMMIT_EDITMSG` via the Write tool (Windows cp1252 hazard — never use shell heredoc for accents per primer):

```
test(crawler-service): regression test for GCS download path 3-way alignment

EN:
Add three failing assertions covering the contract between
crawler-service settings, docker-compose bind targets, and the host-side
download daemon. Drift here regressed since 29918f83 and silently breaks
every GCS download. Tests fail with current code; subsequent commits in
this plan green them by restoring the original 1bb288a7 paths and
unifying env var names.

FR:
Ajout de trois assertions échouantes couvrant le contrat entre la
config crawler-service, les bind targets docker-compose et le daemon de
download côté hôte. Le drift régresse depuis 29918f83 et casse
silencieusement tout download GCS. Les tests échouent sur le code
actuel ; les commits suivants de ce plan les passent en vert en
restaurant les chemins originaux du 1bb288a7 et en unifiant les noms de
variables d'environnement.
```

Run:
```bash
git add apps-microservices/crawler-service/tests/test_config_paths.py
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

### Task 2: Restore Python container path defaults

**Goal:** Green the first two assertions by restoring the `1bb288a7` defaults in `pydantic_settings.BaseSettings`.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/config.py` (lines 33-35)

**Acceptance Criteria:**
- [ ] `settings.DOWNLOAD_REQUESTS_PATH == "/app/download_requests"`.
- [ ] `settings.DOWNLOAD_RESULTS_PATH == "/app/download_results"`.
- [ ] Inline comment documents the contract with `docker-compose.yml`.
- [ ] `test_download_requests_path_matches_compose_bind_target` and `test_download_results_path_matches_compose_bind_target` pass. `test_download_daemon_uses_canonical_env_var_names` still fails (deferred to Task 3).

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_config_paths.py -v` → 2 PASS, 1 FAIL.

**Steps:**

- [ ] **Step 2.1: Edit `config.py`**

In `apps-microservices/crawler-service/app/core/config.py`, replace the existing block at lines 33-35:

```python
    # GCS download daemon paths
    DOWNLOAD_REQUESTS_PATH: str = "/app/gcs-requests"
    DOWNLOAD_RESULTS_PATH: str = "/app/gcs-downloads"
```

with:

```python
    # GCS download daemon paths (must match docker-compose.yml bind target
    # for the crawler-service container; tools/download_daemon.sh reads the
    # same env var names on the host)
    DOWNLOAD_REQUESTS_PATH: str = "/app/download_requests"
    DOWNLOAD_RESULTS_PATH: str = "/app/download_results"
```

- [ ] **Step 2.2: Run the regression test**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_config_paths.py -v`

Expected:
- `test_download_requests_path_matches_compose_bind_target` PASS
- `test_download_results_path_matches_compose_bind_target` PASS
- `test_download_daemon_uses_canonical_env_var_names` FAIL (daemon still on legacy var names — fixed in Task 3)

- [ ] **Step 2.3: Run the full crawler-service suite (excluding pre-existing broken locally)**

Run:
```bash
cd apps-microservices/crawler-service
python -m pytest --ignore=tests/test_api.py --ignore=tests/test_domain_fr.py --ignore=tests/test_routes_invalid_page.py -q
```

Expected: pre-existing pass count unchanged, plus 2 new passes from Task 1 test file (`test_config_paths.py` shows 2 PASS, 1 FAIL — the daemon test is still red).

(The three ignored files are documented in `~/.claude/primer.md` as pre-existing broken locally due to cp1252/fastText/import-path issues unrelated to this change.)

- [ ] **Step 2.4: Commit the config fix**

Generate bilingual commit message in `.git/COMMIT_EDITMSG`:

```
fix(crawler-service): restore GCS download paths to compose bind targets

EN:
Restore DOWNLOAD_REQUESTS_PATH and DOWNLOAD_RESULTS_PATH defaults to
/app/download_requests and /app/download_results (the docker-compose
bind target). The 29918f83 pydantic-settings refactor silently renamed
these to /app/gcs-requests and /app/gcs-downloads in March, causing
every GCS download (archived crawl results + update-mode restoration)
to 504 unless .env masked the regression. Inline comment now documents
the contract with docker-compose.yml so a future refactor cannot drift
again without a code review catching it. Daemon env var rename in next
commit.

FR:
Restaurer les valeurs par défaut DOWNLOAD_REQUESTS_PATH et
DOWNLOAD_RESULTS_PATH vers /app/download_requests et
/app/download_results (la bind target docker-compose). Le refactor
pydantic-settings du 29918f83 a silencieusement renommé ces valeurs en
/app/gcs-requests et /app/gcs-downloads en mars, ce qui fait que tout
download GCS (résultats de crawls archivés + restauration mode update)
termine en 504 sauf si .env masque la régression. Un commentaire en
ligne documente désormais le contrat avec docker-compose.yml pour
qu'un futur refactor ne puisse pas dériver à nouveau sans qu'une revue
de code le détecte. Renommage de la variable d'environnement du daemon
dans le prochain commit.
```

Run:
```bash
git add apps-microservices/crawler-service/app/core/config.py
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

### Task 3: Rename daemon env var to canonical names

**Goal:** Green the third assertion by renaming the daemon env var read from `*_DIR` to `*_PATH`, unifying with the Python side.

**Files:**
- Modify: `tools/download_daemon.sh` (lines 17-21)

**Acceptance Criteria:**
- [ ] Daemon reads `DOWNLOAD_REQUESTS_PATH` instead of `DOWNLOAD_REQUESTS_DIR`.
- [ ] Daemon reads `DOWNLOAD_RESULTS_PATH` instead of `DOWNLOAD_RESULTS_DIR`.
- [ ] Default host paths (`crawler_download_requests/`, `crawler_download_results/`) unchanged.
- [ ] All three regression tests pass.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_config_paths.py -v` → 3 PASS.

**Steps:**

- [ ] **Step 3.1: Edit `download_daemon.sh`**

In `tools/download_daemon.sh`, replace the existing block at lines 17-21:

```bash
DEFAULT_REQUESTS_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_download_requests"
REQUESTS_DIR="${DOWNLOAD_REQUESTS_DIR:-$DEFAULT_REQUESTS_DIR}"

DEFAULT_RESULTS_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_download_results"
RESULTS_DIR="${DOWNLOAD_RESULTS_DIR:-$DEFAULT_RESULTS_DIR}"
```

with:

```bash
DEFAULT_REQUESTS_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_download_requests"
REQUESTS_DIR="${DOWNLOAD_REQUESTS_PATH:-$DEFAULT_REQUESTS_DIR}"

DEFAULT_RESULTS_DIR="$(dirname "$0")/../apps-microservices/crawler-service/crawler_download_results"
RESULTS_DIR="${DOWNLOAD_RESULTS_PATH:-$DEFAULT_RESULTS_DIR}"
```

(Only the `${...:-...}` env var name on the right-hand side of each assignment changes. Defaults and shell variable names — `REQUESTS_DIR`, `RESULTS_DIR`, `DEFAULT_REQUESTS_DIR`, `DEFAULT_RESULTS_DIR` — remain identical so downstream uses inside the script require no further edits.)

- [ ] **Step 3.2: Syntax check the daemon**

Run: `bash -n tools/download_daemon.sh`

Expected: no output (script is syntactically valid).

- [ ] **Step 3.3: Confirm the rest of the script still references the unchanged shell variables**

Run: `grep -nE 'REQUESTS_DIR|RESULTS_DIR' tools/download_daemon.sh`

Expected output (line numbers approximate):
```
17:DEFAULT_REQUESTS_DIR=...
18:REQUESTS_DIR="${DOWNLOAD_REQUESTS_PATH:-$DEFAULT_REQUESTS_DIR}"
20:DEFAULT_RESULTS_DIR=...
21:RESULTS_DIR="${DOWNLOAD_RESULTS_PATH:-$DEFAULT_RESULTS_DIR}"
40:mkdir -p "$REQUESTS_DIR" "$RESULTS_DIR"
43:echo "Watching requests: $REQUESTS_DIR"
44:echo "Writing results:   $RESULTS_DIR"
49:    find "$REQUESTS_DIR" -maxdepth 1 -name "*.request" -print0 | while IFS= read -r -d '' request_file; do
54:        target_path="$RESULTS_DIR/$crawl_id.tar.gz"
55:        done_marker="$RESULTS_DIR/$crawl_id.done"
56:        error_marker="$RESULTS_DIR/$crawl_id.error"
```

Confirm: no remaining references to `DOWNLOAD_REQUESTS_DIR` or `DOWNLOAD_RESULTS_DIR` (the env var names) anywhere in the script.

- [ ] **Step 3.4: Run the regression test**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_config_paths.py -v`

Expected: 3 PASS.

- [ ] **Step 3.5: Run the full crawler-service suite**

Run:
```bash
cd apps-microservices/crawler-service
python -m pytest --ignore=tests/test_api.py --ignore=tests/test_domain_fr.py --ignore=tests/test_routes_invalid_page.py -q
```

Expected: pre-existing pass count unchanged, plus 3 new passes from `test_config_paths.py`.

- [ ] **Step 3.6: Static scope check — no legacy references anywhere**

Run:
```bash
git grep -nE "DOWNLOAD_REQUESTS_DIR|DOWNLOAD_RESULTS_DIR|/app/gcs-requests|/app/gcs-downloads" -- ':!docs' ':!graphify-out' ':!*.md' ':!*.tasks.json'
```

Expected output: empty.

(Spec design doc + this plan doc + `.tasks.json` legitimately reference the legacy names as historical context; the `:!docs` `:!*.md` `:!*.tasks.json` exclusions filter them out.)

- [ ] **Step 3.7: Commit the daemon rename**

Generate bilingual commit message in `.git/COMMIT_EDITMSG`:

```
fix(crawler-service): unify daemon env var names with Python config

EN:
Rename download_daemon.sh env var read from DOWNLOAD_REQUESTS_DIR /
DOWNLOAD_RESULTS_DIR to DOWNLOAD_REQUESTS_PATH / DOWNLOAD_RESULTS_PATH
to match the Python settings names. Operators no longer need to set
both pairs in .env — a single name per direction now configures both
layers. Hard rename per spec §5.2; legacy _DIR variant fully removed.
Default host paths unchanged so the daemon picks up the compose bind
source out of the box. Migration note for operators with the legacy
var set is in spec §6.

FR:
Renommer la lecture des variables d'environnement de
download_daemon.sh de DOWNLOAD_REQUESTS_DIR / DOWNLOAD_RESULTS_DIR vers
DOWNLOAD_REQUESTS_PATH / DOWNLOAD_RESULTS_PATH pour correspondre aux
noms du settings Python. Les opérateurs n'ont plus besoin de définir
les deux paires dans .env — un seul nom par direction configure
désormais les deux couches. Renommage dur conformément à la spec §5.2 ;
l'ancienne variante _DIR est totalement supprimée. Les chemins par
défaut côté hôte ne changent pas, donc le daemon récupère la bind
source compose immédiatement. La note de migration pour les opérateurs
ayant l'ancienne variable est dans la spec §6.
```

Run:
```bash
git add tools/download_daemon.sh
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

## Post-Plan Operator Action (Not Part of the Plan)

Per spec §6 / §7.4, after deploy + daemon restart, the operator runs a manual smoke test on staging:

1. Identify an archived `crawl_id`: `GET /status?status=archived` → pick any entry.
2. `curl -fsS https://staging/crawler-service/results/<crawl_id> -o /tmp/x.tar.gz` → expect HTTP 200, non-empty tar.
3. Negative case: stop daemon → expect 504 with "Ensure the download daemon is running" → restart daemon → expect 200.

This is operator-driven and outside the scope of the implementation plan.

---

## Self-Review

**Spec coverage check:**
- Spec §2 goal "restore original defaults" → Task 2.
- Spec §2 goal "unify env var names" → Task 3.
- Spec §2 goal "regression test asserting three layers stay aligned" → Task 1.
- Spec §5.1 `config.py` change → Task 2 step 2.1.
- Spec §5.2 `download_daemon.sh` change → Task 3 step 3.1.
- Spec §5.3 compose no change → reflected in File Structure table.
- Spec §6 migration note → out of plan scope (operator action), documented in Post-Plan section.
- Spec §7.1 unit test (3 cases) → Task 1 step 1.1.
- Spec §7.2 static scope check → Task 3 step 3.6.
- Spec §7.3 existing suite check → Task 2 step 2.3 + Task 3 step 3.5.
- Spec §7.4 operator smoke → Post-Plan.
- Spec §8 deploy gate → out of plan scope (deploy/operator).
- Spec §9 risks → mitigated by §6 migration note (out of plan scope).
- All spec requirements covered.

**Placeholder scan:** no TBD / TODO / "add appropriate handling" / unspecified code blocks.

**Type/name consistency:** test function names match across Task 1 step 1.1 + Task 2 verify + Task 3 verify. Env var names match across Task 1 assertions + Task 3 step 3.1. Path strings match across Task 1 assertions + Task 2 step 2.1.

No issues found.
