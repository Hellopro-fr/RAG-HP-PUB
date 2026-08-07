"""Predicate for the archived-status repair pass.

Pure by construction: no I/O, no framework imports, every input a primitive
gathered by the caller. The whole decision is therefore unit-testable without
Docker, Redis or a filesystem — which matters because the local environment has
neither.

Spec: docs/superpowers/specs/2026-08-07-archived-status-repair-design.md
"""
from typing import AbstractSet, Optional, Union

# Rejection buckets, in evaluation order. These strings are part of the
# GET /admin/archived-status-repair contract — a blob failing several conditions
# is counted in the FIRST one, so renaming or reordering changes what operators
# read.
NOT_FINISHED = "not_finished"
STASHED = "stashed"
NOT_IN_GCS_LIST = "not_in_gcs_list"
NO_SNAPSHOT = "no_snapshot"
RUN_AFTER_ARCHIVE = "run_after_archive"
# Condition 6 is NOT evaluated by classify(): it needs a Redis round trip, and the
# caller runs it LAST so the EXISTS is only paid for blobs that already passed 1-5.
# The constant lives here so both callers report the same bucket name.
ARCHIVE_IN_PROGRESS = "archive_in_progress"


def classify(
    crawl_id: Union[str, int],
    status: Optional[str],
    stashed_at: Optional[str],
    verified_ids: AbstractSet[str],
    snapshot_mtime: Optional[float],
    log_mtime: Optional[float],
) -> Optional[str]:
    """Return None when the crawl must be repaired to 'archived', else the name
    of the FIRST condition it fails.

    Args:
        crawl_id: coerced to str — Redis blobs and the allowlist both hold strings.
        status: the blob's status field.
        stashed_at: truthy means the tar is under stash/, not crawls/.
        verified_ids: ids listed by tools/verify_archives_in_gcs.sh. The container
            has no GCS access; this file is the only admissible evidence.
        snapshot_mtime: mtime of {storage_path}/_status_snapshot.json, or None when
            the file is absent. Any OTHER stat error must make the caller skip the
            crawl entirely rather than pass None here.
        log_mtime: mtime of {storage_path}/crawler.log, same rule.

    The log/snapshot comparison is what separates "archived and untouched since"
    from "archived, then re-crawled". crawler.log is appended for the whole run and
    _cleanup_local_data keeps it deliberately (crawler_manager.py:2637-2640), so
    nothing removes it — unlike _completion_marker.json, which
    _cleanup_stale_state_for_relaunch deletes on every relaunch.
    """
    if status != "finished":
        return NOT_FINISHED
    if stashed_at:
        return STASHED
    if str(crawl_id) not in verified_ids:
        return NOT_IN_GCS_LIST
    if snapshot_mtime is None:
        return NO_SNAPSHOT
    if log_mtime is None or log_mtime >= snapshot_mtime:
        return RUN_AFTER_ARCHIVE
    return None


def is_status_repair_candidate(**kwargs) -> bool:
    """Boolean form of classify(), for callers that don't need the bucket."""
    return classify(**kwargs) is None
