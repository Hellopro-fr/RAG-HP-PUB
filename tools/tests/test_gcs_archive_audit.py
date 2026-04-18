"""Tests for tools/gcs_archive_audit.py."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import gcs_archive_audit as ga


class TestExtractCrawlId:
    def test_plain_tar_gz(self):
        assert ga.extract_crawl_id("crawls/4365.tar.gz") == "4365"

    def test_tmp_tar_gz(self):
        assert ga.extract_crawl_id("crawls/4365.tmp.tar.gz") == "4365"

    def test_full_gs_uri(self):
        assert ga.extract_crawl_id("gs://my-bucket/crawls/4365.tar.gz") == "4365"

    def test_unrecognized_name(self):
        assert ga.extract_crawl_id("gs://my-bucket/crawls/weird") is None

    def test_empty_crawl_id(self):
        # `.tar.gz` alone should not produce an empty string crawl_id
        assert ga.extract_crawl_id("crawls/.tar.gz") is None


class TestCheckGcloudAuth:
    def test_exits_when_gcloud_not_installed(self, capsys):
        with patch("gcs_archive_audit._run_gcloud", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit) as exc:
                ga.check_gcloud_auth()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "gcloud" in err.lower()

    def test_exits_when_no_active_account(self, capsys):
        mock_result = MagicMock(stdout="", stderr="")
        with patch("gcs_archive_audit._run_gcloud", return_value=mock_result):
            with pytest.raises(SystemExit) as exc:
                ga.check_gcloud_auth()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "No active gcloud account" in err

    def test_passes_when_account_active(self):
        mock_result = MagicMock(stdout="user@example.com\n", stderr="")
        with patch("gcs_archive_audit._run_gcloud", return_value=mock_result):
            # Should not raise
            ga.check_gcloud_auth()


class TestGcloudLs:
    def test_short_listing(self):
        mock_result = MagicMock(
            stdout="gs://bucket/crawls/a.tar.gz\ngs://bucket/crawls/b.tar.gz\n",
            stderr="",
        )
        with patch("gcs_archive_audit._run_gcloud", return_value=mock_result):
            result = ga.gcloud_ls("gs://bucket/crawls/")
        assert result == [
            "gs://bucket/crawls/a.tar.gz",
            "gs://bucket/crawls/b.tar.gz",
        ]

    def test_long_listing_parses_size(self):
        mock_result = MagicMock(
            stdout=(
                "12582912  2026-04-01T10:00:00Z  gs://bucket/crawls/a.tar.gz\n"
                "524288  2026-04-01T11:00:00Z  gs://bucket/crawls/b.tar.gz\n"
                "TOTAL: 2 objects, 13107200 bytes\n"
            ),
            stderr="",
        )
        with patch("gcs_archive_audit._run_gcloud", return_value=mock_result):
            result = ga.gcloud_ls("gs://bucket/crawls/", long=True)
        assert result == [
            (12582912, "gs://bucket/crawls/a.tar.gz"),
            (524288, "gs://bucket/crawls/b.tar.gz"),
        ]

    def test_returns_empty_on_error(self, capsys):
        err = subprocess.CalledProcessError(1, "gcloud", stderr="permission denied")
        with patch("gcs_archive_audit._run_gcloud", side_effect=err):
            result = ga.gcloud_ls("gs://bucket/crawls/")
        assert result == []


class TestGcloudOperations:
    def test_download_shells_out(self, tmp_path):
        with patch("gcs_archive_audit._run_gcloud") as mock_run:
            ga.gcloud_download("gs://bucket/obj.tar.gz", tmp_path / "x.tar.gz")
        mock_run.assert_called_once_with(
            ["storage", "cp", "gs://bucket/obj.tar.gz", str(tmp_path / "x.tar.gz")]
        )

    def test_delete_shells_out(self):
        with patch("gcs_archive_audit._run_gcloud") as mock_run:
            ga.gcloud_delete("gs://bucket/obj.tar.gz")
        mock_run.assert_called_once_with(["storage", "rm", "gs://bucket/obj.tar.gz"])

    def test_move_shells_out(self):
        with patch("gcs_archive_audit._run_gcloud") as mock_run:
            ga.gcloud_move("gs://bucket/a", "gs://bucket/b")
        mock_run.assert_called_once_with(["storage", "mv", "gs://bucket/a", "gs://bucket/b"])
