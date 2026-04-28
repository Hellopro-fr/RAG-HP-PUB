# GCS Archive Quarantine Remediation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the 99 archives quarantined by the 2026-04-19 audit run without destructive action on main archives until the classifier is provably correct, while unblocking downstream consumers of `crawls/` immediately.

**Architecture:** Two-phase operational runbook. Phase 1 unblocks `crawls/` (upload 10 pending locals; delete two safe duplicate tmps; produce an update-mode re-ingestion queue for unrecoverable archives). Phase 2 fixes three identified classifier false-positives (`actual > expected`, `expected == 0`, small drift), re-audits the quarantine prefix with the corrected classifier, and surgically moves reclassified-OK archives back to `crawls/`. All destructive actions gated behind verification.

**Tech Stack:** Python 3.10, `pytest`, `argparse`, `gcloud storage` CLI (no google-cloud-storage Python lib), `shutil.make_archive`–compatible tar handling, Bash for ops glue.

**Spec:** `docs/superpowers/specs/2026-04-22-gcs-quarantine-remediation-runbook-design.md`

**Conventions:** `{bucket}` means the actual GCS bucket name. `$BUCKET` in shell snippets is the same. All paths are relative to the repo root (`D:\DevHellopro\Workspaces\RAG-HP-PUB`). Run pytest from the repo root.

---

## Task 0: Phase 0 — Pre-flight Checks

**Goal:** Capture bucket versioning state, confirm upload daemon is running, snapshot the quarantine prefix, back up the source report. No code changes.

**Files:**
- Create: `quarantine_snapshot_$(date +%Y-%m-%d).txt` (local, then uploaded to GCS).
- Upload: `gs://{bucket}/remediation/2026-04-19_corrected_report.json`.

**Acceptance Criteria:**
- [ ] Bucket versioning state recorded in the operator log.
- [ ] Upload daemon confirmed running (or started).
- [ ] `quarantine_snapshot_YYYY-MM-DD.txt` produced locally and uploaded to `gs://{bucket}/remediation/`.
- [ ] `corrected_report.json` copied to `gs://{bucket}/remediation/2026-04-19_corrected_report.json`.

**Verify:**
```bash
gcloud storage ls gs://$BUCKET/remediation/
```
Expected output includes the two uploaded files.

**Steps:**

- [ ] **Step 1: Set environment**

```bash
export BUCKET=<your-bucket-name>            # same value as GCS_BUCKET_NAME in .env
export TODAY=$(date +%Y-%m-%d)
```

- [ ] **Step 2: Check bucket versioning**

```bash
gcloud storage buckets describe gs://$BUCKET --format="value(versioning.enabled)"
```
Expected: `True` or `False`. Record the answer in the operator log. If `False`, flag during any Phase 1B/2.3 delete decision — deletes are permanent.

- [ ] **Step 3: Confirm upload daemon is running**

```bash
ps aux | grep -v grep | grep upload_daemon.sh
```
Expected: one running process. If nothing: start via whatever service manager the host uses (systemd, `nohup`, screen). No crawler should currently be writing any of the 10 pending filenames — quick check:

```bash
ls -la apps-microservices/crawler-service/crawler_archives/
ls -la apps-microservices/crawler-service/crawler_archives/.staging/ 2>/dev/null
```
Expected: 10 `.tar.gz` files directly in `crawler_archives/` (none in `.staging/` with matching names).

- [ ] **Step 4: Snapshot the quarantine prefix**

```bash
gcloud storage ls -l gs://$BUCKET/crawls-quarantine/ > quarantine_snapshot_$TODAY.txt
wc -l quarantine_snapshot_$TODAY.txt
```
Expected: non-empty file (~100 lines including header).

- [ ] **Step 5: Back up the source report**

```bash
gcloud storage cp corrected_report.json \
    gs://$BUCKET/remediation/2026-04-19_corrected_report.json

gcloud storage cp quarantine_snapshot_$TODAY.txt \
    gs://$BUCKET/remediation/quarantine_snapshot_$TODAY.txt
```

- [ ] **Step 6: Verify artifacts present**

```bash
gcloud storage ls gs://$BUCKET/remediation/
```
Expected output lists at least:
- `2026-04-19_corrected_report.json`
- `quarantine_snapshot_$TODAY.txt`

No git commit in this task — artifacts live in GCS.

---

## Task 1: Add `--include-ids` Flag to Audit Tool

**Goal:** Implement a targeted-audit CLI flag on `tools/gcs_archive_audit.py` that filters objects by crawl_id allowlist (CSV string or file path). Used by every subsequent verification task.

**Files:**
- Modify: `tools/gcs_archive_audit.py`
- Modify: `tools/tests/test_gcs_archive_audit.py`

**Acceptance Criteria:**
- [ ] `test_load_include_ids_from_csv_string` passes.
- [ ] `test_load_include_ids_from_file` passes.
- [ ] `test_audit_skips_non_matching_ids` passes (mocked gcloud).
- [ ] `test_include_ids_combined_with_resume` passes.
- [ ] All existing tests in `test_gcs_archive_audit.py` still pass.

**Verify:** `pytest tools/tests/test_gcs_archive_audit.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the four failing tests**

Append to `tools/tests/test_gcs_archive_audit.py`:

```python
class TestIncludeIds:
    def test_load_include_ids_from_csv_string(self):
        result = ga._load_include_ids("1806,2517, 4606 , 5250")
        assert result == {"1806", "2517", "4606", "5250"}

    def test_load_include_ids_from_file(self, tmp_path):
        p = tmp_path / "ids.txt"
        p.write_text("1806\n2517\n\n 4606 \n")
        result = ga._load_include_ids(str(p))
        assert result == {"1806", "2517", "4606"}

    def test_load_include_ids_returns_none_when_no_spec(self):
        assert ga._load_include_ids(None) is None
        assert ga._load_include_ids("") is None

    def test_audit_skips_non_matching_ids(self, tmp_path, monkeypatch):
        listing = [
            (100, "gs://b/crawls/1806.tar.gz"),
            (200, "gs://b/crawls/9999.tar.gz"),
        ]
        def fake_ls(uri, long=False):
            return listing if long else [u for _, u in listing]

        inspected = []
        def fake_inspect_one(obj_uri, size, name_only):
            inspected.append(obj_uri)
            return ga.OK, {}

        monkeypatch.setattr(ga, "gcloud_ls", fake_ls)
        monkeypatch.setattr(ga, "_inspect_one", fake_inspect_one)
        monkeypatch.setattr(ga, "check_gcloud_auth", lambda: None)

        out_path = tmp_path / "out.json"
        ga.main(["--bucket", "b", "--include-ids", "1806", "--output", str(out_path)])

        assert inspected == ["gs://b/crawls/1806.tar.gz"]

    def test_include_ids_combined_with_resume(self, tmp_path, monkeypatch):
        listing = [
            (100, "gs://b/crawls/1806.tar.gz"),
            (200, "gs://b/crawls/2517.tar.gz"),
        ]
        prior = {"archives": [{"object_name": "crawls/1806.tar.gz"}]}
        prior_path = tmp_path / "prior.json"
        prior_path.write_text(_json.dumps(prior))

        def fake_ls(uri, long=False):
            return listing if long else [u for _, u in listing]

        inspected = []
        def fake_inspect_one(obj_uri, size, name_only):
            inspected.append(obj_uri)
            return ga.OK, {}

        monkeypatch.setattr(ga, "gcloud_ls", fake_ls)
        monkeypatch.setattr(ga, "_inspect_one", fake_inspect_one)
        monkeypatch.setattr(ga, "check_gcloud_auth", lambda: None)

        out_path = tmp_path / "out.json"
        ga.main([
            "--bucket", "b",
            "--include-ids", "1806,2517",
            "--resume", str(prior_path),
            "--output", str(out_path),
        ])
        # 1806 skipped by resume; 2517 allowed by include + not in resume
        assert inspected == ["gs://b/crawls/2517.tar.gz"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tools/tests/test_gcs_archive_audit.py::TestIncludeIds -v
```
Expected: all FAIL. First with `AttributeError: module 'gcs_archive_audit' has no attribute '_load_include_ids'` for the helper tests; later with unrecognized CLI argument for the integration tests.

- [ ] **Step 3: Add the helper function**

In `tools/gcs_archive_audit.py`, add near `_load_resume_set` (the existing loader pattern):

```python
def _load_include_ids(spec: Optional[str]) -> Optional[Set[str]]:
    """Parse --include-ids input. Returns None when no filter, else Set[str].

    Accepts either a path to a file (one crawl_id per line) or a
    comma-separated string. Empty tokens and whitespace are stripped.
    """
    if not spec:
        return None
    p = Path(spec)
    if p.exists():
        return {line.strip() for line in p.read_text().splitlines() if line.strip()}
    return {s.strip() for s in spec.split(",") if s.strip()}
```

- [ ] **Step 4: Wire the CLI flag into `parse_args`**

Add to the argparse block in `parse_args` (near `--resume`):

```python
    parser.add_argument("--include-ids", default=None, metavar="SPEC",
                        help="Comma-separated list of crawl_ids, or path to a file "
                             "with one ID per line. Only audit archives whose "
                             "extracted crawl_id is in this set.")
```

- [ ] **Step 5: Wire the filter into `main`**

In `main()`, just after `skip_set = _load_resume_set(args.resume)` add:

```python
    include_ids = _load_include_ids(args.include_ids)
```

Inside the main loop `for size_bytes, obj_uri in listing:`, after the `skip_set` check and before `if args.limit is not None`:

```python
        if include_ids is not None:
            cid = extract_crawl_id(obj_uri)
            if cid not in include_ids:
                continue
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tools/tests/test_gcs_archive_audit.py -v
```
Expected: all tests (existing + new) PASS.

- [ ] **Step 7: Commit**

```bash
git add tools/gcs_archive_audit.py tools/tests/test_gcs_archive_audit.py
git commit -m "$(cat <<'EOF'
feat(tools): add --include-ids flag to gcs_archive_audit.py

Enables targeted audit over a subset of crawl_ids (CSV string or
one-per-line file path). Used by the quarantine-remediation runbook
for post-upload and post-restore verification without re-auditing the
full prefix.

---

feat(tools): ajout du flag --include-ids a gcs_archive_audit.py

Permet un audit cible sur un sous-ensemble de crawl_ids (chaine CSV ou
fichier avec un ID par ligne). Utilise par le runbook de remediation de
la quarantaine pour la verification post-upload et post-restauration
sans re-auditer le prefixe complet.
EOF
)"
```

---

## Task 2: Phase 2.0 + 2.1 — Investigate and Fix Classifier

**Goal:** Confirm three hypothesized classifier bugs against real archives, then apply the three fixes TDD-style.

**Files:**
- Modify: `tools/gcs_archive_audit.py`
- Modify: `tools/tests/test_gcs_archive_audit.py`
- Upload (investigation notes): `gs://{bucket}/remediation/phase2_investigation_YYYY-MM-DD.md`

