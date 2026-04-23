"""Tests for tools/restore_from_reaudit.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

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
            count = rr.restore(
                input_path=path, bucket="b", target_prefix="crawls/",
                log_path=tmp_path / "log.md", dry_run=False,
            )

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
            count = rr.restore(
                input_path=path, bucket="b", target_prefix="crawls/",
                log_path=tmp_path / "log.md", dry_run=False,
            )

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
            rr.restore(
                input_path=path, bucket="b", target_prefix="crawls/",
                log_path=tmp_path / "log.md", dry_run=False,
            )

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
            count = rr.restore(
                input_path=path, bucket="b", target_prefix="crawls/",
                log_path=tmp_path / "log.md", dry_run=False,
            )

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
             patch("restore_from_reaudit._exists", return_value=False) as mock_exists:
            count = rr.restore(
                input_path=path, bucket="b", target_prefix="crawls/",
                log_path=tmp_path / "log.md", dry_run=True,
            )

        assert count == 1  # would-have-been moved
        mock_mv.assert_not_called()
        mock_exists.assert_called_once()  # collision check still runs in dry-run
        log = (tmp_path / "log.md").read_text()
        assert "DRY-RUN" in log
