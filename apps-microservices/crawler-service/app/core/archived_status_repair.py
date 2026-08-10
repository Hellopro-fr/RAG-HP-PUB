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
# A snapshot rewrite not yet (or never) followed by a successful archive: the
# tar is in flight, or the process died mid-tar. Unlike condition 5, this one
# does NOT self-clear when the archive completes normally — archiving again
# rewrites the snapshot, so a failed attempt leaves it permanently "recent"
# relative to nothing but wall-clock time (spec S4/I-3).
SNAPSHOT_TOO_RECENT = "snapshot_too_recent"
# Condition 7 is NOT evaluated by classify(): it needs a Redis round trip, and the
# caller runs it LAST so the EXISTS is only paid for blobs that already passed 1-6.
# The constant lives here so both callers report the same bucket name.
ARCHIVE_IN_PROGRESS = "archive_in_progress"


def archive_freshness_verdict(log_mtime: Optional[float],
                              snapshot_mtime: Optional[float]) -> Optional[str]:
    """NO_SNAPSHOT / RUN_AFTER_ARCHIVE, or None when the archive postdates the tree.

    `_status_snapshot.json` is written only on the real archiving path
    (crawler_manager.py:2627). archive_crawl's two shortcut branches — local-tar
    reuse (:2570-2578) and the GCS fallback (:2583-2594) — return before reaching
    it, and _mark_as_archived (:2729-2741) never touches it. Its mtime therefore
    answers "when was a tar actually produced", which is the only local evidence
    of the attested tar's age. `archived_at` cannot serve: _mark_as_archived
    rewrites it in BOTH shortcut branches, so it reads "just now" precisely when
    the tar is old.

    Both passes need this comparison and used to disagree about it: the repair
    rejected on it, the destructive sweep never checked at all. Sharing one
    predicate makes that divergence impossible to reintroduce — which is the
    actual cause of the data-loss defect, not a DRY preference.

    Returns the module's existing bucket constants rather than new strings: the
    repair's dry-run already counts these two by name, and the sweep's per-tick
    summary must agree with it.

    Missing evidence rejects — absence of proof is not proof. Equal timestamps
    reject too, for the same reason the .move-done guard uses a strict
    comparison: the error leans the safe way.
    """
    if snapshot_mtime is None:
        return NO_SNAPSHOT
    if log_mtime is None or log_mtime >= snapshot_mtime:
        return RUN_AFTER_ARCHIVE
    return None


def classify(
    crawl_id: Union[str, int],
    status: Optional[str],
    stashed_at: Optional[str],
    verified_ids: AbstractSet[str],
    snapshot_mtime: Optional[float],
    log_mtime: Optional[float],
    snapshot_age_seconds: Optional[float],
    min_snapshot_age_seconds: float,
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
        snapshot_age_seconds: caller-computed `now - snapshot_mtime` (this module
            never touches wall-clock time, so it takes the result rather than the
            inputs). None must reject, same as an absent log_mtime.
        min_snapshot_age_seconds: the caller's settings.ARCHIVED_RECLEAN_MIN_AGE_SECONDS
            — reused rather than a new setting, passed in rather than imported so
            this module stays dependency-free.

    The log/snapshot comparison is what separates "archived and untouched since"
    from "archived, then re-crawled". crawler.log is appended for the whole run and
    _cleanup_local_data keeps it deliberately (crawler_manager.py:2650-2653), so
    nothing removes it — unlike _completion_marker.json, which
    _cleanup_stale_state_for_relaunch deletes on every relaunch.

    The age check (condition 6) closes a gap condition 5 leaves open: a genuine
    repair target was archived days ago, so its snapshot is old; a snapshot
    written minutes ago means an archive is currently running or just failed
    partway through — condition 5 alone cannot tell these apart, because a
    fresh snapshot is by construction the most recently touched file in the
    crawl dir regardless of which case it is.
    """
    if status != "finished":
        return NOT_FINISHED
    if stashed_at:
        return STASHED
    if str(crawl_id) not in verified_ids:
        return NOT_IN_GCS_LIST
    freshness = archive_freshness_verdict(log_mtime, snapshot_mtime)
    if freshness is not None:
        return freshness
    if snapshot_age_seconds is None or snapshot_age_seconds <= min_snapshot_age_seconds:
        return SNAPSHOT_TOO_RECENT
    return None


def is_status_repair_candidate(**kwargs) -> bool:
    """Boolean form of classify(), for callers that don't need the bucket."""
    return classify(**kwargs) is None
