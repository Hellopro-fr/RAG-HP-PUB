# Design: GCS Archive Quarantine Remediation — Two-Phase Runbook

**Date:** 2026-04-22
**Service:** `tools/gcs_archive_audit.py` + operational runbook
**Status:** Approved

## Problem

A 2026-04-19 run of `gcs_archive_audit.py --quarantine crawls-quarantine/ --yes` classified 117 archives and moved 99 to `gs://{bucket}/crawls-quarantine/`. Breakdown:

| Category | Count |
|---|---|
| OK | 18 |
| CORRUPTED | 14 |
| ROW_COUNT_MISMATCH | 75 |
| WRONG_NAME | 10 |
| **Total** | **117** |

The quarantine ratio (85%) is alarming on its face. On inspection, the `ROW_COUNT_MISMATCH` bucket turns out to be heterogeneous: about half (~37 of 75) appear to be classifier false positives, not real data loss. Meanwhile, 10 `.tar.gz` files currently sit in `apps-microservices/crawler-service/crawler_archives/` awaiting the upload daemon — several of them overlap with crawl_ids that have CORRUPTED or WRONG_NAME entries in GCS.

Crucially, **re-crawl is not a free recovery path**. Affected domains have downstream processes already committed to the data; the only re-ingestion channel is the crawler's existing "update mode." Every irreversible deletion is a genuine loss.

## Goals

1. Unblock `crawls/` for downstream consumers (fix the duplicate/corrupted pairs, land pending locals).
2. Preserve optionality on ambiguous archives — nothing destructive until the classifier is trustworthy.
3. Fix the three classifier bugs so future audits don't false-positive.
4. Produce an actionable list of crawl_ids that genuinely need update-mode re-ingestion.

## Non-goals

- Scheduling or triggering update-mode runs (operator action; outside this runbook).
- Designing a middle-bucket (5–30% deficit) policy — deferred to a follow-up ticket.
- Changing the crawler, upload daemon, or downstream pipelines. This runbook only touches the audit tool and the quarantine prefix.

## Constraints

- **No free re-crawl.** Update-mode is the only recovery path for unrecoverable data.
- **Current state is safe.** The prior audit used `--quarantine`, not `--delete`. Every bad archive is isolated but intact.
- **Classifier has known false positives** (~37 archives across 3 distinct bugs):
  - Domain-resolver overcount (`actual > expected`)
  - `expected == 0, actual > 0` (failed crawl with residue)
  - Small drift (deficit within ±5%)
- **Quarantine prefix is the primary staging ground.** No work in `crawls/` until we're confident.

## Conventions

Throughout this spec `{bucket}` stands for the actual GCS bucket name (the `GCS_BUCKET_NAME` env var used by the upload/download daemons and by `tools/gcs_archive_audit.py`). Shell snippets use `$BUCKET` expected to be set to the same value.

## Key sources of truth

- **Source report:** `corrected_report.json` from 2026-04-19 (to be backed up to `gs://{bucket}/remediation/2026-04-19_corrected_report.json` during pre-flight).
- **Upload daemon:** `tools/upload_daemon.sh` — no `--no-clobber`, so `gcloud storage cp` overwrites by default. Confirmed via `gcloud storage cp --help` (SDK 565.0.0).
- **Crawler archive fix (context):** commits `ea45f9b4` + `a3629724` isolate in-progress archives to a `.staging/` subdirectory. The GCS `.tmp.tar.gz` entries are residue from before that fix — not ongoing.

## High-level plan

Two phases, parallelizable after Phase 1B.

### Phase 1 — unblock `crawls/`
- **1A** Let the upload daemon process 10 pending locals → repopulate `crawls/{id}.tar.gz` for 10 crawl_ids.
- **1B** Delete the two `.tmp.tar.gz` entries in quarantine whose main counterpart classifies OK (`4365.tmp`, `5934.tmp`).
- **1C** Produce an update-mode re-ingestion queue JSON and upload to `gs://{bucket}/remediation/`.

