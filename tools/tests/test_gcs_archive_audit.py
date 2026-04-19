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


import json as _json
import shutil as _shutil
import tarfile as _tarfile
from typing import Dict


def _build_tar(tmp_path: Path, files: Dict[str, bytes], name: str = "test") -> Path:
    """Helper: build a realistic tar.gz using shutil.make_archive.

    This matches the crawler's actual archiving code path (crawler_manager.py's
    `_create_archive` calls `shutil.make_archive(..., root_dir=job_storage_path)`).
    Resulting members will have './' prefix — exactly as real archives do.

    `files` is a dict of { path_in_tar: bytes_content }. The `name` parameter
    is the base name (without extension); the returned path ends in `.tar.gz`.
    """
    staging = tmp_path / f"staging_{name}"
    staging.mkdir(exist_ok=True)
    for path, content in files.items():
        full_path = staging / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
    archive_base = str(tmp_path / name)
    archive_path = _shutil.make_archive(archive_base, 'gztar', root_dir=str(staging))
    return Path(archive_path)


def _payload(domain: str = "example.com", stored: int = 3, success=None) -> bytes:
    data = {"domain": domain, "stored_files_count": stored}
    if success is not None:
        data["success"] = success
    return _json.dumps(data).encode()


def _marker() -> bytes:
    return _json.dumps({"final_status": "finished", "exit_code": 0}).encode()


class TestClassifyByName:
    def test_tmp_tar_gz_is_wrong_name(self):
        assert ga.classify_by_name("crawls/4365.tmp.tar.gz") == ga.WRONG_NAME

    def test_plain_tar_gz_is_none(self):
        assert ga.classify_by_name("crawls/4365.tar.gz") is None

    def test_full_gs_uri(self):
        assert ga.classify_by_name("gs://b/crawls/4365.tmp.tar.gz") == ga.WRONG_NAME


