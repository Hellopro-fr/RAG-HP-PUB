"""GCS Archive Audit Tool.

Audits every archive in gs://{bucket}/crawls/, classifies each, writes a
JSON report, and optionally remediates via --delete or --quarantine.

Shells out to `gcloud storage` — no google-cloud-storage Python dependency.
Authentication is whatever gcloud is configured with on the host.

Run:
    python tools/gcs_archive_audit.py --bucket <name> [--output report.json]
"""
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union


def _run_gcloud(args: List[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a gcloud command via subprocess. Centralized so tests can patch a single point."""
    cmd = ["gcloud"] + args
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def check_gcloud_auth() -> None:
    """Ensure gcloud has an active authenticated account. Exit with a helpful message if not."""
    try:
        result = _run_gcloud(["auth", "list", "--filter=status:ACTIVE", "--format=value(account)"])
    except FileNotFoundError:
        print("ERROR: `gcloud` CLI not found on PATH. Install Google Cloud SDK.", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: `gcloud auth list` failed: {e.stderr}", file=sys.stderr)
        sys.exit(2)

    active = (result.stdout or "").strip()
    if not active:
        print(
            "ERROR: No active gcloud account. Run one of:\n"
            "  gcloud auth login\n"
            "  gcloud auth activate-service-account --key-file=<path>",
            file=sys.stderr,
        )
        sys.exit(2)


def gcloud_ls(uri: str, long: bool = False) -> List[Union[str, Tuple[int, str]]]:
    """List objects under a GCS URI.

    When long=False: returns a list of URIs (strings).
    When long=True: returns a list of (size_bytes, uri) tuples. Non-parseable
    lines are skipped (e.g., the trailing 'TOTAL:' summary line).
    """
    args = ["storage", "ls"]
    if long:
        args.append("-l")
    args.append(uri)
    try:
        result = _run_gcloud(args)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: gcloud storage ls failed for '{uri}': {e.stderr}", file=sys.stderr)
        return []

    lines = [line.rstrip() for line in result.stdout.splitlines() if line.strip()]
    if not long:
        return [line for line in lines if line.startswith("gs://")]

    # Long format:
    #   <size>  <YYYY-MM-DDTHH:MM:SSZ>  gs://bucket/path
    # We want (size, uri) tuples, skipping any line that doesn't parse.
    out: List[Tuple[int, str]] = []
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        if not parts[-1].startswith("gs://"):
            continue
        try:
            size = int(parts[0])
        except ValueError:
            continue
        out.append((size, parts[-1]))
    return out


def gcloud_download(obj_uri: str, local_path: Path) -> None:
    """Download a GCS object to a local path. Raises on failure."""
    _run_gcloud(["storage", "cp", obj_uri, str(local_path)])


def gcloud_delete(obj_uri: str) -> None:
    """Delete a GCS object. Raises on failure."""
    _run_gcloud(["storage", "rm", obj_uri])


def gcloud_move(src_uri: str, dst_uri: str) -> None:
    """Move (rename) a GCS object. Server-side where possible. Raises on failure."""
    _run_gcloud(["storage", "mv", src_uri, dst_uri])


def extract_crawl_id(object_name: str) -> Optional[str]:
    """Given `crawls/4365.tar.gz` or `crawls/4365.tmp.tar.gz` or a full gs:// URI,
    return the crawl_id component. Returns None if the name doesn't match.

    Examples:
        'crawls/4365.tar.gz'         -> '4365'
        'crawls/4365.tmp.tar.gz'     -> '4365'
        'gs://b/crawls/4365.tar.gz'  -> '4365'
        'gs://b/crawls/weird'        -> None
    """
    # Strip gs://bucket/ prefix if present
    path = object_name
    if path.startswith("gs://"):
        # gs://bucket/rest/of/path → rest/of/path
        parts = path.split("/", 3)
        path = parts[3] if len(parts) >= 4 else ""

    # Take the basename and strip known suffixes
    base = path.rsplit("/", 1)[-1]
    for suffix in (".tmp.tar.gz", ".tar.gz"):
        if base.endswith(suffix):
            crawl_id = base[: -len(suffix)]
            if crawl_id:
                return crawl_id
    return None


# ---- Categories ----

OK = "OK"
WRONG_NAME = "WRONG_NAME"
CORRUPTED = "CORRUPTED"
MISSING_PAYLOAD = "MISSING_PAYLOAD"
MISSING_MARKER = "MISSING_MARKER"
ROW_COUNT_MISMATCH = "ROW_COUNT_MISMATCH"
DUPLICATE = "DUPLICATE"
INSPECTION_FAILED = "INSPECTION_FAILED"


def classify_by_name(object_name: str) -> Optional[str]:
    """Return WRONG_NAME if the object name ends in `.tmp.tar.gz`, else None.

    Name-only screening — does not download or open the archive.
    """
    base = object_name.rsplit("/", 1)[-1]
    if base.endswith(".tmp.tar.gz"):
        return WRONG_NAME
    return None


def inspect_archive(
    local_tar_path: Path,
    row_count_tolerance: float = 0.05,
) -> Tuple[str, Dict]:
    """Open a .tar.gz and classify it.

    Returns (category, details). `details` always includes the callback-payload
    and marker read state; when row count is checked, it also includes
    `expected_count` and `actual_count`, and may include `secondary_tags` with
    one of:
    - `EXCESS_FILES`: actual > expected (Node's 'success' under-reports; archive
      is valid and contains more files than the counter claimed).
    - `FAILED_CRAWL_WITH_RESIDUE`: expected == 0 but files exist (crawl errored
      at the webhook-reporting step; archive still carries real data per
      Python's status_snapshot).
    - `COUNT_DRIFT`: deficit within `row_count_tolerance` (crawler-side
      accounting noise — retries counted twice, flush races, etc.).

    Only deficits above `row_count_tolerance` become `ROW_COUNT_MISMATCH`.
    """
    details: Dict = {}

    # 1. Integrity — can we open the tar at all?
    try:
        tar = tarfile.open(str(local_tar_path), "r:gz")
    except (tarfile.TarError, OSError, EOFError) as e:
        details["error"] = f"{type(e).__name__}: {e}"
        return CORRUPTED, details

    try:
        members = tar.getmembers()  # forces reading the full index; may raise on truncated tars
    except (tarfile.TarError, OSError, EOFError) as e:
        tar.close()
        details["error"] = f"{type(e).__name__}: {e}"
        return CORRUPTED, details

    try:
        # 2. Extract _callback_payload.json
        payload = _read_json_member(tar, "_callback_payload.json")
        if payload is None:
            details["missing"] = "_callback_payload.json"
            return MISSING_PAYLOAD, details
        details["payload"] = payload

        # 3. Extract _completion_marker.json
        marker = _read_json_member(tar, "_completion_marker.json")
        if marker is None:
            details["missing"] = "_completion_marker.json"
            return MISSING_MARKER, details
        details["marker"] = marker

        # 4. Resolve domain via multi-source lookup (payload, snapshot, tar inference).
        domain = _resolve_domain_name(tar, members, payload)

        # 5. Get expected count. Prefer _status_snapshot.json.urls_crawled when
        #    present — it matches the main-domain file count precisely. Node's
        #    'success' field conflates main + NFR + error counts and drifts by
        #    various magnitudes (confirmed live against 1806/selux.com:
        #    success=10054, urls_crawled=1324, main files=1324, nfr=8728).
        #    Fall back to payload's 'stored_files_count' or 'success' only when
        #    the snapshot is absent or lacks urls_crawled.
        snapshot = _read_json_member(tar, "_status_snapshot.json")
        expected = None
        if snapshot and isinstance(snapshot.get("urls_crawled"), (int, float)):
            expected = int(snapshot["urls_crawled"])
            details["expected_count_source"] = "snapshot.urls_crawled"
        else:
            fallback = payload.get("stored_files_count")
            if fallback is not None:
                expected = fallback
                details["expected_count_source"] = "payload.stored_files_count"
            else:
                fallback = payload.get("success")
                if fallback is not None:
                    expected = fallback
                    details["expected_count_source"] = "payload.success"

        # 6. Row count check — best-effort. Skip (with warning) if we lack either input.
        if domain is None:
            details["warning"] = "domain could not be resolved; row count check skipped"
            if expected is not None:
                details["expected_count"] = int(expected)
            return OK, details

        if expected is None:
            details["warning"] = "payload has no count field (stored_files_count/success); row count check skipped"
            details["domain"] = domain
            return OK, details

        actual = _count_dataset_files(members, domain)
        expected_int = int(expected)
        details["domain"] = domain
        details["expected_count"] = expected_int
        details["actual_count"] = actual

        # Edge case first: expected=0 with files on disk is a failed crawl
        # whose webhook step zeroed the counter (see `4398` investigation:
        # exit_code=2, success=0, but urls_crawled=108).
        if expected_int == 0:
            if actual > 0:
                details.setdefault("secondary_tags", []).append("FAILED_CRAWL_WITH_RESIDUE")
            return OK, details
        # Node's 'success' under-reports in some crawls (see `3487`: success=35
        # vs 1426 files). The archive is not corrupt; tag and pass.
        if actual > expected_int:
            details.setdefault("secondary_tags", []).append("EXCESS_FILES")
            return OK, details
        # Small drift (within tolerance) — crawler-side accounting noise
        # (see `2754`: success=267 vs 265 files; `5441`: success=21 vs 20).
        if actual < expected_int:
            deficit = expected_int - actual
            if deficit <= expected_int * row_count_tolerance:
                details.setdefault("secondary_tags", []).append("COUNT_DRIFT")
                return OK, details
            return ROW_COUNT_MISMATCH, details

        return OK, details
    finally:
        tar.close()


def _normalize_member_name(name: str) -> str:
    """Strip leading './' or '.' from tar member names.

    shutil.make_archive passes base_dir='.' to tarfile, which produces members
    like './_callback_payload.json' (not 'foo.txt'). Normalization lets us
    compare against unprefixed expected names regardless of how the tar was
    produced.
    """
    if name.startswith("./"):
        return name[2:]
    if name == ".":
        return ""
    return name


def _read_json_member(tar: tarfile.TarFile, name: str) -> Optional[Dict]:
    """Read and parse a JSON file from the tar. Handles tars produced by
    shutil.make_archive (which prefix members with './').

    Iterates members and compares by normalized name rather than using
    getmember() — getmember() is exact-name lookup and would miss './foo'
    when asked for 'foo'.
    """
    for member in tar.getmembers():
        if _normalize_member_name(member.name) == name:
            try:
                f = tar.extractfile(member)
                if f is None:
                    return None
                return json.loads(f.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                return None
    return None


def _count_dataset_files(members: List[tarfile.TarInfo], domain: str) -> int:
    """Count .json files under storage/datasets/{domain}/ (or sanitized variant).

    Normalizes member names before prefix comparison so './storage/datasets/...'
    correctly matches 'storage/datasets/...'.

    Returns the number of JSON files directly under the dataset directory.
    Matches the crawler's convention: one JSON file per successfully crawled URL.
    """
    sanitized = domain.replace(".", "-")
    candidates = [f"storage/datasets/{domain}/", f"storage/datasets/{sanitized}/"]

    for prefix in candidates:
        count = 0
        found_dir = False
        for m in members:
            normalized = _normalize_member_name(m.name)
            if normalized.startswith(prefix):
                found_dir = True
                # Only count files (not nested directories), and only .json
                name_after_prefix = normalized[len(prefix):]
                if m.isfile() and "/" not in name_after_prefix and name_after_prefix.endswith(".json"):
                    count += 1
        if found_dir:
            return count
    return 0


def _resolve_domain_name(
    tar: tarfile.TarFile,
    members: List[tarfile.TarInfo],
    payload: Dict,
) -> Optional[str]:
    """Resolve the crawl's domain name from multiple possible sources.

    Priority:
    1. payload['domain'] — not currently written by Node.js but future-proof
    2. _status_snapshot.json['domain'] — written by Python's archive_crawl
       (CrawlStatus model has domain as a required field)
    3. Inferred from tar structure: first 'storage/datasets/{X}/' where X does
       NOT start with a known special prefix (nfr-, error-, update-)

    Returns the domain name as a string, or None if all sources fail.
    """
    # 1. Try payload
    domain = payload.get("domain")
    if domain:
        return domain

    # 2. Try status snapshot (Python writes this before archiving)
    snapshot = _read_json_member(tar, "_status_snapshot.json")
    if snapshot:
        domain = snapshot.get("domain")
        if domain:
            return domain

    # 3. Infer from tar structure
    special_prefixes = ("nfr-", "error-", "update-")
    seen_candidates: Set[str] = set()
    for m in members:
        normalized = _normalize_member_name(m.name)
        if normalized.startswith("storage/datasets/"):
            parts = normalized.split("/", 3)  # e.g. 'storage/datasets/example.com' -> 3 parts
            if len(parts) >= 3 and parts[2]:
                candidate = parts[2]
                if candidate in seen_candidates:
                    continue
                seen_candidates.add(candidate)
                if not any(candidate.startswith(p) for p in special_prefixes):
                    return candidate

    return None


# ---- Orchestration ----

REPORT_FLUSH_INTERVAL = 50  # write partial report every N archives


def detect_duplicates(archives: List[Dict]) -> None:
    """Mutates `archives` in place. Adds 'DUPLICATE' to the `secondary_tags` list
    of any archive whose crawl_id appears in more than one object."""
    counts: Dict[str, int] = {}
    for a in archives:
        cid = a.get("crawl_id")
        if cid:
            counts[cid] = counts.get(cid, 0) + 1

    for a in archives:
        cid = a.get("crawl_id")
        if cid and counts.get(cid, 0) > 1:
            a.setdefault("secondary_tags", [])
            if "DUPLICATE" not in a["secondary_tags"]:
                a["secondary_tags"].append("DUPLICATE")


def remediate(obj_uri: str, category: str, action: str, quarantine_prefix: Optional[str], bucket: str) -> str:
    """Perform delete or quarantine for a bad archive. Returns a human-readable
    description of what was done. Does nothing when category == OK."""
    if category == OK:
        return ""
    if action == "delete":
        gcloud_delete(obj_uri)
        return f"deleted {obj_uri}"
    if action == "quarantine":
        assert quarantine_prefix is not None
        # Object name relative to bucket, e.g. "crawls/4365.tar.gz" → "<quarantine_prefix>/4365.tar.gz"
        rel = obj_uri.replace(f"gs://{bucket}/", "", 1)
        base = rel.rsplit("/", 1)[-1]
        dst = f"gs://{bucket}/{quarantine_prefix.rstrip('/')}/{base}"
        gcloud_move(obj_uri, dst)
        return f"quarantined to {dst}"
    return ""


def restore_from_quarantine(bucket: str, quarantine_prefix: str, target_prefix: str = "crawls/") -> int:
    """Move all objects from gs://{bucket}/{quarantine_prefix}/ back to
    gs://{bucket}/{target_prefix}/, preserving basenames.

    Used to recover from a faulty prior audit that quarantined false positives.
    Returns the count of successfully-moved objects. Individual failures are
    logged but do not abort the whole operation.
    """
    quarantine_uri = f"gs://{bucket}/{quarantine_prefix.rstrip('/')}/"
    listing = gcloud_ls(quarantine_uri)
    if not listing:
        print(f"No objects under {quarantine_uri}")
        return 0

    count = 0
    for obj_uri in listing:
        if not isinstance(obj_uri, str):
            # gcloud_ls called without long=True returns List[str]; defensive guard
            continue
        basename = obj_uri.rsplit("/", 1)[-1]
        dst = f"gs://{bucket}/{target_prefix.rstrip('/')}/{basename}"
        try:
            gcloud_move(obj_uri, dst)
            print(f"Restored: {basename}")
            count += 1
        except subprocess.CalledProcessError as e:
            stderr = e.stderr if hasattr(e, 'stderr') else str(e)
            print(f"Failed to restore {basename}: {stderr}", file=sys.stderr)
    return count


def write_report(path: Path, report: Dict) -> None:
    """Write the audit report to a JSON file with pretty formatting.
    Re-tallies the 'categories' counter from the archives list before writing."""
    counts: Dict[str, int] = {}
    for a in report.get("archives", []):
        counts[a["category"]] = counts.get(a["category"], 0) + 1
    report["categories"] = counts
    report["total_objects"] = len(report.get("archives", []))

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)


def _confirm_or_exit(action: str, quarantine_prefix: Optional[str]) -> None:
    msg = f"About to {action} bad archives" + (
        f" (quarantine prefix: {quarantine_prefix})" if action == "quarantine" else ""
    ) + ". Continue? [y/N] "
    try:
        reply = input(msg).strip().lower()
    except EOFError:
        reply = ""
    if reply not in ("y", "yes"):
        print("Aborted.", file=sys.stderr)
        sys.exit(1)


def _print_summary(report: Dict) -> None:
    print("\n=== GCS Archive Audit ===")
    print(f"Bucket: {report['bucket']}")
    print(f"Prefix: {report['prefix']}")
    print(f"Audited: {report['total_objects']} archives\n")
    print("Categories:")
    for cat in (OK, WRONG_NAME, CORRUPTED, MISSING_PAYLOAD, MISSING_MARKER,
                ROW_COUNT_MISMATCH, DUPLICATE, INSPECTION_FAILED):
        count = report["categories"].get(cat, 0)
        if count:
            pct = (100.0 * count / report["total_objects"]) if report["total_objects"] else 0
            print(f"  {cat:<24} {count:>5}  ({pct:.1f}%)")


def _load_resume_set(resume_path: Optional[str]) -> set:
    """Load previously-audited object names from a prior report so we can skip them."""
    if not resume_path:
        return set()
    p = Path(resume_path)
    if not p.exists():
        return set()
    try:
        with open(p, "r", encoding="utf-8") as f:
            prior = json.load(f)
        return {a["object_name"] for a in prior.get("archives", [])}
    except (json.JSONDecodeError, KeyError, OSError):
        return set()


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


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit GCS archives for corruption, incompleteness, and name issues."
    )
    parser.add_argument("--bucket", required=True, help="GCS bucket name (no gs:// prefix)")
    parser.add_argument("--prefix", default="crawls/", help="Object name prefix to scan (default: crawls/)")
    parser.add_argument("--output", default="gcs_archive_audit_report.json", help="Report output path")
    parser.add_argument("--name-only", action="store_true",
                        help="Fast mode: skip download/inspection, only check names")
    parser.add_argument("--limit", type=int, default=None,
                        help="Maximum number of archives to audit (for testing)")
    parser.add_argument("--delete", action="store_true",
                        help="Delete bad archives (mutually exclusive with --quarantine)")
    parser.add_argument("--quarantine", default=None,
                        help="Prefix inside bucket to move bad archives to (mutually exclusive with --delete)")
    parser.add_argument("--yes", action="store_true",
                        help="Skip the confirmation prompt for --delete/--quarantine")
    parser.add_argument("--resume", default=None,
                        help="Skip archives already present in the given prior report")
    parser.add_argument("--include-ids", default=None, metavar="SPEC",
                        help="Comma-separated list of crawl_ids, or path to a file "
                             "with one ID per line. Only audit archives whose "
                             "extracted crawl_id is in this set.")
    parser.add_argument("--row-count-tolerance", type=float, default=0.05,
                        metavar="FRACTION",
                        help="Deficit fraction tolerated before flagging "
                             "ROW_COUNT_MISMATCH (default 0.05 = 5%%). "
                             "Archives within tolerance classify OK with "
                             "secondary tag COUNT_DRIFT.")
    parser.add_argument("--restore-from-quarantine", default=None, metavar="PREFIX",
                        help="Move all objects from gs://<bucket>/<PREFIX>/ back to "
                             "gs://<bucket>/<--prefix>/, then exit. Used to recover from "
                             "a faulty prior audit run.")
    args = parser.parse_args(argv)

    if args.delete and args.quarantine:
        parser.error("--delete and --quarantine are mutually exclusive")
    return args


def _inspect_one(
    obj_uri: str,
    size_bytes: int,
    name_only: bool,
    row_count_tolerance: float = 0.05,
) -> Tuple[str, Dict]:
    """Inspect a single archive. Returns (category, details)."""
    # Name-based screening first — cheap and catches WRONG_NAME without download.
    name_cat = classify_by_name(obj_uri)
    if name_cat is not None:
        return name_cat, {}
    if name_only:
        return OK, {}

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        try:
            gcloud_download(obj_uri, tmp_path)
        except subprocess.CalledProcessError as e:
            return INSPECTION_FAILED, {"error": f"download failed: {e.stderr}"}
        return inspect_archive(tmp_path, row_count_tolerance=row_count_tolerance)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    check_gcloud_auth()

    # Early exit: restore-from-quarantine is a separate top-level operation.
    # It does not run the normal audit flow.
    if args.restore_from_quarantine:
        if not args.yes:
            _confirm_or_exit(
                f"restore from quarantine '{args.restore_from_quarantine}'",
                quarantine_prefix=None,
            )
        count = restore_from_quarantine(
            args.bucket, args.restore_from_quarantine, args.prefix
        )
        print(f"\nRestored {count} objects.")
        return 0

    action: Optional[str] = None
    if args.delete:
        action = "delete"
    elif args.quarantine:
        action = "quarantine"
    if action and not args.yes:
        _confirm_or_exit(action, args.quarantine)

    # Build initial report skeleton
    report: Dict = {
        "bucket": args.bucket,
        "prefix": args.prefix,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "total_objects": 0,
        "categories": {},
        "archives": [],
    }
    report_path = Path(args.output)

    # SIGINT handler to write partial report before exiting
    def _on_sigint(signum, frame):
        print("\nInterrupted — writing partial report...", file=sys.stderr)
        detect_duplicates(report["archives"])
        write_report(report_path, report)
        sys.exit(130)

    signal.signal(signal.SIGINT, _on_sigint)

    skip_set = _load_resume_set(args.resume)
    include_ids = _load_include_ids(args.include_ids)

    # List
    uri = f"gs://{args.bucket}/{args.prefix}"
    listing = gcloud_ls(uri, long=True)
    total = len(listing)
    print(f"Found {total} objects under {uri}. Beginning audit...")

    processed = 0
    for size_bytes, obj_uri in listing:
        # skip_set holds bucket-stripped object_names (same shape as stored in the report).
        # Normalize obj_uri to match before checking.
        normalized_name = obj_uri.replace(f"gs://{args.bucket}/", "", 1)
        if normalized_name in skip_set:
            continue
        if include_ids is not None:
            cid = extract_crawl_id(obj_uri)
            if cid not in include_ids:
                continue
        if args.limit is not None and processed >= args.limit:
            break
        processed += 1

        entry: Dict = {
            "object_name": obj_uri.replace(f"gs://{args.bucket}/", "", 1),
            "crawl_id": extract_crawl_id(obj_uri),
            "size_bytes": size_bytes,
            "category": OK,
            "secondary_tags": [],
            "actions_taken": [],
        }

        category, details = _inspect_one(
            obj_uri,
            size_bytes,
            args.name_only,
            row_count_tolerance=args.row_count_tolerance,
        )
        entry["category"] = category
        for tag in details.get("secondary_tags", []):
            if tag not in entry["secondary_tags"]:
                entry["secondary_tags"].append(tag)
        if details.get("expected_count") is not None:
            entry["expected_count"] = details["expected_count"]
            entry["actual_count"] = details["actual_count"]
        if details.get("error"):
            entry["error"] = details["error"]

        if action and category != OK:
            try:
                note = remediate(obj_uri, category, action, args.quarantine, args.bucket)
                if note:
                    entry["actions_taken"].append(note)
            except subprocess.CalledProcessError as e:
                entry["actions_taken"].append(f"remediation failed: {e.stderr}")

        report["archives"].append(entry)

        if processed % REPORT_FLUSH_INTERVAL == 0:
            detect_duplicates(report["archives"])
            write_report(report_path, report)
            print(f"  ...audited {processed}/{total}")

    # Final duplicate detection + write
    detect_duplicates(report["archives"])
    write_report(report_path, report)
    _print_summary(report)
    print(f"\nFull report written to: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