### Phase 2 — fix classifier, re-audit, surgically restore
- **2.0** Investigate (confirm hypotheses against real archives).
- **2.1** Three classifier fixes + TDD.
- **2.2** Re-audit `crawls-quarantine/`.
- **2.3** Surgically restore reclassified-OK archives to `crawls/`.
- **2.4** Middle-bucket decision (follow-up, out of scope).

## Pre-flight checks (before any Phase 1 action)

1. **Bucket versioning:**
   ```bash
   gcloud storage buckets describe gs://{bucket} --format="value(versioning.enabled)"
   ```
   If `False`, every delete is permanent — raises the bar for Phase 1B.
2. **Upload daemon running** on the host that owns `crawler_archives/`, and no crawler currently writing one of the 10 pending filenames.
3. **Snapshot the quarantine prefix:**
   ```bash
   gcloud storage ls -l gs://{bucket}/crawls-quarantine/ > quarantine_snapshot_$(date +%Y-%m-%d).txt
   ```
4. **Back up the source report:**
   ```bash
   gcloud storage cp corrected_report.json \
       gs://{bucket}/remediation/2026-04-19_corrected_report.json
   ```

## Phase 1A — Pending-Local Upload

### Scope

Have the upload daemon ship these 10 files from `apps-microservices/crawler-service/crawler_archives/` to `gs://{bucket}/crawls/{id}.tar.gz`:

| crawl_id | Prior GCS state (now in `crawls-quarantine/`) | Post-upload outcome |
|---|---|---|
| 1806 | `.tar.gz` CORRUPTED + `.tmp.tar.gz` WRONG_NAME | Fresh `crawls/1806.tar.gz`. |
| 2517 | same pattern | Fresh `crawls/2517.tar.gz`. |
| 4683 | same pattern | Fresh `crawls/4683.tar.gz`. |
| 4699 | same pattern | Fresh `crawls/4699.tar.gz`. |
| 5250 | `.tmp.tar.gz` only | Fresh `crawls/5250.tar.gz`. |
| 5643 | `.tmp.tar.gz` only (199 MB) | Fresh `crawls/5643.tar.gz`. |
| 4606 | not in GCS | Fresh `crawls/4606.tar.gz`. |
| 5362 | not in GCS | Fresh `crawls/5362.tar.gz`. |
| 6171 | not in GCS | Fresh `crawls/6171.tar.gz`. |
| 6207 | not in GCS | Fresh `crawls/6207.tar.gz`. |

### Pre-upload sanity

Before trusting the daemon:

```bash
for f in apps-microservices/crawler-service/crawler_archives/*.tar.gz; do
  echo "=== $f ==="
  ls -la "$f"
  tar -tzf "$f" 2>&1 | head -10
  echo
done
```

Confirm each file: non-zero size, opens cleanly, contains `_callback_payload.json` + `_completion_marker.json` + `storage/datasets/…`. Any failure → `mv {file} crawler_archives/dead_letter/` so the daemon doesn't ship it. The crawl_id joins the update-mode queue instead.

### Execution

