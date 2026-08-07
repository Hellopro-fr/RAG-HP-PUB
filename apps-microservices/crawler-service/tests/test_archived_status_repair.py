# tests/test_archived_status_repair.py
"""Predicate for the archived-status repair pass.

The evaluation ORDER is part of the contract: the dry-run endpoint reports the
first failing condition, so two implementations that disagree on order produce
different operator-facing counts for the same Redis state.

The log/snapshot comparison replaces an earlier marker-based check that was
fail-OPEN: _cleanup_stale_state_for_relaunch deletes _completion_marker.json on
every relaunch (crawler_manager.py:3494) and _monitor_process writes
status='finished' at :1284 but the marker only at :1298, swallowing failures at
:1301. A re-crawled id caught in that window would have been flipped to
'archived', making /results serve the previous generation's tar.
"""
import pytest

from app.core import archived_status_repair as asr

VERIFIED = {"6712", "6713"}


def _call(**over):
    kw = dict(
        crawl_id="6712",
        status="finished",
        stashed_at=None,
        verified_ids=VERIFIED,
        snapshot_mtime=200.0,
        log_mtime=100.0,
    )
    kw.update(over)
    return asr.classify(**kw)


def test_nominal_archived_crawl_is_a_candidate():
    assert _call() is None
    assert asr.is_status_repair_candidate(
        crawl_id="6712", status="finished", stashed_at=None,
        verified_ids=VERIFIED, snapshot_mtime=200.0, log_mtime=100.0) is True


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
                        log_mtime=100.0) is None


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


def test_evaluation_order_is_first_failure_wins():
    # Stashed AND absent from the allowlist AND no snapshot: bucket must be the
    # earliest failing condition, or the dry-run's counts are not reproducible.
    assert _call(stashed_at="x", crawl_id="9999", snapshot_mtime=None) == asr.STASHED
    assert _call(status="archived", stashed_at="x") == asr.NOT_FINISHED


def test_module_is_pure():
    import inspect
    src = inspect.getsource(asr)
    for forbidden in ("import os", "import redis", "cache_service", "open("):
        assert forbidden not in src, f"pure predicate module must not reference {forbidden}"
