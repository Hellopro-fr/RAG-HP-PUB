"""Build the update-mode re-ingestion queue from a gcs_archive_audit report.

Reads a report (e.g. `corrected_report.json`), applies inclusion rules
(CORRUPTED without local replacement; ROW_COUNT_MISMATCH with deficit above
threshold; excluding classifier-bug patterns and entries with tmp siblings),
and writes a JSON artifact with two lists:
  - `entries`: actionable now via update-mode
  - `deferred_to_phase2`: metadata for later decisions

Optionally uploads the artifact to GCS via `gcloud storage cp`.

Run:
    python tools/build_update_mode_queue.py \
        --input corrected_report.json \
        --exclude-ids 1806,2517,4683,4699 \
        --deficit-threshold 0.30 \
        --output update_mode_queue.json \
        --upload gs://<bucket>/remediation/update_mode_queue_<date>.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set


def load_report(path: Path) -> Dict:
    """Load a gcs_archive_audit report JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_exclude_ids(spec: Optional[str]) -> Set[str]:
    """Parse --exclude-ids input (comma-separated string or empty)."""
    if not spec:
        return set()
    return {s.strip() for s in spec.split(",") if s.strip()}


def _has_tmp_sibling(all_entries: List[Dict], crawl_id: str) -> bool:
    """Return True if any entry with the given crawl_id has a .tmp.tar.gz object_name."""
    for e in all_entries:
        if (
            e.get("crawl_id") == crawl_id
            and e.get("object_name", "").endswith(".tmp.tar.gz")
        ):
            return True
    return False


def classify_entry(
    entry: Dict,
    all_entries: List[Dict],
    exclude_ids: Set[str],
    deficit_threshold: float,
) -> Optional[Dict]:
    """Classify a single report entry for the update-mode queue.

    Returns a dict with `bucket` ('entries' or 'deferred_to_phase2'), `reason`,
    and `detail`; or None if the entry doesn't belong in either list (OK,
    WRONG_NAME, excluded by ID, or a .tmp sibling entry itself).
    """
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
        return None  # OK or WRONG_NAME — not queue material

    # Skip the .tmp sibling entry itself — only the main (.tar.gz) drives the decision.
    obj = entry.get("object_name", "")
    if obj.endswith(".tmp.tar.gz"):
        return None

    expected = entry.get("expected_count", 0) or 0
    actual = entry.get("actual_count", 0) or 0

    # Defer classifier-bug patterns (should be reclassified after Phase 2.1,
    # but old reports may still list them as ROW_COUNT_MISMATCH).
    # Order matters: expected=0 && actual>0 also satisfies "actual > expected",
    # so the zero-edge case must be checked first.
    if expected == 0:
        return {
            "bucket": "deferred_to_phase2",
            "reason": "EXPECTED_ZERO_LIKELY_CLASSIFIER_BUG",
            "detail": f"expected=0 actual={actual}",
        }
    if actual > expected:
        return {
            "bucket": "deferred_to_phase2",
            "reason": "EXCESS_LIKELY_CLASSIFIER_BUG",
            "detail": f"expected={expected} actual={actual}",
        }

    # Hold crawl_ids with a .tmp.tar.gz sibling — the tmp might carry more data.
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
    """Walk the report's archives, classify each, and build the queue artifact."""
    all_entries = report.get("archives", [])
    bucket_name = report.get("bucket", "{bucket}")

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
            "quarantine_uri": (
                f"gs://{bucket_name}/crawls-quarantine/"
                f"{entry['object_name'].rsplit('/', 1)[-1]}"
            ),
            "notes": [],
        }
        if classified["bucket"] == "entries":
            entries.append(payload)
        else:
            deferred.append(
                {k: v for k, v in payload.items() if k in ("crawl_id", "reason", "detail")}
            )

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
    """Upload a local file to a gs:// URI via gcloud storage cp."""
    subprocess.run(
        ["gcloud", "storage", "cp", str(local_path), gs_uri],
        check=True,
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the update-mode re-ingestion queue from a gcs_archive_audit report."
    )
    parser.add_argument("--input", required=True, help="Path to corrected_report.json")
    parser.add_argument("--output", required=True, help="Local output path for the queue JSON")
    parser.add_argument("--exclude-ids", default="",
                        help="Comma-separated crawl_ids to skip (e.g. Phase 1A survivors)")
    parser.add_argument("--deficit-threshold", type=float, default=0.30,
                        help="ROW_COUNT_MISMATCH deficit threshold for "
                             "MAJOR_UNDER_DELIVERY (default 0.30 = 30%%)")
    parser.add_argument("--source-report-uri",
                        default="gs://{bucket}/remediation/2026-04-19_corrected_report.json",
                        help="Source report URI to record in the artifact")
    parser.add_argument("--generator",
                        default="tools/build_update_mode_queue.py",
                        help="Generator identifier recorded in the artifact")
    parser.add_argument("--upload", default=None,
                        help="If set, upload the generated queue to this gs:// URI "
                             "via gcloud storage cp.")
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

    print(f"entries:            {len(queue['entries'])}")
    print(f"deferred_to_phase2: {len(queue['deferred_to_phase2'])}")
    print(f"written to:         {args.output}")

    if args.upload:
        upload_to_gcs(Path(args.output), args.upload)
        print(f"uploaded to:        {args.upload}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