1. Verify daemon is running (pre-flight #2).
2. Let it run on its 60 s poll cycle. Tail logs for 10 `Upload successful` lines.
3. On success, the daemon deletes the local file automatically (`upload_daemon.sh:55`).
4. On 3-strike failure, the file lands in `crawler_archives/dead_letter/`. Diagnose manually (auth, network, daemon user).

### Post-upload verification

Requires the `--include-ids` flag addition (see Tool Changes). Target audit:

```bash
python tools/gcs_archive_audit.py --bucket "$BUCKET" \
    --include-ids 1806,2517,4606,4683,4699,5250,5362,5643,6171,6207 \
    --output phase1a_verification.json

gcloud storage cp phase1a_verification.json \
    gs://{bucket}/remediation/phase1a_verification_$(date +%Y-%m-%d).json
```

**Acceptance:** all 10 classify as OK. (This step requires the Phase 2.1 classifier fixes to have already landed — see "Sequencing notes" below. Without them, a fresh upload with an ±5 % drift would false-flag as `ROW_COUNT_MISMATCH` and muddy the acceptance signal.) Any CORRUPTED / MISSING_* / real `ROW_COUNT_MISMATCH` → rollback that ID:
```bash
gcloud storage mv gs://{bucket}/crawls/{id}.tar.gz gs://{bucket}/crawls-quarantine-rejected/{id}.tar.gz
```
Add that crawl_id to the Phase 1C update-mode queue.

### Risks

- **Local itself corrupted** — sanity pre-check catches most cases. Post-upload audit is the second line.
- **Daemon uploads a stale/older version** (for `1806/2517/4683/4699` where a retry history exists) — mtime + `tar -tzf` check mitigates. Post-upload audit catches remaining cases.
- **No data is lost.** Destinations in `crawls/` are empty thanks to the prior quarantine; uploads create fresh objects.

### Deliverable

`gs://{bucket}/remediation/phase1a_verification_YYYY-MM-DD.json` — the per-ID classification of the 10 fresh uploads.

## Phase 1B — Safe `.tmp` Deletes

### Scope

Delete exactly two objects from `crawls-quarantine/`:

- `gs://{bucket}/crawls-quarantine/4365.tmp.tar.gz` (11 MB)
- `gs://{bucket}/crawls-quarantine/5934.tmp.tar.gz` (3.2 MB)

Both are the only `.tmp.tar.gz` WRONG_NAME entries whose `.tar.gz` main counterpart is OK with matching row counts:

| crawl_id | main category (still in `crawls/`) | row count | tmp to delete |
|---|---|---|---|
| 4365 | OK | 2495 / 2495 | `4365.tmp.tar.gz` |
| 5934 | OK | 541 / 541 | `5934.tmp.tar.gz` |

The `.tmp.tar.gz` is pre-fix race residue; the verified-OK main carries the same data.

**Every other WRONG_NAME entry stays quarantined** because its main is either missing, CORRUPTED, or ROW_COUNT_MISMATCH — which means the `.tmp` sibling may still carry unique data worth inspecting in Phase 2.

### Execution

Pre-delete sanity (idempotent):

```bash
BUCKET=<your bucket>
for id in 4365 5934; do
  echo "--- ${id} ---"
  gcloud storage ls -l "gs://${BUCKET}/crawls/${id}.tar.gz" \
    || { echo "ABORT: main ${id} not in crawls/"; exit 1; }
  gcloud storage ls -l "gs://${BUCKET}/crawls-quarantine/${id}.tmp.tar.gz" \
    || { echo "ABORT: tmp ${id} not in crawls-quarantine/"; exit 1; }
done
```

Re-audit the two mains today (not just trust the 2026-04-19 report):

```bash
python tools/gcs_archive_audit.py --bucket "$BUCKET" \
    --include-ids 4365,5934 \
    --output phase1b_preflight.json
```

If either regressed from OK, **abort**. The `.tmp` sibling stays until we understand why the main changed.

Delete:

```bash
for id in 4365 5934; do
  gcloud storage rm "gs://${BUCKET}/crawls-quarantine/${id}.tmp.tar.gz"
done
```

Verify:

```bash
for id in 4365 5934; do
  gcloud storage ls "gs://${BUCKET}/crawls-quarantine/${id}.tmp.tar.gz" 2>&1 \
    | grep -q "not found\|One or more URLs" \
    && echo "${id}: removed" \
    || { echo "FAIL: ${id} still present"; exit 1; }
done
```

### Risks

- **Versioning off** + wrong delete → unrecoverable. Pre-flight #1 surfaces this. Still defensible here because the data duplicates a verified-OK main.
- **Main regressed between report and now** — re-audit catches this.
- **No meaningful rollback.** The `.tmp` carries no information beyond the OK main.

### Deliverable

`gs://{bucket}/remediation/phase1b_log_YYYY-MM-DD.md` with the preflight JSON result and the two deletion timestamps.

## Phase 1C — Update-Mode Re-Ingestion Queue

### Scope

Produce `gs://{bucket}/remediation/update_mode_queue_YYYY-MM-DD.json` listing crawl_ids that need re-ingestion via update-mode. No bucket mutations. No scheduling — the runbook stops at the JSON handoff.

### Inclusion rules

A crawl_id enters `entries` (actionable now) if **any** of:

1. **CORRUPTED with no local replacement.** From the 14 CORRUPTED entries, exclude the 4 covered by Phase 1A (`1806, 2517, 4683, 4699`) — pending their verification result. Expect ~10 IDs: `1427, 1933, 3437, 3559, 3733, 3743, 3775, 4027, 4058, 4066`.
2. **Major under-delivery.** `ROW_COUNT_MISMATCH` with `(expected - actual) / expected > 0.30`, excluding excess (`actual > expected`) and `expected == 0`. Expect ~14 IDs: `1714, 1741, 1941, 3975, 4345, 4469, 4658, 4672, 4701, 4760, 5385, 6011, 6067, 6223`.

The 30% cutoff falls in a natural gap in the report (no entries between 32 % — `6067` — and 37.7 % — `4701`). Revisable post-Phase-2.

### Exclusion rules (go to `deferred_to_phase2`)

- Minor/borderline under-delivery (deficit ≤ 30 %).
- Excess (`actual > expected`: `3487, 3717, 4105, 4115, 4525, 4782, 5415`) — Phase 2 domain-resolver fix will reclassify most as OK.
- `expected == 0` (`4398, 4413, 4769, 6054, 6082`) — Phase 2 classifier fix.
- Crawl_ids with a `.tmp.tar.gz` sibling that may carry more data (`4347, 4478`) — Phase 2 inspects before deciding.
- Phase 1A upload failures — append at the very end.

### Artifact format

```json
{
  "generated_at": "2026-04-22T...",
  "source_report": "gs://{bucket}/remediation/2026-04-19_corrected_report.json",
  "generator": "tools/build_update_mode_queue.py@<git-sha>",
  "entries": [
    {
      "crawl_id": "1427",
      "reason": "CORRUPTED",
      "detail": "EOFError: Compressed file ended before end-of-stream marker",
      "quarantine_uri": "gs://{bucket}/crawls-quarantine/1427.tar.gz",
      "notes": []
    },
    {
      "crawl_id": "1714",
      "reason": "MAJOR_UNDER_DELIVERY",
      "detail": "expected=5789 actual=478 deficit=91.7%",
      "quarantine_uri": "gs://{bucket}/crawls-quarantine/1714.tar.gz",
      "notes": []
    }
  ],
  "deferred_to_phase2": [
    {"crawl_id": "2754", "reason": "MINOR_UNDER_DELIVERY", "detail": "267/265 deficit=0.7%"},
    {"crawl_id": "3487", "reason": "EXCESS_LIKELY_CLASSIFIER_BUG", "detail": "expected=35 actual=1426"},
    {"crawl_id": "4398", "reason": "EXPECTED_ZERO_LIKELY_CLASSIFIER_BUG", "detail": "expected=0 actual=108"},
    {"crawl_id": "4347", "reason": "HOLD_TMP_SIBLING", "detail": "inspect .tmp sibling before scheduling"}
  ]
}
```

### Generator script

New committed `tools/build_update_mode_queue.py`:

```
python tools/build_update_mode_queue.py \
    --input corrected_report.json \
    --exclude-ids 1806,2517,4683,4699 \
    --deficit-threshold 0.30 \
    --output update_mode_queue.json \
    --upload gs://{bucket}/remediation/update_mode_queue_$(date +%Y-%m-%d).json
```

Tests (`tools/tests/test_build_update_mode_queue.py`): fixture report with one entry per category → verify each lands in `entries` or `deferred_to_phase2` correctly.

### Execution

1. Phase 1A must have completed. Record which of `1806, 2517, 4683, 4699` passed verification → pass to `--exclude-ids`.
2. Run the generator. Sanity-check output (~23 entries, spot-check 2–3).
3. Upload to GCS.
4. Hand URI to whoever schedules update-mode.

### Deliverable

`tools/build_update_mode_queue.py` + tests committed. `gs://{bucket}/remediation/update_mode_queue_YYYY-MM-DD.json` with ~23 entries.

## Phase 2 — Classifier Fixes, Re-Audit, Surgical Restore

### Sequencing notes

- **Phase 2.0 + 2.1 (investigation + classifier fixes) should land before Phase 1A verification.** The verification uses the audit tool; it produces cleaner signal against the corrected classifier. Phase 1A's daemon upload itself does not depend on the classifier — only the verification gate does.
- **Phase 1A and 1B must complete before Phase 2.2 re-audit** (otherwise the two safe tmps would still appear in the re-audit, and any Phase 1A failures wouldn't have been rolled back yet).
- **Phase 1C can run in parallel with Phase 2.2 and 2.3.**

### 2.0 Investigation (before any code change)

Confirm each hypothesis by downloading and inspecting a real archive. If any hypothesis is contradicted, pause and escalate before applying that fix.

**Bug 2A — `actual > expected`.** Pick `3487` (1426 / 35):
```bash
gcloud storage cp gs://{bucket}/crawls-quarantine/3487.tar.gz /tmp/3487.tar.gz
cd /tmp && mkdir 3487 && tar xzf 3487.tar.gz -C 3487
cat 3487/_callback_payload.json | python -m json.tool
ls 3487/storage/datasets/
find 3487/storage/datasets/{domain}/ -name '*.json' | wc -l
head -3 3487/storage/datasets/{domain}/*.json | less
```
Expected finding: `success` is narrower than "files written" (e.g. excludes error pages, redirects, post-validator failures).

**Bug 2B — `expected == 0, actual > 0`.** Pick `4398`:
```bash
# Same flow. Confirm success=0, check _completion_marker.json.final_status, isError flag.
```
Expected finding: crawl declared failure at the URL level; the archive captured partial residue.

**Bug 2C — deficit ≤ 5 %.** Pick `2754` (267 / 265) and `5441` (21 / 20):
```bash
# Check _status_snapshot.json.urls_crawled (Python's own count).
# If snapshot matches 'actual' and Node's 'success' is +2, drift is Node-side accounting.
```

### 2.1 Classifier fixes (TDD)

Changes inside `inspect_archive` in `tools/gcs_archive_audit.py`:

1. **Skip excess.** `actual > expected` → return `OK`, append secondary tag `EXCESS_FILES`. Keep both counts in details.
2. **Skip expected=0 case.** `expected == 0 and actual > 0` → `OK` + secondary tag `FAILED_CRAWL_WITH_RESIDUE`.
3. **Tolerance.** New CLI `--row-count-tolerance` (default `0.05`). When `0 < (expected - actual) <= expected * tolerance` → `OK` + secondary tag `COUNT_DRIFT`. Only deficits above tolerance remain `ROW_COUNT_MISMATCH`.

### 2.1b Tests (TDD — red first)

Add to `tools/tests/test_gcs_archive_audit.py`:

- `test_ok_with_excess_files_tag` — payload `success=10`, tar has 20 data files → OK, `EXCESS_FILES` in `secondary_tags`.
- `test_ok_with_failed_crawl_residue_tag` — payload `success=0`, tar has 5 data files → OK, `FAILED_CRAWL_WITH_RESIDUE`.
- `test_ok_with_count_drift_within_tolerance` — payload `success=20`, tar has 19 → OK, `COUNT_DRIFT`.
- `test_row_count_mismatch_above_tolerance` — payload `success=20`, tar has 15 (25 %) → still `ROW_COUNT_MISMATCH`.
- `test_row_count_tolerance_cli_override` — with `--row-count-tolerance 0.10`: 18 / 20 passes, 17 / 20 still flags.

Existing `test_row_count_mismatch` (5 / 2 = 60 % deficit) still passes untouched.

### 2.2 Re-audit `crawls-quarantine/`

```bash
python tools/gcs_archive_audit.py --bucket "$BUCKET" \
    --prefix crawls-quarantine/ \
    --output quarantine_reaudit_$(date +%Y-%m-%d).json
```

`extract_crawl_id` works on basenames — the non-default prefix needs no code change. Expected reclassification:

| Bucket | Pre-Phase-2 count | Post-fix category |
|---|---|---|
| Small drift (≤ 5 %) | ~35 | **OK + COUNT_DRIFT** |
| Excess (`actual > expected`) | ~7 | **OK + EXCESS_FILES** |
| Expected=0, actual>0 | ~5 | **OK + FAILED_CRAWL_WITH_RESIDUE** |
| Major under-delivery (> 30 %) | ~14 | `ROW_COUNT_MISMATCH` (unchanged) |
| Middle bucket (5–30 %) | ~8 | `ROW_COUNT_MISMATCH` (2.4 decision) |
| CORRUPTED | 14 | unchanged |
| WRONG_NAME | 8 (after 1B) | unchanged |

Roughly **~47 archives become restore candidates**.

### 2.3 Surgical restore

New committed `tools/restore_from_reaudit.py`:

```
python tools/restore_from_reaudit.py \
    --input quarantine_reaudit_YYYY-MM-DD.json \
    --bucket "$BUCKET" \
    --target-prefix crawls/ \
    --log phase2_restore_log.md
```

Core logic:

```python
for entry in reaudit["archives"]:
    if entry["category"] != "OK":
        continue
    src_uri  = f"gs://{bucket}/{entry['object_name']}"                       # crawls-quarantine/xxx.tar.gz
    basename = entry["object_name"].rsplit("/", 1)[-1]
    dst_uri  = f"gs://{bucket}/{target_prefix.rstrip('/')}/{basename}"       # crawls/xxx.tar.gz

    if _exists(dst_uri):
        log(f"SKIP {entry['crawl_id']}: destination already occupied — keeping existing")
        continue
    gcloud_move(src_uri, dst_uri)
    log(f"RESTORED {entry['crawl_id']}: secondary_tags={entry['secondary_tags']}")
```

Tests (`tools/tests/test_restore_from_reaudit.py`): synthesize a fake re-audit JSON with OK + non-OK + collision cases, mock `gcloud_ls` / `gcloud_move`, verify:
- Only OK entries get moved.
- Collisions skipped, logged.
- Non-OK entries left in place.

Collision handling is defensive — in practice no conflicts are expected because Phase 1A crawl_ids (`1806, 2517, 4683, 4699`) are still CORRUPTED in quarantine post-Phase-2 (no classifier fix touches CORRUPTED) and therefore don't reclassify OK.

### 2.4 Middle-bucket decision (out of scope; follow-up ticket)

After 2.3 restores, ~8 archives with 5–30 % deficit remain in `crawls-quarantine/` as `ROW_COUNT_MISMATCH`. Too big for drift, too small for the major cutoff.

Three options the follow-up should evaluate:

- **A. Extend Phase 1C queue** with a lower threshold (e.g. `--deficit-threshold 0.05`).
- **B. Leave quarantined indefinitely.**
- **C. Per-archive inspection** (recommended — 8 archives is cheap to eyeball).

### Deliverables

- `tools/gcs_archive_audit.py` — three classifier fixes + tests.
- `tools/restore_from_reaudit.py` committed + tests.
- `gs://{bucket}/remediation/quarantine_reaudit_YYYY-MM-DD.json` — the post-fix re-audit.
- `gs://{bucket}/remediation/phase2_restore_log_YYYY-MM-DD.md` — per-ID restore log.
- Follow-up ticket for 2.4.

### Risks

- **A classifier fix hides a real crawler bug.** Mitigation: 2.0 investigation — if drift systematically points to retry-double-counting or fsync races, escalate upstream instead of widening tolerance.
- **Restore moves wrongly.** `gcloud storage mv` is reversible; the log is the paper trail.
- **Re-audit bandwidth.** ~99 archives download. 5–15 minutes on a typical connection. Single-threaded but acceptable for one-off ops.

## Rollback convention

For any recovery attempt that fails audit (Phase 1A rollback, post-restore regression, etc.):

```bash
gcloud storage mv gs://{bucket}/crawls/{id}.tar.gz gs://{bucket}/crawls-quarantine-rejected/{id}.tar.gz
```

Dedicated prefix `crawls-quarantine-rejected/` — separate from `crawls-quarantine/` so `--restore-from-quarantine crawls-quarantine/` can never accidentally re-introduce a known-bad retry. `extract_crawl_id` works unchanged (basename is `{id}.tar.gz`). Likely stays empty if Phase 1A sanity checks hold.

## Tool changes required

Summary of changes committed through this runbook:

### `tools/gcs_archive_audit.py`

- **New CLI flag** `--include-ids {CSV | path/to/ids.txt}` — targeted audit over a subset of crawl_ids. Used by Phases 1A and 1B.
- **Classifier — excess files** — `actual > expected` classifies OK with secondary tag `EXCESS_FILES` (Phase 2.1).
- **Classifier — failed crawl with residue** — `expected == 0 && actual > 0` classifies OK with secondary tag `FAILED_CRAWL_WITH_RESIDUE` (Phase 2.1).
- **Classifier — drift tolerance** — new CLI flag `--row-count-tolerance` (default `0.05`); within-tolerance deficits classify OK with secondary tag `COUNT_DRIFT` (Phase 2.1).

### New scripts

- **`tools/build_update_mode_queue.py`** — reads `corrected_report.json`, applies inclusion rules, produces the update-mode queue JSON (Phase 1C).
- **`tools/restore_from_reaudit.py`** — per-object move from `crawls-quarantine/` back to `crawls/` for entries reclassified OK (Phase 2.3).

### Tests

All additions and new scripts follow the existing TDD pattern in `tools/tests/`. Every new branch of `inspect_archive` has at least one test; both new scripts have a dedicated test module.

## Open questions and known deferrals

- **Middle-bucket policy (5–30 % deficit):** deferred to a follow-up ticket after Phase 2.3 exposes the final count.
- **Update-mode trigger mechanism:** out of scope. The runbook ends at the JSON handoff.
- **`.tmp.tar.gz` siblings of `4347` and `4478`:** flagged in `deferred_to_phase2`. Phase 2 should inspect whether the `.tmp` carries more data than the main before scheduling update-mode for either.

## Runbook order of operations (quick reference)

1. **Pre-flight** (versioning, daemon, snapshot, report backup).
2. **Implement `--include-ids` flag** + tests. Commit.
3. **Phase 2.0 — Investigation.** Download and inspect `3487`, `4398`, `2754` / `5441`. Confirm the three bug hypotheses.
4. **Phase 2.1 — Classifier fixes** (TDD). Three fixes + tests + `--row-count-tolerance` flag. Commit.
5. **Phase 1A — Pending-local upload.** Sanity locals → daemon uploads → verify with `--include-ids` against the corrected classifier.
6. **Phase 1B — Safe `.tmp` deletes.** Pre-flight → re-audit mains → `gcloud storage rm` the two tmps.
7. **Implement `build_update_mode_queue.py`** + tests. Commit.
8. **Phase 1C — Update-mode queue.** Generate → upload to `gs://{bucket}/remediation/` → hand URI to ops.
9. **Phase 2.2 — Re-audit `crawls-quarantine/`** with the corrected classifier.
10. **Implement `restore_from_reaudit.py`** + tests. Commit.
11. **Phase 2.3 — Surgical restore** with collision check.
12. **File follow-up ticket** for the middle-bucket decision (2.4).