class TestArchiveInspection:
    def _ok_tar(self, tmp_path: Path) -> Path:
        """Build a tar with payload, marker, and 3 dataset files — matches stored_files_count=3."""
        return _build_tar(tmp_path, {
            "_callback_payload.json": _payload(domain="example.com", stored=3),
            "_completion_marker.json": _marker(),
            "storage/datasets/example.com/url1.json": b'{"url": "a"}',
            "storage/datasets/example.com/url2.json": b'{"url": "b"}',
            "storage/datasets/example.com/url3.json": b'{"url": "c"}',
        })

    def test_ok_archive(self, tmp_path):
        path = self._ok_tar(tmp_path)
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["expected_count"] == 3
        assert details["actual_count"] == 3

    def test_corrupted_archive(self, tmp_path):
        # Write random bytes that are not a valid gzip
        path = tmp_path / "bad.tar.gz"
        path.write_bytes(b"this is not a gzip file at all")
        category, details = ga.inspect_archive(path)
        assert category == ga.CORRUPTED
        assert "error" in details

    def test_missing_payload(self, tmp_path):
        path = _build_tar(tmp_path, {
            "_completion_marker.json": _marker(),
            # no _callback_payload.json
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.MISSING_PAYLOAD
        assert "_callback_payload.json" in details.get("missing", "")

    def test_missing_marker(self, tmp_path):
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(stored=3),
            # no _completion_marker.json
            "storage/datasets/example.com/x.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.MISSING_MARKER
        assert "_completion_marker.json" in details.get("missing", "")

    def test_row_count_mismatch(self, tmp_path):
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(stored=5),  # claims 5
            "_completion_marker.json": _marker(),
            # but only 2 dataset files
            "storage/datasets/example.com/a.json": b'{}',
            "storage/datasets/example.com/b.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.ROW_COUNT_MISMATCH
        assert details["expected_count"] == 5
        assert details["actual_count"] == 2

    def test_sanitized_domain_fallback(self, tmp_path):
        """If storage/datasets/{domain}/ is missing but the sanitized variant exists, use it."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(domain="foo.com", stored=1),
            "_completion_marker.json": _marker(),
            # Only sanitized variant exists (foo-com not foo.com)
            "storage/datasets/foo-com/only.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["actual_count"] == 1

    def test_success_field_fallback(self, tmp_path):
        """If stored_files_count is absent but success is present, use success."""
        payload = _json.dumps({"domain": "example.com", "success": 2}).encode()
        path = _build_tar(tmp_path, {
            "_callback_payload.json": payload,
            "_completion_marker.json": _marker(),
            "storage/datasets/example.com/a.json": b'{}',
            "storage/datasets/example.com/b.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["expected_count"] == 2

    def test_payload_missing_domain_field(self, tmp_path):
        payload = _json.dumps({"stored_files_count": 3}).encode()  # no domain
        path = _build_tar(tmp_path, {
            "_callback_payload.json": payload,
            "_completion_marker.json": _marker(),
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.MISSING_PAYLOAD
        assert "domain" in details.get("missing", "")


class TestDetectDuplicates:
    def test_tags_duplicate_crawl_ids(self):
        archives = [
            {"object_name": "crawls/4365.tar.gz", "crawl_id": "4365", "category": ga.OK, "secondary_tags": []},
            {"object_name": "crawls/4365.tmp.tar.gz", "crawl_id": "4365", "category": ga.WRONG_NAME, "secondary_tags": []},
            {"object_name": "crawls/5000.tar.gz", "crawl_id": "5000", "category": ga.OK, "secondary_tags": []},
        ]
        ga.detect_duplicates(archives)
        assert "DUPLICATE" in archives[0]["secondary_tags"]
        assert "DUPLICATE" in archives[1]["secondary_tags"]
        assert "DUPLICATE" not in archives[2]["secondary_tags"]

    def test_no_duplicates_when_all_unique(self):
        archives = [
            {"crawl_id": "1", "category": ga.OK, "secondary_tags": []},
            {"crawl_id": "2", "category": ga.OK, "secondary_tags": []},
        ]
        ga.detect_duplicates(archives)
        assert all("DUPLICATE" not in a["secondary_tags"] for a in archives)


class TestRemediate:
    def test_delete(self):
        with patch("gcs_archive_audit.gcloud_delete") as mock_del:
            note = ga.remediate("gs://b/crawls/4365.tmp.tar.gz", ga.WRONG_NAME, "delete", None, "b")
        mock_del.assert_called_once_with("gs://b/crawls/4365.tmp.tar.gz")
        assert "deleted" in note

    def test_quarantine(self):
        with patch("gcs_archive_audit.gcloud_move") as mock_mv:
            note = ga.remediate("gs://b/crawls/4365.tmp.tar.gz", ga.WRONG_NAME, "quarantine", "quarantine/", "b")
        mock_mv.assert_called_once_with(
            "gs://b/crawls/4365.tmp.tar.gz",
            "gs://b/quarantine/4365.tmp.tar.gz",
        )
        assert "quarantined" in note

    def test_ok_skips_action(self):
        with patch("gcs_archive_audit.gcloud_delete") as mock_del:
            note = ga.remediate("gs://b/crawls/x.tar.gz", ga.OK, "delete", None, "b")
        mock_del.assert_not_called()
        assert note == ""


class TestArgs:
    def test_delete_and_quarantine_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            ga.parse_args(["--bucket", "b", "--delete", "--quarantine", "q/"])

    def test_bucket_is_required(self):
        with pytest.raises(SystemExit):
            ga.parse_args([])

    def test_defaults(self):
        args = ga.parse_args(["--bucket", "b"])
        assert args.bucket == "b"
        assert args.prefix == "crawls/"
        assert args.delete is False
        assert args.quarantine is None
        assert args.name_only is False


class TestPathNormalization:
    """Regression tests for tar-member '.' prefix handling.
    Real archives produced by shutil.make_archive contain './'-prefixed members."""

    def test_fixture_actually_produces_dot_slash_prefix(self, tmp_path):
        """Sanity-check the _build_tar helper matches the real crawler layout."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(domain="example.com", stored=1),
        })
        with _tarfile.open(str(path), 'r:gz') as t:
            names = [m.name for m in t.getmembers()]
        assert any(n.startswith("./") for n in names), (
            f"Fixture should produce './' prefixed members, got: {names}"
        )

    def test_payload_found_despite_leading_dot_slash(self, tmp_path):
        """The audit must classify a well-formed archive as OK even though
        its members have the './' prefix from shutil.make_archive."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(domain="example.com", stored=1),
            "_completion_marker.json": _marker(),
            "storage/datasets/example.com/a.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["actual_count"] == 1

    def test_normalize_strips_dot_slash_prefix(self):
        assert ga._normalize_member_name("./_callback_payload.json") == "_callback_payload.json"

    def test_normalize_maps_bare_dot_to_empty(self):
        assert ga._normalize_member_name(".") == ""

    def test_normalize_leaves_unprefixed_names_unchanged(self):
        assert ga._normalize_member_name("foo/bar.json") == "foo/bar.json"