**Acceptance Criteria:**
- [ ] Investigation notes uploaded documenting findings for `3487`, `4398`, and `2754` (or `5441`).
- [ ] `test_ok_with_excess_files_tag` passes.
- [ ] `test_ok_with_failed_crawl_residue_tag` passes.
- [ ] `test_ok_with_count_drift_within_tolerance` passes.
- [ ] `test_row_count_mismatch_above_tolerance` passes.
- [ ] `test_row_count_tolerance_cli_override` passes.
- [ ] Existing `test_row_count_mismatch` (5/2, 60% deficit) still passes untouched.
- [ ] `actions_taken` and `secondary_tags` propagate correctly from `details` into `entry` in `main`.

**Verify:** `pytest tools/tests/test_gcs_archive_audit.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Investigation — Bug 2A (`actual > expected`)**

Pick `3487` (1426 / 35):

```bash
cd /tmp
mkdir -p inv_3487 && cd inv_3487
gcloud storage cp gs://$BUCKET/crawls-quarantine/3487.tar.gz .
tar xzf 3487.tar.gz
python -m json.tool _callback_payload.json | head -20
ls storage/datasets/
DOMAIN=$(ls storage/datasets/ | grep -vE '^(nfr-|error-|update-)' | head -1)
echo "Main domain: $DOMAIN"
find "storage/datasets/$DOMAIN" -name '*.json' -type f | wc -l
head -3 "storage/datasets/$DOMAIN"/*.json | head -30
```
Expected finding: Node's `success` counts a narrower set than "files written" (e.g. excludes error pages, redirects, or content that failed a post-validator). If contradicted (e.g. `success=35` is correct and 1391 extra files are actual garbage), STOP and escalate before coding.

- [ ] **Step 2: Investigation — Bug 2B (`expected=0, actual>0`)**

Pick `4398`:

```bash
cd /tmp
mkdir -p inv_4398 && cd inv_4398
gcloud storage cp gs://$BUCKET/crawls-quarantine/4398.tar.gz .
tar xzf 4398.tar.gz
python -m json.tool _callback_payload.json
python -m json.tool _completion_marker.json
find storage/datasets -name '*.json' | head -5
```
Expected: `success=0, failed>0`, marker says `final_status != "finished"` or `isError != ""`. Residue files present. Confirms the crawl genuinely failed at the URL level but partial data was archived.

- [ ] **Step 3: Investigation — Bug 2C (small drift)**

Pick `2754` (267/265):

```bash
cd /tmp
mkdir -p inv_2754 && cd inv_2754
gcloud storage cp gs://$BUCKET/crawls-quarantine/2754.tar.gz .
tar xzf 2754.tar.gz
python -m json.tool _callback_payload.json | grep -E 'success|failed'
python -m json.tool _status_snapshot.json | grep -E 'urls_crawled'
DOMAIN=$(ls storage/datasets/ | grep -vE '^(nfr-|error-|update-)' | head -1)
find "storage/datasets/$DOMAIN" -name '*.json' | wc -l
```
Expected: Python's `urls_crawled` in the snapshot is either 265 (= `actual`, suggests Node overcounts success) or 267 (= `expected`, suggests Python/Node both say 267 but 2 files didn't persist). Either way, the drift is crawler-side accounting; tolerating ≤5% is safe.

- [ ] **Step 4: Upload investigation notes**

Write a short `phase2_investigation_$TODAY.md` (5–10 lines per bug: archive inspected, counts, raw payload snippets, conclusion), then:

```bash
gcloud storage cp phase2_investigation_$TODAY.md \
    gs://$BUCKET/remediation/phase2_investigation_$TODAY.md
```

- [ ] **Step 5: Write failing tests for the three fixes**

Append to `tools/tests/test_gcs_archive_audit.py` inside a new class:

```python
class TestClassifierBugFixes:
    def _tar_with_files(self, tmp_path, payload_success, file_count, domain="example.com"):
        files = {
            "_callback_payload.json": _payload(success=payload_success),
            "_completion_marker.json": _marker(),
        }
        files.update({
            f"storage/datasets/{domain}/url{i}.json": b'{"url": "a"}'
            for i in range(file_count)
        })
        return _build_tar(tmp_path, files)

    def test_ok_with_excess_files_tag(self, tmp_path):
        path = self._tar_with_files(tmp_path, payload_success=10, file_count=20)
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert "EXCESS_FILES" in details.get("secondary_tags", [])
        assert details["expected_count"] == 10
        assert details["actual_count"] == 20

    def test_ok_with_failed_crawl_residue_tag(self, tmp_path):
        path = self._tar_with_files(tmp_path, payload_success=0, file_count=5)
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert "FAILED_CRAWL_WITH_RESIDUE" in details.get("secondary_tags", [])

    def test_ok_with_count_drift_within_tolerance(self, tmp_path):
        # 20 expected, 19 actual = 5% deficit, exactly at tolerance
        path = self._tar_with_files(tmp_path, payload_success=20, file_count=19)
        category, details = ga.inspect_archive(path, row_count_tolerance=0.05)
        assert category == ga.OK
        assert "COUNT_DRIFT" in details.get("secondary_tags", [])

    def test_row_count_mismatch_above_tolerance(self, tmp_path):
        # 20 expected, 15 actual = 25% deficit, above 5% tolerance
        path = self._tar_with_files(tmp_path, payload_success=20, file_count=15)
        category, details = ga.inspect_archive(path, row_count_tolerance=0.05)
        assert category == ga.ROW_COUNT_MISMATCH

    def test_row_count_tolerance_cli_override(self):
        args = ga.parse_args(["--bucket", "b", "--row-count-tolerance", "0.10"])
        assert args.row_count_tolerance == pytest.approx(0.10)
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
pytest tools/tests/test_gcs_archive_audit.py::TestClassifierBugFixes -v
```
Expected: all FAIL — either `row_count_tolerance` kwarg unknown, or classifier still returns `ROW_COUNT_MISMATCH` for the excess / zero / drift cases.

- [ ] **Step 7: Modify `inspect_archive` signature and classifier logic**

In `tools/gcs_archive_audit.py`, change `inspect_archive`:

```python
def inspect_archive(
    local_tar_path: Path,
    row_count_tolerance: float = 0.05,
) -> Tuple[str, Dict]:
```

Find the final block where `int(expected) != actual` flags `ROW_COUNT_MISMATCH`:

```python
        if int(expected) != actual:
            return ROW_COUNT_MISMATCH, details
        return OK, details
```

Replace with:

```python
        details["expected_count"] = int(expected)
        details["actual_count"] = actual

        if actual > int(expected):
            details.setdefault("secondary_tags", []).append("EXCESS_FILES")
            return OK, details
        if int(expected) == 0:
            # actual > 0 here (actual > expected branch above handled actual > 0 with expected=0
            # already, but keep this guard for clarity — expected=0 && actual=0 reached only if
            # both zero, treated as OK without tag)
            if actual > 0:
                details.setdefault("secondary_tags", []).append("FAILED_CRAWL_WITH_RESIDUE")
            return OK, details

        deficit = int(expected) - actual
        if deficit > 0 and deficit <= int(expected) * row_count_tolerance:
            details.setdefault("secondary_tags", []).append("COUNT_DRIFT")
            return OK, details
        if deficit > 0:
            return ROW_COUNT_MISMATCH, details
        return OK, details
```

Note: when the earlier branch already set `details["expected_count"]/actual_count` (e.g. in the domain-unresolved warning path), do not double-assign. Inspect the function body to ensure only the post-check-enabled branch touches these keys.

- [ ] **Step 8: Thread `row_count_tolerance` through `_inspect_one`**

```python
def _inspect_one(
    obj_uri: str,
    size_bytes: int,
    name_only: bool,
    row_count_tolerance: float = 0.05,
) -> Tuple[str, Dict]:
    ...
    return inspect_archive(tmp_path, row_count_tolerance=row_count_tolerance)
```

- [ ] **Step 9: Add CLI flag in `parse_args`**

```python
    parser.add_argument("--row-count-tolerance", type=float, default=0.05,
                        metavar="FRACTION",
                        help="Deficit fraction tolerated before flagging "
                             "ROW_COUNT_MISMATCH (default 0.05 = 5%%). "
                             "Archives within tolerance classify OK with "
                             "secondary tag COUNT_DRIFT.")
```

- [ ] **Step 10: Pass it from `main` into `_inspect_one`**

```python
        category, details = _inspect_one(
            obj_uri,
            size_bytes,
            args.name_only,
            row_count_tolerance=args.row_count_tolerance,
        )
```

- [ ] **Step 11: Propagate `details["secondary_tags"]` into the entry**

Immediately after `entry["category"] = category` in `main`, add:

```python
        for tag in details.get("secondary_tags", []):
            if tag not in entry["secondary_tags"]:
                entry["secondary_tags"].append(tag)
```

This runs before `detect_duplicates` appends `DUPLICATE`, so tags coexist without conflict.

- [ ] **Step 12: Run all tests**

```bash
pytest tools/tests/test_gcs_archive_audit.py -v
```
Expected: all PASS, including the pre-existing `test_row_count_mismatch` (5 expected / 2 actual = 60 % deficit → still `ROW_COUNT_MISMATCH` because 60 % > 5 % tolerance).

- [ ] **Step 13: Commit**

```bash
git add tools/gcs_archive_audit.py tools/tests/test_gcs_archive_audit.py
git commit -m "$(cat <<'EOF'
fix(tools): gcs audit classifier — three false-positive fixes

- actual > expected: OK + secondary tag EXCESS_FILES (Node 'success'
  counts a narrower set than files written; excess is not bad data).
- expected == 0, actual > 0: OK + FAILED_CRAWL_WITH_RESIDUE (crawl
  failed at URL level but residue files archived).
- deficit within --row-count-tolerance (default 5%): OK + COUNT_DRIFT
  (crawler-side accounting noise, tolerable at scale).

Deficits above tolerance remain ROW_COUNT_MISMATCH. Existing tests
pass untouched. Investigation artifact at
gs://{bucket}/remediation/phase2_investigation_<date>.md.

---

fix(tools): audit gcs classifier — correction de trois faux positifs

- actual > expected : OK + tag secondaire EXCESS_FILES (le 'success'
  de Node compte moins que les fichiers ecrits ; l'excedent n'est pas
  une anomalie).
- expected == 0, actual > 0 : OK + FAILED_CRAWL_WITH_RESIDUE (crawl
  echoue au niveau URL mais fichiers residuels archives).
- deficit dans --row-count-tolerance (defaut 5%) : OK + COUNT_DRIFT
  (bruit de comptage cote crawler, tolerable a l'echelle).

Les deficits au-dessus de la tolerance restent ROW_COUNT_MISMATCH.
Les tests existants passent inchangees. Artefact d'investigation a
gs://{bucket}/remediation/phase2_investigation_<date>.md.
EOF
)"
```

---

## Task 3: Phase 1A — Upload Pending Locals and Verify

**Goal:** Let the upload daemon process the 10 pending `.tar.gz` files in `apps-microservices/crawler-service/crawler_archives/` and verify each lands OK in `crawls/` using the corrected classifier.

**Files:**
- Produce: `phase1a_verification.json` (local, then uploaded to GCS).
- Upload: `gs://{bucket}/remediation/phase1a_verification_YYYY-MM-DD.json`.

**Acceptance Criteria:**
- [ ] Each of the 10 locals passed the pre-upload sanity check (opens cleanly, has required system files) or was moved to `dead_letter/`.
- [ ] The upload daemon logged `Upload successful` for every passing local (10 or fewer).
- [ ] Targeted audit produces a JSON where every remaining crawl_id classifies as `OK` (optionally with tags `COUNT_DRIFT`, `EXCESS_FILES`, `FAILED_CRAWL_WITH_RESIDUE`). Any `CORRUPTED` / `MISSING_*` / `ROW_COUNT_MISMATCH` rolled back.
- [ ] Verification JSON uploaded to `gs://{bucket}/remediation/`.

**Verify:**
```bash
gcloud storage cat gs://$BUCKET/remediation/phase1a_verification_$TODAY.json | \
    python -c "import sys,json; d=json.load(sys.stdin); \
    print([a['category'] for a in d['archives']])"
```
Expected: all `OK` in the list.

**Steps:**

- [ ] **Step 1: Pre-upload sanity on each local**

```bash
cd apps-microservices/crawler-service/crawler_archives/
for f in *.tar.gz; do
  echo "=== $f ==="
  ls -la "$f"
  if ! tar -tzf "$f" > /tmp/_tar_list 2>&1; then
    echo "FAIL: tar read error"
    continue
  fi
  if ! grep -q '_callback_payload.json' /tmp/_tar_list; then
    echo "FAIL: missing _callback_payload.json"
    continue
  fi
  if ! grep -q '_completion_marker.json' /tmp/_tar_list; then
    echo "FAIL: missing _completion_marker.json"
    continue
  fi
  if ! grep -q 'storage/datasets/' /tmp/_tar_list; then
    echo "FAIL: missing storage/datasets/"
    continue
  fi
  echo "OK"
  echo
done
cd - > /dev/null
```
Any file marked FAIL: move it to `dead_letter/`:
```bash
mkdir -p apps-microservices/crawler-service/crawler_archives/dead_letter/
mv apps-microservices/crawler-service/crawler_archives/{id}.tar.gz \
   apps-microservices/crawler-service/crawler_archives/dead_letter/
```
Record the crawl_id — it joins the Phase 1C queue via the `--exclude-ids` flag (Task 5).

- [ ] **Step 2: Wait for daemon uploads**

The daemon polls every 60 s. For 10 small files it should finish in 2–10 minutes. Monitor:
```bash
tail -f <daemon-log-path> | grep -E 'Found archive|Upload successful|Upload failed'
```
Stop tailing once 10 `Upload successful` lines have scrolled past (or fewer if you moved some to dead_letter in Step 1).

- [ ] **Step 3: Verify uploads landed and locals are gone**

```bash
for id in 1806 2517 4606 4683 4699 5250 5362 5643 6171 6207; do
  gcloud storage ls -l "gs://$BUCKET/crawls/$id.tar.gz" 2>/dev/null \
    && echo "   in crawls/: $id" \
    || echo "   NOT in crawls/: $id"
done
ls apps-microservices/crawler-service/crawler_archives/*.tar.gz 2>/dev/null || \
  echo "all local .tar.gz cleared (expected)"
```

Any expected ID not in `crawls/`: check `dead_letter/` or daemon log for the failure.

- [ ] **Step 4: Run targeted audit**

Use only the IDs that actually landed in `crawls/` (skip any that went to dead_letter). Example assumes all 10 landed:

```bash
python tools/gcs_archive_audit.py --bucket "$BUCKET" \
    --include-ids 1806,2517,4606,4683,4699,5250,5362,5643,6171,6207 \
    --output phase1a_verification.json
```

- [ ] **Step 5: Inspect verification result**

```bash
python - <<'EOF'
import json
with open("phase1a_verification.json") as f:
    d = json.load(f)
for a in d["archives"]:
    tags = ",".join(a.get("secondary_tags", []))
    print(f"{a['crawl_id']:>6}  {a['category']:<24} tags={tags}")
EOF
```
Expected: each row shows `OK` (tags optional, benign). Any `CORRUPTED`, `MISSING_*`, or `ROW_COUNT_MISMATCH` → that crawl_id is a Phase 1A failure.

- [ ] **Step 6: Rollback any failed IDs**

For each failed crawl_id:
```bash
gcloud storage mv "gs://$BUCKET/crawls/$id.tar.gz" \
                  "gs://$BUCKET/crawls-quarantine-rejected/$id.tar.gz"
```
Record the crawl_id — it joins the Phase 1C queue as "Phase 1A failed upload."

- [ ] **Step 7: Upload verification artifact**

```bash
gcloud storage cp phase1a_verification.json \
    gs://$BUCKET/remediation/phase1a_verification_$TODAY.json
```

No git commit — artifacts live in GCS.

---

## Task 4: Phase 1B — Delete Two Safe Duplicate `.tmp` Archives

**Goal:** Delete `crawls-quarantine/4365.tmp.tar.gz` and `crawls-quarantine/5934.tmp.tar.gz`, but only after confirming each main counterpart in `crawls/` still classifies OK today.

**Files:**
- Produce: `phase1b_preflight.json` (targeted audit of the two mains).
- Upload: `gs://{bucket}/remediation/phase1b_preflight_YYYY-MM-DD.json` and `gs://{bucket}/remediation/phase1b_log_YYYY-MM-DD.md`.

**Acceptance Criteria:**
- [ ] Preflight re-audit confirms `4365` and `5934` mains classify OK.
- [ ] Both `.tmp.tar.gz` objects deleted from `crawls-quarantine/`.
- [ ] Deletion verified via `gcloud storage ls` (both produce `not found`).
- [ ] Operator log uploaded to GCS with preflight JSON reference and deletion timestamps.

**Verify:**
```bash
gcloud storage ls gs://$BUCKET/crawls-quarantine/4365.tmp.tar.gz 2>&1 | grep -q "not found\|One or more URLs" && echo ok
gcloud storage ls gs://$BUCKET/crawls-quarantine/5934.tmp.tar.gz 2>&1 | grep -q "not found\|One or more URLs" && echo ok
```
Expected: two `ok` lines.

**Steps:**

- [ ] **Step 1: Pre-delete existence check**

```bash
for id in 4365 5934; do
  echo "--- $id ---"
  gcloud storage ls -l "gs://$BUCKET/crawls/$id.tar.gz" \
    || { echo "ABORT: main $id not in crawls/"; exit 1; }
  gcloud storage ls -l "gs://$BUCKET/crawls-quarantine/$id.tmp.tar.gz" \
    || { echo "ABORT: tmp $id not in crawls-quarantine/"; exit 1; }
done
```
If either aborts, stop — investigate before continuing.

- [ ] **Step 2: Re-audit the two mains with the corrected classifier**

```bash
python tools/gcs_archive_audit.py --bucket "$BUCKET" \
    --include-ids 4365,5934 \
    --output phase1b_preflight.json

python - <<'EOF'
import json
with open("phase1b_preflight.json") as f:
    d = json.load(f)
for a in d["archives"]:
    print(a["crawl_id"], a["category"], a.get("expected_count"), a.get("actual_count"))
EOF
```
Expected: both `4365` and `5934` → `OK` with matching counts (2495/2495 and 541/541). Any regression → **ABORT** and investigate.

- [ ] **Step 3: Delete the two tmps**

```bash
for id in 4365 5934; do
  gcloud storage rm "gs://$BUCKET/crawls-quarantine/$id.tmp.tar.gz"
done
```

- [ ] **Step 4: Post-delete verification**

```bash
for id in 4365 5934; do
  if gcloud storage ls "gs://$BUCKET/crawls-quarantine/$id.tmp.tar.gz" 2>&1 \
     | grep -q "not found\|One or more URLs"; then
    echo "$id: removed"
  else
    echo "FAIL: $id still present"
    exit 1
  fi
done
```

- [ ] **Step 5: Write and upload operator log**

```bash
cat > phase1b_log_$TODAY.md <<EOF
# Phase 1B operator log — $TODAY

Bucket versioning: <True|False>  (see Phase 0 record)

## Preflight
Re-audit of mains 4365 + 5934 via --include-ids → both OK.
Artifact: gs://$BUCKET/remediation/phase1b_preflight_$TODAY.json

## Deletions (timestamps in UTC)
- $(date -u +%Y-%m-%dT%H:%M:%SZ)  gs://$BUCKET/crawls-quarantine/4365.tmp.tar.gz
- $(date -u +%Y-%m-%dT%H:%M:%SZ)  gs://$BUCKET/crawls-quarantine/5934.tmp.tar.gz

## Post-delete check
Both returned "not found" via gcloud storage ls.
EOF

gcloud storage cp phase1b_preflight.json \
    gs://$BUCKET/remediation/phase1b_preflight_$TODAY.json
gcloud storage cp phase1b_log_$TODAY.md \
    gs://$BUCKET/remediation/phase1b_log_$TODAY.md
```

No git commit — artifacts live in GCS.

---

## Task 5: Phase 1C — Build and Upload Update-Mode Queue

**Goal:** Implement `tools/build_update_mode_queue.py` (with tests), then run it to produce and upload the update-mode re-ingestion queue JSON.

**Files:**
- Create: `tools/build_update_mode_queue.py`
- Create: `tools/tests/test_build_update_mode_queue.py`
- Upload: `gs://{bucket}/remediation/update_mode_queue_YYYY-MM-DD.json`

**Acceptance Criteria:**
- [ ] `test_corrupted_goes_to_entries` passes.
- [ ] `test_major_under_delivery_goes_to_entries` passes.
- [ ] `test_minor_under_delivery_goes_to_deferred` passes.
- [ ] `test_excess_goes_to_deferred` passes.
- [ ] `test_expected_zero_goes_to_deferred` passes.
- [ ] `test_tmp_sibling_row_mismatch_defers` passes.
- [ ] `test_ok_entries_skipped` passes.
- [ ] `test_wrong_name_skipped` passes.
- [ ] `test_exclude_ids_filters_out` passes.
- [ ] `test_threshold_override` passes.
- [ ] Running the script against the real `corrected_report.json` produces a queue with ~23 `entries` and ~50 `deferred_to_phase2` items.
- [ ] Queue JSON uploaded to `gs://{bucket}/remediation/`.

**Verify:** `pytest tools/tests/test_build_update_mode_queue.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `tools/tests/test_build_update_mode_queue.py`:

```python
"""Tests for tools/build_update_mode_queue.py."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

import build_update_mode_queue as bq


def _report_with(archives):
    return {"archives": archives, "bucket": "b"}


class TestClassifyEntry:
    def test_corrupted_goes_to_entries(self):
        entry = {
            "crawl_id": "1427",
            "object_name": "crawls/1427.tar.gz",
            "category": "CORRUPTED",
            "secondary_tags": [],
            "error": "EOFError",
        }
        result = bq.classify_entry(entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30)
        assert result["bucket"] == "entries"
        assert result["reason"] == "CORRUPTED"

    def test_major_under_delivery_goes_to_entries(self):
        entry = {
            "crawl_id": "1714",
            "object_name": "crawls/1714.tar.gz",
            "category": "ROW_COUNT_MISMATCH",
            "secondary_tags": [],
            "expected_count": 5789,
            "actual_count": 478,
        }
        result = bq.classify_entry(entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30)
        assert result["bucket"] == "entries"
        assert result["reason"] == "MAJOR_UNDER_DELIVERY"

    def test_minor_under_delivery_goes_to_deferred(self):
        entry = {
            "crawl_id": "2754",
            "object_name": "crawls/2754.tar.gz",
            "category": "ROW_COUNT_MISMATCH",
            "secondary_tags": [],
            "expected_count": 267,
            "actual_count": 265,
        }
        result = bq.classify_entry(entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30)
        assert result["bucket"] == "deferred_to_phase2"
        assert result["reason"] == "MINOR_UNDER_DELIVERY"

    def test_excess_goes_to_deferred(self):
        entry = {
            "crawl_id": "3487",
            "object_name": "crawls/3487.tar.gz",
            "category": "ROW_COUNT_MISMATCH",
            "secondary_tags": [],
            "expected_count": 35,
            "actual_count": 1426,
        }
        result = bq.classify_entry(entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30)
        assert result["bucket"] == "deferred_to_phase2"
        assert result["reason"] == "EXCESS_LIKELY_CLASSIFIER_BUG"

    def test_expected_zero_goes_to_deferred(self):
        entry = {
            "crawl_id": "4398",
            "object_name": "crawls/4398.tar.gz",
            "category": "ROW_COUNT_MISMATCH",
            "secondary_tags": [],
            "expected_count": 0,
            "actual_count": 108,
        }
        result = bq.classify_entry(entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30)
        assert result["bucket"] == "deferred_to_phase2"
        assert result["reason"] == "EXPECTED_ZERO_LIKELY_CLASSIFIER_BUG"

    def test_tmp_sibling_row_mismatch_defers(self):
        main = {
            "crawl_id": "4347",
            "object_name": "crawls/4347.tar.gz",
            "category": "ROW_COUNT_MISMATCH",
            "secondary_tags": ["DUPLICATE"],
            "expected_count": 1518,
            "actual_count": 424,
        }
        tmp = {
            "crawl_id": "4347",
            "object_name": "crawls/4347.tmp.tar.gz",
            "category": "WRONG_NAME",
            "secondary_tags": ["DUPLICATE"],
        }
        result = bq.classify_entry(main, all_entries=[main, tmp], exclude_ids=set(), deficit_threshold=0.30)
        assert result["bucket"] == "deferred_to_phase2"
        assert result["reason"] == "HOLD_TMP_SIBLING"

    def test_ok_entries_skipped(self):
        entry = {"crawl_id": "2409", "object_name": "crawls/2409.tar.gz", "category": "OK", "secondary_tags": []}
        assert bq.classify_entry(entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30) is None

    def test_wrong_name_skipped(self):
        entry = {"crawl_id": "5643", "object_name": "crawls/5643.tmp.tar.gz", "category": "WRONG_NAME", "secondary_tags": []}
        assert bq.classify_entry(entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30) is None

    def test_exclude_ids_filters_out(self):
        entry = {"crawl_id": "1806", "object_name": "crawls/1806.tar.gz", "category": "CORRUPTED", "secondary_tags": [], "error": "x"}
        assert bq.classify_entry(entry, all_entries=[entry], exclude_ids={"1806"}, deficit_threshold=0.30) is None

    def test_threshold_override(self):
        entry = {
            "crawl_id": "4156",
            "object_name": "crawls/4156.tar.gz",
            "category": "ROW_COUNT_MISMATCH",
            "secondary_tags": [],
            "expected_count": 1627,
            "actual_count": 1280,   # 21.3% deficit
        }
        # Default 0.30 → deferred
        assert bq.classify_entry(entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30)["bucket"] == "deferred_to_phase2"
        # Lowered 0.10 → entries
        assert bq.classify_entry(entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.10)["bucket"] == "entries"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tools/tests/test_build_update_mode_queue.py -v
```
Expected: all FAIL with `ModuleNotFoundError: No module named 'build_update_mode_queue'`.

- [ ] **Step 3: Implement `tools/build_update_mode_queue.py`**

```python
"""Build the update-mode re-ingestion queue from a gcs_archive_audit report.

Reads a report (e.g. `corrected_report.json`), applies inclusion rules
(CORRUPTED without local replacement; ROW_COUNT_MISMATCH with deficit above
threshold; excluding classifier-bug patterns and entries with tmp siblings),
and writes a JSON artifact with two lists:
  - `entries`: actionable now via update-mode
  - `deferred_to_phase2`: metadata for later decisions

Optionally uploads the artifact to GCS via `gcloud storage cp`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def load_report(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_exclude_ids(spec: Optional[str]) -> Set[str]:
    if not spec:
        return set()
    return {s.strip() for s in spec.split(",") if s.strip()}


def _has_tmp_sibling(all_entries: List[Dict], crawl_id: str) -> bool:
    for e in all_entries:
        if (e.get("crawl_id") == crawl_id
                and e.get("object_name", "").endswith(".tmp.tar.gz")):
            return True
    return False


def classify_entry(
    entry: Dict,
    all_entries: List[Dict],
    exclude_ids: Set[str],
    deficit_threshold: float,
) -> Optional[Dict]:
    """Return {'bucket': 'entries'|'deferred_to_phase2', 'reason', 'detail'}
    or None if the entry doesn't belong in either list (OK, WRONG_NAME,
    excluded by ID)."""
    cid = entry.get("crawl_id")
    if not cid or cid in exclude_ids:
        return None

    category = entry.get("category")

    if category == "CORRUPTED":
        return {
            "bucket": "entries",
            "reason": "CORRUPTED",
            "detail": entry.get("error", "unreadable"),
        }

    if category != "ROW_COUNT_MISMATCH":
        return None  # OK or WRONG_NAME

    # Skip the .tmp sibling itself — only the main (.tar.gz) drives the decision.
    obj = entry.get("object_name", "")
    if obj.endswith(".tmp.tar.gz"):
        return None

    expected = entry.get("expected_count", 0) or 0
    actual = entry.get("actual_count", 0) or 0

    if actual > expected:
        return {
            "bucket": "deferred_to_phase2",
            "reason": "EXCESS_LIKELY_CLASSIFIER_BUG",
            "detail": f"expected={expected} actual={actual}",
        }
    if expected == 0:
        return {
            "bucket": "deferred_to_phase2",
            "reason": "EXPECTED_ZERO_LIKELY_CLASSIFIER_BUG",
            "detail": f"expected=0 actual={actual}",
        }

    if _has_tmp_sibling(all_entries, cid):
        return {
            "bucket": "deferred_to_phase2",
            "reason": "HOLD_TMP_SIBLING",
            "detail": "inspect .tmp sibling in Phase 2 before scheduling",
        }

    deficit_ratio = (expected - actual) / expected
    detail = f"expected={expected} actual={actual} deficit={deficit_ratio * 100:.1f}%"

    if deficit_ratio > deficit_threshold:
        return {"bucket": "entries", "reason": "MAJOR_UNDER_DELIVERY", "detail": detail}
    return {"bucket": "deferred_to_phase2", "reason": "MINOR_UNDER_DELIVERY", "detail": detail}


def build_queue(
    report: Dict,
    exclude_ids: Set[str],
    deficit_threshold: float,
    source_report_uri: str,
    generator_id: str,
) -> Dict:
    all_entries = report.get("archives", [])
    entries: List[Dict] = []
    deferred: List[Dict] = []
    for entry in all_entries:
        classified = classify_entry(entry, all_entries, exclude_ids, deficit_threshold)
        if classified is None:
            continue
        payload = {
            "crawl_id": entry["crawl_id"],
            "reason": classified["reason"],
            "detail": classified["detail"],
            "quarantine_uri": f"gs://{report.get('bucket', '{bucket}')}/crawls-quarantine/{entry['object_name'].rsplit('/', 1)[-1]}",
            "notes": [],
        }
        if classified["bucket"] == "entries":
            entries.append(payload)
        else:
            deferred.append({k: v for k, v in payload.items() if k in ("crawl_id", "reason", "detail")})

    entries.sort(key=lambda e: e["crawl_id"])
    deferred.sort(key=lambda e: e["crawl_id"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_report": source_report_uri,
        "generator": generator_id,
        "deficit_threshold": deficit_threshold,
        "entries": entries,
        "deferred_to_phase2": deferred,
    }


def upload_to_gcs(local_path: Path, gs_uri: str) -> None:
    subprocess.run(["gcloud", "storage", "cp", str(local_path), gs_uri], check=True)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the update-mode re-ingestion queue.")
    parser.add_argument("--input", required=True, help="Path to corrected_report.json")
    parser.add_argument("--output", required=True, help="Local output path for the queue JSON")
    parser.add_argument("--exclude-ids", default="",
                        help="Comma-separated crawl_ids to skip (e.g. Phase 1A survivors)")
    parser.add_argument("--deficit-threshold", type=float, default=0.30,
                        help="ROW_COUNT_MISMATCH deficit threshold for MAJOR_UNDER_DELIVERY (default 0.30)")
    parser.add_argument("--source-report-uri",
                        default="gs://{bucket}/remediation/2026-04-19_corrected_report.json",
                        help="Source report URI to record in the artifact")
    parser.add_argument("--generator",
                        default="tools/build_update_mode_queue.py",
                        help="Generator identifier recorded in the artifact")
    parser.add_argument("--upload", default=None,
                        help="If set, upload the generated queue to this gs:// URI")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    report = load_report(Path(args.input))
    exclude_ids = load_exclude_ids(args.exclude_ids)

    queue = build_queue(
        report=report,
        exclude_ids=exclude_ids,
        deficit_threshold=args.deficit_threshold,
        source_report_uri=args.source_report_uri,
        generator_id=args.generator,
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)

    print(f"entries: {len(queue['entries'])}")
    print(f"deferred_to_phase2: {len(queue['deferred_to_phase2'])}")
    print(f"written to: {args.output}")

    if args.upload:
        upload_to_gcs(Path(args.output), args.upload)
        print(f"uploaded to: {args.upload}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tools/tests/test_build_update_mode_queue.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit the generator**

```bash
git add tools/build_update_mode_queue.py tools/tests/test_build_update_mode_queue.py
git commit -m "$(cat <<'EOF'
feat(tools): add build_update_mode_queue.py — update-mode queue builder

Reads a gcs_archive_audit report and produces a JSON artifact with
'entries' (actionable via update-mode now) and 'deferred_to_phase2'
(classifier-bug patterns and tmp-sibling holds). Configurable deficit
threshold and exclude-ids for Phase 1A survivors. Optional GCS upload.

---

feat(tools): ajout de build_update_mode_queue.py — generateur de file update-mode

Lit un rapport gcs_archive_audit et produit un artefact JSON avec
'entries' (actionable via update-mode maintenant) et 'deferred_to_phase2'
(patterns de bug classifieur et holds pour freres .tmp). Seuil de
deficit et exclude-ids configurables pour les survivants Phase 1A.
Upload GCS optionnel.
EOF
)"
```

- [ ] **Step 6: Generate the real queue**

Use the Phase 1A survivors for `--exclude-ids` (the IDs that passed verification in Task 3). Default assumes all 4 overlapping IDs passed:

```bash
python tools/build_update_mode_queue.py \
    --input corrected_report.json \
    --exclude-ids 1806,2517,4683,4699 \
    --deficit-threshold 0.30 \
    --source-report-uri "gs://$BUCKET/remediation/2026-04-19_corrected_report.json" \
    --output update_mode_queue.json \
    --upload "gs://$BUCKET/remediation/update_mode_queue_$TODAY.json"
```

- [ ] **Step 7: Sanity-check output**

```bash
python - <<'EOF'
import json
with open("update_mode_queue.json") as f:
    q = json.load(f)
print(f"entries:           {len(q['entries'])}")
print(f"deferred_to_phase2: {len(q['deferred_to_phase2'])}")
print()
print("sample entries (first 5):")
for e in q["entries"][:5]:
    print(f"  {e['crawl_id']:>6}  {e['reason']:<22}  {e['detail']}")
print()
print("sample deferred (first 5):")
for e in q["deferred_to_phase2"][:5]:
    print(f"  {e['crawl_id']:>6}  {e['reason']:<40}  {e['detail']}")
EOF
```
Expected: `entries` count close to 23 (14 major + ~10 CORRUPTED minus Phase 1A survivors); `deferred_to_phase2` count close to ~50.

- [ ] **Step 8: Hand URI to ops**

The `--upload` in Step 6 has already uploaded to `gs://$BUCKET/remediation/update_mode_queue_$TODAY.json`. Pass that URI to whoever triggers update-mode. Runbook stops here.

---

## Task 6: Phase 2.2 + 2.3 — Re-audit Quarantine and Surgically Restore

**Goal:** Re-audit `crawls-quarantine/` with the corrected classifier, implement a committed per-object restore script, execute it, and open a follow-up ticket for the middle bucket.

**Files:**
- Create: `tools/restore_from_reaudit.py`
- Create: `tools/tests/test_restore_from_reaudit.py`
- Upload: `gs://{bucket}/remediation/quarantine_reaudit_YYYY-MM-DD.json`
- Upload: `gs://{bucket}/remediation/phase2_restore_log_YYYY-MM-DD.md`

**Acceptance Criteria:**
- [ ] Re-audit JSON has ~47 archives reclassified to `OK` (35 drift + 7 excess + 5 expected=0 — approximate).
- [ ] `test_restore_moves_only_ok_entries` passes.
- [ ] `test_restore_skips_on_destination_collision` passes.
- [ ] `test_restore_logs_each_action` passes.
- [ ] `test_restore_preserves_non_ok_entries` passes.
- [ ] `test_restore_dry_run_makes_no_calls` passes.
- [ ] Real restore run moves the reclassified archives back to `crawls/` without collision.
- [ ] Restore log uploaded to GCS with per-ID outcome.
- [ ] Follow-up ticket filed for the middle-bucket decision (5–30 % deficit entries that still flag).

**Verify:**
```bash
gcloud storage cat gs://$BUCKET/remediation/phase2_restore_log_$TODAY.md | head -20
pytest tools/tests/test_restore_from_reaudit.py -v
```
Expected: log shows the RESTORED/SKIP actions; all tests pass.

**Steps:**

- [ ] **Step 1: Re-audit the quarantine prefix**

```bash
python tools/gcs_archive_audit.py --bucket "$BUCKET" \
    --prefix crawls-quarantine/ \
    --output quarantine_reaudit_$TODAY.json
```
Note: this downloads ~99 archives. Expect 5–15 minutes.

- [ ] **Step 2: Inspect the re-audit**

```bash
python - <<'EOF'
import json
from collections import Counter
with open(f"quarantine_reaudit_$TODAY.json") as f:
    d = json.load(f)
cats = Counter(a["category"] for a in d["archives"])
tags = Counter(t for a in d["archives"] for t in a.get("secondary_tags", []))
print("categories:", dict(cats))
print("tags:", dict(tags))
EOF
```
Expected roughly: `OK` count ≈ 47 (35 COUNT_DRIFT + 7 EXCESS_FILES + 5 FAILED_CRAWL_WITH_RESIDUE); `CORRUPTED` unchanged (14); `WRONG_NAME` 8 (after Phase 1B removed 2); `ROW_COUNT_MISMATCH` ≈ 22 (14 major + 8 middle bucket).

- [ ] **Step 3: Upload the re-audit**

```bash
gcloud storage cp quarantine_reaudit_$TODAY.json \
    gs://$BUCKET/remediation/quarantine_reaudit_$TODAY.json
```

- [ ] **Step 4: Write failing tests for the restore script**

Create `tools/tests/test_restore_from_reaudit.py`:

```python
"""Tests for tools/restore_from_reaudit.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import restore_from_reaudit as rr


def _reaudit(archives):
    return {"bucket": "b", "prefix": "crawls-quarantine/", "archives": archives}


class TestRestore:
    def test_restore_moves_only_ok_entries(self, tmp_path):
        audit = _reaudit([
            {"object_name": "crawls-quarantine/1111.tar.gz", "crawl_id": "1111",
             "category": "OK", "secondary_tags": ["COUNT_DRIFT"]},
            {"object_name": "crawls-quarantine/2222.tar.gz", "crawl_id": "2222",
             "category": "ROW_COUNT_MISMATCH", "secondary_tags": []},
        ])
        path = tmp_path / "a.json"
        path.write_text(json.dumps(audit))

        with patch("restore_from_reaudit.gcloud_move") as mock_mv, \
             patch("restore_from_reaudit._exists", return_value=False):
            count = rr.restore(input_path=path, bucket="b", target_prefix="crawls/",
                               log_path=tmp_path / "log.md", dry_run=False)

        assert count == 1
        mock_mv.assert_called_once_with(
            "gs://b/crawls-quarantine/1111.tar.gz",
            "gs://b/crawls/1111.tar.gz",
        )

    def test_restore_skips_on_destination_collision(self, tmp_path):
        audit = _reaudit([
            {"object_name": "crawls-quarantine/1111.tar.gz", "crawl_id": "1111",
             "category": "OK", "secondary_tags": []},
        ])
        path = tmp_path / "a.json"
        path.write_text(json.dumps(audit))

        with patch("restore_from_reaudit.gcloud_move") as mock_mv, \
             patch("restore_from_reaudit._exists", return_value=True):
            count = rr.restore(input_path=path, bucket="b", target_prefix="crawls/",
                               log_path=tmp_path / "log.md", dry_run=False)

        assert count == 0
        mock_mv.assert_not_called()
        log = (tmp_path / "log.md").read_text()
        assert "SKIP 1111" in log

    def test_restore_logs_each_action(self, tmp_path):
        audit = _reaudit([
            {"object_name": "crawls-quarantine/a.tar.gz", "crawl_id": "1",
             "category": "OK", "secondary_tags": ["COUNT_DRIFT"]},
            {"object_name": "crawls-quarantine/b.tar.gz", "crawl_id": "2",
             "category": "OK", "secondary_tags": ["EXCESS_FILES"]},
        ])
        path = tmp_path / "a.json"
        path.write_text(json.dumps(audit))

        with patch("restore_from_reaudit.gcloud_move"), \
             patch("restore_from_reaudit._exists", return_value=False):
            rr.restore(input_path=path, bucket="b", target_prefix="crawls/",
                       log_path=tmp_path / "log.md", dry_run=False)

        log = (tmp_path / "log.md").read_text()
        assert "RESTORED 1" in log and "COUNT_DRIFT" in log
        assert "RESTORED 2" in log and "EXCESS_FILES" in log

    def test_restore_preserves_non_ok_entries(self, tmp_path):
        audit = _reaudit([
            {"object_name": "crawls-quarantine/1.tar.gz", "crawl_id": "1",
             "category": "CORRUPTED", "secondary_tags": []},
            {"object_name": "crawls-quarantine/2.tar.gz", "crawl_id": "2",
             "category": "WRONG_NAME", "secondary_tags": []},
            {"object_name": "crawls-quarantine/3.tar.gz", "crawl_id": "3",
             "category": "ROW_COUNT_MISMATCH", "secondary_tags": []},
        ])
        path = tmp_path / "a.json"
        path.write_text(json.dumps(audit))

        with patch("restore_from_reaudit.gcloud_move") as mock_mv, \
             patch("restore_from_reaudit._exists", return_value=False):
            count = rr.restore(input_path=path, bucket="b", target_prefix="crawls/",
                               log_path=tmp_path / "log.md", dry_run=False)

        assert count == 0
        mock_mv.assert_not_called()

    def test_restore_dry_run_makes_no_calls(self, tmp_path):
        audit = _reaudit([
            {"object_name": "crawls-quarantine/1.tar.gz", "crawl_id": "1",
             "category": "OK", "secondary_tags": []},
        ])
        path = tmp_path / "a.json"
        path.write_text(json.dumps(audit))

        with patch("restore_from_reaudit.gcloud_move") as mock_mv, \
             patch("restore_from_reaudit._exists") as mock_exists:
            count = rr.restore(input_path=path, bucket="b", target_prefix="crawls/",
                               log_path=tmp_path / "log.md", dry_run=True)

        assert count == 1  # would-have-been moved
        mock_mv.assert_not_called()
        mock_exists.assert_called_once()       # existence check still runs
        log = (tmp_path / "log.md").read_text()
        assert "DRY-RUN" in log
```

- [ ] **Step 5: Run tests to verify they fail**

```bash
pytest tools/tests/test_restore_from_reaudit.py -v
```
Expected: all FAIL with `ModuleNotFoundError: No module named 'restore_from_reaudit'`.

- [ ] **Step 6: Implement `tools/restore_from_reaudit.py`**

```python
"""Move reclassified-OK archives from crawls-quarantine/ back to crawls/.

Reads a re-audit JSON produced by gcs_archive_audit.py --prefix
crawls-quarantine/, finds entries with category == OK, and moves each
back to the target prefix via `gcloud storage mv`. Defensive:
- Skips any entry whose destination already exists (e.g. a Phase 1A
  upload filled that slot).
- Never moves non-OK entries.
- Supports a dry-run mode.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


def _run_gcloud(args: List[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gcloud"] + args, check=check, capture_output=True, text=True)


def gcloud_move(src_uri: str, dst_uri: str) -> None:
    _run_gcloud(["storage", "mv", src_uri, dst_uri])


def _exists(gs_uri: str) -> bool:
    """Return True if the object exists at gs_uri.

    `gcloud storage ls <obj>` exits 0 when present, non-zero on
    'One or more URLs matched no objects'.
    """
    result = _run_gcloud(["storage", "ls", gs_uri], check=False)
    return result.returncode == 0


def restore(
    input_path: Path,
    bucket: str,
    target_prefix: str,
    log_path: Path,
    dry_run: bool,
) -> int:
    """Restore reclassified-OK archives. Returns the number of moves
    performed (or would-have-been moves if dry_run)."""
    with open(input_path, "r", encoding="utf-8") as f:
        audit = json.load(f)

    log_lines: List[str] = [
        f"# Phase 2.3 restore log — {datetime.now(timezone.utc).isoformat()}",
        f"Bucket: {bucket}",
        f"Target prefix: {target_prefix}",
        f"Dry-run: {dry_run}",
        f"Source: {input_path}",
        "",
    ]
    mode_prefix = "DRY-RUN " if dry_run else ""

    count = 0
    for entry in audit.get("archives", []):
        if entry.get("category") != "OK":
            continue
        obj = entry["object_name"]
        basename = obj.rsplit("/", 1)[-1]
        src_uri = f"gs://{bucket}/{obj}"
        dst_uri = f"gs://{bucket}/{target_prefix.rstrip('/')}/{basename}"
        crawl_id = entry.get("crawl_id", "?")
        tags = ",".join(entry.get("secondary_tags", [])) or "-"

        if _exists(dst_uri):
            log_lines.append(f"{mode_prefix}SKIP {crawl_id}: {dst_uri} already exists (tags={tags})")
            continue

        if dry_run:
            log_lines.append(f"DRY-RUN RESTORED {crawl_id}: {src_uri} -> {dst_uri} (tags={tags})")
        else:
            try:
                gcloud_move(src_uri, dst_uri)
                log_lines.append(f"RESTORED {crawl_id}: {src_uri} -> {dst_uri} (tags={tags})")
            except subprocess.CalledProcessError as e:
                log_lines.append(f"FAILED {crawl_id}: {e.stderr.strip()}")
                continue
        count += 1

    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return count


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Surgically move reclassified-OK archives out of quarantine.")
    parser.add_argument("--input", required=True, help="Re-audit JSON path")
    parser.add_argument("--bucket", required=True, help="GCS bucket name")
    parser.add_argument("--target-prefix", default="crawls/", help="Destination prefix (default crawls/)")
    parser.add_argument("--log", required=True, help="Output log markdown path")
    parser.add_argument("--dry-run", action="store_true", help="Don't move; just plan and log")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    count = restore(
        input_path=Path(args.input),
        bucket=args.bucket,
        target_prefix=args.target_prefix,
        log_path=Path(args.log),
        dry_run=args.dry_run,
    )
    mode = "would restore" if args.dry_run else "restored"
    print(f"{mode} {count} archive(s). Log: {args.log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest tools/tests/test_restore_from_reaudit.py -v
```
Expected: all PASS.

- [ ] **Step 8: Commit the restore script**

```bash
git add tools/restore_from_reaudit.py tools/tests/test_restore_from_reaudit.py
git commit -m "$(cat <<'EOF'
feat(tools): add restore_from_reaudit.py — surgical quarantine restore

Moves reclassified-OK archives out of crawls-quarantine/ back to
crawls/, per-object via gcloud storage mv. Defensive: skips any entry
whose destination already exists (protects Phase 1A uploads); never
moves non-OK entries; supports --dry-run for pre-flight planning.

Complements the --restore-from-quarantine bulk move in
gcs_archive_audit.py by enabling selective, evidence-driven restores.

---

feat(tools): ajout de restore_from_reaudit.py — restauration chirurgicale

Deplace les archives reclassees OK de crawls-quarantine/ vers crawls/,
objet par objet via gcloud storage mv. Defensif : ignore toute entree
dont la destination existe deja (protege les uploads Phase 1A) ; ne
deplace jamais les entrees non-OK ; --dry-run pour la planification.

Complement du --restore-from-quarantine bulk de gcs_archive_audit.py
en permettant des restaurations selectives basees sur des preuves.
EOF
)"
```

- [ ] **Step 9: Dry-run the restore**

```bash
python tools/restore_from_reaudit.py \
    --input quarantine_reaudit_$TODAY.json \
    --bucket "$BUCKET" \
    --target-prefix crawls/ \
    --log phase2_restore_dryrun_$TODAY.md \
    --dry-run

cat phase2_restore_dryrun_$TODAY.md
```
Expected: `DRY-RUN RESTORED` lines for ~47 OK entries; any `DRY-RUN SKIP` lines flag collisions. Review carefully.

- [ ] **Step 10: Execute the restore**

Only after the dry-run log looks correct:

```bash
python tools/restore_from_reaudit.py \
    --input quarantine_reaudit_$TODAY.json \
    --bucket "$BUCKET" \
    --target-prefix crawls/ \
    --log phase2_restore_log_$TODAY.md
```
Expected: `restored N archive(s).` where N matches the dry-run RESTORED count.

- [ ] **Step 11: Verify restores landed**

```bash
python - <<'EOF'
import json, subprocess
with open(f"quarantine_reaudit_$TODAY.json") as f:
    d = json.load(f)
ok_ids = [a["crawl_id"] for a in d["archives"] if a["category"] == "OK"]
missing = []
for cid in ok_ids:
    r = subprocess.run(["gcloud", "storage", "ls", f"gs://$BUCKET/crawls/{cid}.tar.gz"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        missing.append(cid)
print(f"restored OK IDs: {len(ok_ids)}; missing in crawls/: {len(missing)}")
if missing:
    print("MISSING:", missing)
EOF
```
Expected: `missing in crawls/: 0` (or a small non-zero count matching SKIPs in the log — investigate each).

- [ ] **Step 12: Upload restore log**

```bash
gcloud storage cp phase2_restore_log_$TODAY.md \
    gs://$BUCKET/remediation/phase2_restore_log_$TODAY.md

gcloud storage cp phase2_restore_dryrun_$TODAY.md \
    gs://$BUCKET/remediation/phase2_restore_dryrun_$TODAY.md
```

- [ ] **Step 13: File follow-up ticket for the middle bucket**

In whichever ticket tracker the team uses (GitHub Issues, Jira, etc.), open a ticket titled roughly:

> **Decide fate of middle-bucket archives (5–30 % deficit) in crawls-quarantine/**

Body:

```markdown
After Phase 2 of the GCS quarantine remediation runbook
(`docs/superpowers/specs/2026-04-22-gcs-quarantine-remediation-runbook-design.md`),
~8 archives in `gs://{bucket}/crawls-quarantine/` remain as `ROW_COUNT_MISMATCH`
with deficit between 5 % and 30 %. Too big for drift tolerance, too small for the
major-under-delivery cutoff. See `gs://{bucket}/remediation/quarantine_reaudit_<date>.json`
and the `deferred_to_phase2` entries in `update_mode_queue_<date>.json` (filter by
`reason == "MINOR_UNDER_DELIVERY"`).

Three options:
- **A.** Extend update-mode queue with `--deficit-threshold 0.05` and re-run Phase 1C.
- **B.** Leave quarantined indefinitely.
- **C.** Per-archive inspection (recommended — 8 archives is cheap to eyeball).

Decide + execute. Once closed, the runbook is complete.
```

Record the ticket URL in the restore log; re-upload the log if needed.

- [ ] **Step 14: Mark the runbook complete**

All Phase 1 and Phase 2 operational steps are done. The middle-bucket follow-up ticket carries the remaining decision.

---

## Self-Review Checklist

Applied inline during plan authoring:

- **Spec coverage:** Every section of the spec maps to a task. Pre-flight → Task 0. `--include-ids` → Task 1. Phase 2.0+2.1 → Task 2. Phase 1A → Task 3. Phase 1B → Task 4. Phase 1C (generator + execution) → Task 5. Phase 2.2+2.3 (re-audit + restore code + execution) + middle-bucket follow-up → Task 6.
- **Placeholder scan:** No `TBD`, `TODO`, or `implement later`. Every code step shows concrete code. The only `<…>` placeholders are operator values (`<your-bucket-name>`, `<True|False>` for versioning state) documented in the Conventions section.
- **Type consistency:** `inspect_archive(local_tar_path, row_count_tolerance=0.05)` and `_inspect_one(obj_uri, size_bytes, name_only, row_count_tolerance=0.05)` match across Task 2's implementation and the test expectations. `classify_entry(entry, all_entries, exclude_ids, deficit_threshold)` used consistently in Task 5 tests and implementation. `restore(input_path, bucket, target_prefix, log_path, dry_run)` used consistently in Task 6 tests and implementation.
- **Commit alignment:** Bilingual (EN + FR) commit messages matching the repo convention, one commit per task (3, 4, 5, 6) where code changed. Ops-only tasks (0, 3, 4) end with GCS artifact uploads rather than git commits.
