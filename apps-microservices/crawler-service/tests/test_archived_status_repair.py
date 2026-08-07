# tests/test_archived_status_repair.py
"""Predicate for the archived-status repair pass.

The evaluation ORDER is part of the contract: the dry-run endpoint reports the
first failing condition, so two implementations that disagree on order produce
different operator-facing counts for the same Redis state.

The log/snapshot comparison replaces an earlier marker-based check that was
fail-OPEN: _cleanup_stale_state_for_relaunch deletes _completion_marker.json on
every relaunch (crawler_manager.py:3511) and _monitor_process writes
status='finished' at :1284 but the marker only at :1298, swallowing failures at
:1301. A re-crawled id caught in that window would have been flipped to
'archived', making /results serve the previous generation's tar.

Condition 6 (snapshot age) closes a second gap the same shape as the first:
condition 5 alone is fail-open on a snapshot rewrite NOT followed by a
successful archive (tar raises, process dies mid-tar) — the log stays older
than the fresh snapshot forever, and nothing else clears it. A caller-computed
age + the ARCHIVED_RECLEAN_MIN_AGE_SECONDS threshold (mirrored here, not
imported — the module stays dependency-free) rejects a snapshot that is too
recent to be a settled archive.
"""
import pytest

from app.core import archived_status_repair as asr

VERIFIED = {"6712", "6713"}

# Mirrors settings.ARCHIVED_RECLEAN_MIN_AGE_SECONDS (86400) for test readability
# only — the module itself takes the threshold as a parameter, it does not know
# this value.
MIN_AGE = 86400.0


def _call(**over):
    kw = dict(
        crawl_id="6712",
        status="finished",
        stashed_at=None,
        verified_ids=VERIFIED,
        snapshot_mtime=200.0,
        log_mtime=100.0,
        snapshot_age_seconds=MIN_AGE * 10,
        min_snapshot_age_seconds=MIN_AGE,
    )
    kw.update(over)
    return asr.classify(**kw)


def test_nominal_archived_crawl_is_a_candidate():
    assert _call() is None
    assert asr.is_status_repair_candidate(
        crawl_id="6712", status="finished", stashed_at=None,
        verified_ids=VERIFIED, snapshot_mtime=200.0, log_mtime=100.0,
        snapshot_age_seconds=MIN_AGE * 10, min_snapshot_age_seconds=MIN_AGE) is True


@pytest.mark.parametrize("status", ["archived", "failed", "stopped", "running", None])
def test_condition_1_rejects_non_finished(status):
    assert _call(status=status) == asr.NOT_FINISHED


def test_condition_2_rejects_stashed():
    assert _call(stashed_at="2026-08-01T10:00:00") == asr.STASHED


def test_condition_3_rejects_id_absent_from_allowlist():
    assert _call(crawl_id="9999") == asr.NOT_IN_GCS_LIST


def test_condition_3_compares_as_string():
    # Redis blobs carry crawl_id as a string; the allowlist is parsed as strings.
    assert asr.classify(crawl_id=6712, status="finished", stashed_at=None,
                        verified_ids=VERIFIED, snapshot_mtime=200.0,
                        log_mtime=100.0, snapshot_age_seconds=MIN_AGE * 10,
                        min_snapshot_age_seconds=MIN_AGE) is None


def test_condition_4_rejects_missing_snapshot():
    assert _call(snapshot_mtime=None) == asr.NO_SNAPSHOT


def test_condition_5_rejects_missing_log():
    # THE regression this predicate exists for: absent evidence must never pass.
    assert _call(log_mtime=None) == asr.RUN_AFTER_ARCHIVE


def test_condition_5_rejects_log_newer_than_snapshot():
    assert _call(log_mtime=300.0, snapshot_mtime=200.0) == asr.RUN_AFTER_ARCHIVE


def test_condition_5_rejects_equal_mtimes():
    # Strictly-older only: equality is unresolvable, so it must not authorize a write.
    assert _call(log_mtime=200.0, snapshot_mtime=200.0) == asr.RUN_AFTER_ARCHIVE


def test_condition_6_rejects_snapshot_below_min_age():
    # A snapshot written minutes ago means an archive is in flight or just died
    # (I-3) — not a settled repair target, even though 1-5 all pass.
    assert _call(snapshot_age_seconds=MIN_AGE - 1) == asr.SNAPSHOT_TOO_RECENT


def test_condition_6_accepts_snapshot_above_min_age():
    assert _call(snapshot_age_seconds=MIN_AGE + 1) is None


def test_condition_6_rejects_equal_age():
    # Strictly-older only, same rule as condition 5's mtime comparison.
    assert _call(snapshot_age_seconds=MIN_AGE) == asr.SNAPSHOT_TOO_RECENT


def test_condition_6_rejects_none_age():
    # Absent evidence must never authorize a write — same shape as condition 5's
    # None-log-mtime case, and the reason condition 5 alone was fail-open on a
    # died-mid-tar archive (I-3).
    assert _call(snapshot_age_seconds=None) == asr.SNAPSHOT_TOO_RECENT


def test_evaluation_order_is_first_failure_wins():
    # Stashed AND absent from the allowlist AND no snapshot: bucket must be the
    # earliest failing condition, or the dry-run's counts are not reproducible.
    assert _call(stashed_at="x", crawl_id="9999", snapshot_mtime=None) == asr.STASHED
    assert _call(status="archived", stashed_at="x") == asr.NOT_FINISHED
    # Condition 6 only evaluated once 1-5 all pass.
    assert _call(log_mtime=None, snapshot_age_seconds=None) == asr.RUN_AFTER_ARCHIVE


def test_module_is_pure():
    import inspect
    src = inspect.getsource(asr)
    for forbidden in ("import os", "import redis", "import time", "cache_service", "open("):
        assert forbidden not in src, f"pure predicate module must not reference {forbidden}"
