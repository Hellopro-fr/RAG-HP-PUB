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


def _payload(success: int = 3, id_domaine: str = "4365") -> bytes:
    """Build a _callback_payload.json matching what Node.js actually writes.

    Key details:
    - Contains 'id_domaine' (the crawl_id), NOT 'domain' (hostname).
    - Contains 'success' (URL count), NOT 'stored_files_count'.
    - 'stored_files_count' is added by Python in-memory at webhook-send time
      and is NEVER persisted to disk.
    """
    return _json.dumps({
        "id_domaine": id_domaine,
        "success": success,
        "failed": 0,
        "isFinished": 1,
        "method": "auto",
        "isError": "",
        "storagePath": f"/app/storage/{id_domaine}",
        "message_erreur_crawling": None,
    }).encode()


def _marker() -> bytes:
    return _json.dumps({"final_status": "finished", "exit_code": 0}).encode()


def _snapshot(domain: str = "example.com") -> bytes:
    """Build a _status_snapshot.json that Python's archive_crawl writes.
    The CrawlStatus model (app/schemas/crawler.py) has `domain` as a required field."""
    return _json.dumps({
        "crawl_id": "4365",
        "status": "finished",
        "domain": domain,
        "start_url": f"https://{domain}/",
        "urls_crawled": 0,
    }).encode()


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
            "_callback_payload.json": _payload(success=3),
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
            "_callback_payload.json": _payload(success=3),
            # no _completion_marker.json
            "storage/datasets/example.com/x.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.MISSING_MARKER
        assert "_completion_marker.json" in details.get("missing", "")

    def test_row_count_mismatch(self, tmp_path):
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=5),  # claims 5
            "_completion_marker.json": _marker(),
            # but only 2 dataset files
            "storage/datasets/example.com/a.json": b'{}',
            "storage/datasets/example.com/b.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.ROW_COUNT_MISMATCH
        assert details["expected_count"] == 5
        assert details["actual_count"] == 2

    def test_uses_status_snapshot_domain_when_payload_lacks_it(self, tmp_path):
        """When payload has no 'domain' but _status_snapshot.json does, the snapshot
        provides the domain for row counting. This exercises the second resolver
        priority (after payload, before tar inference)."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=1),
            "_completion_marker.json": _marker(),
            "_status_snapshot.json": _snapshot(domain="foo.com"),
            # Tar has sanitized dir name; snapshot resolves the real domain 'foo.com',
            # which _count_dataset_files matches via its sanitized fallback.
            "storage/datasets/foo-com/only.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["domain"] == "foo.com"
        assert details["actual_count"] == 1

    def test_uses_success_field_from_realistic_payload(self, tmp_path):
        """The Node.js payload has 'success' (not 'stored_files_count'). The audit
        must pick up the count from 'success' and classify as OK when the count matches."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=2),
            "_completion_marker.json": _marker(),
            "storage/datasets/example.com/a.json": b'{}',
            "storage/datasets/example.com/b.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["expected_count"] == 2

    def test_ok_when_payload_lacks_domain_field(self, tmp_path):
        """The Node.js payload doesn't have a 'domain' field — that's normal, not a failure.
        When the tar contains dataset files, the resolver infers the domain from tar structure
        and the audit classifies as OK."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=1),  # no 'domain' field — realistic
            "_completion_marker.json": _marker(),
            "storage/datasets/example.com/a.json": b'{}',
        })
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert details["domain"] == "example.com"
        assert details["actual_count"] == 1


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
            "_callback_payload.json": _payload(success=1),
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
            "_callback_payload.json": _payload(success=1),
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


class TestRestoreFromQuarantine:
    def test_moves_every_quarantined_object_to_target_prefix(self):
        quarantined = [
            "gs://b/crawls-quarantine/4365.tar.gz",
            "gs://b/crawls-quarantine/4683.tar.gz",
        ]
        with patch("gcs_archive_audit.gcloud_ls", return_value=quarantined) as mock_ls, \
             patch("gcs_archive_audit.gcloud_move") as mock_mv:
            count = ga.restore_from_quarantine("b", "crawls-quarantine/", "crawls/")

        assert count == 2
        mock_ls.assert_called_once_with("gs://b/crawls-quarantine/")
        # Each object moved to gs://b/crawls/{basename}
        assert mock_mv.call_args_list == [
            (("gs://b/crawls-quarantine/4365.tar.gz", "gs://b/crawls/4365.tar.gz"),),
            (("gs://b/crawls-quarantine/4683.tar.gz", "gs://b/crawls/4683.tar.gz"),),
        ]

    def test_returns_zero_when_quarantine_is_empty(self, capsys):
        with patch("gcs_archive_audit.gcloud_ls", return_value=[]):
            count = ga.restore_from_quarantine("b", "crawls-quarantine/", "crawls/")

        assert count == 0
        out = capsys.readouterr().out
        assert "No objects under" in out

    def test_continues_after_individual_move_failure(self, capsys):
        quarantined = [
            "gs://b/crawls-quarantine/ok.tar.gz",
            "gs://b/crawls-quarantine/fail.tar.gz",
            "gs://b/crawls-quarantine/another.tar.gz",
        ]
        err = subprocess.CalledProcessError(1, "gcloud", stderr="permission denied")

        def _move(src, dst):
            if "fail" in src:
                raise err

        with patch("gcs_archive_audit.gcloud_ls", return_value=quarantined), \
             patch("gcs_archive_audit.gcloud_move", side_effect=_move):
            count = ga.restore_from_quarantine("b", "crawls-quarantine/", "crawls/")

        # 2 succeed, 1 fails
        assert count == 2
        err_out = capsys.readouterr().err
        assert "Failed to restore fail.tar.gz" in err_out


class TestDomainResolution:
    """Tests for the multi-source _resolve_domain_name helper.
    Priority: payload.domain > _status_snapshot.json.domain > tar inference."""

    def _open_tar(self, path: Path):
        return _tarfile.open(str(path), 'r:gz')

    def test_uses_payload_domain_if_present(self, tmp_path):
        """Priority 1: if payload has 'domain', use it even if the tar layout
        suggests a different domain."""
        payload_bytes = _json.dumps({"id_domaine": "4365", "domain": "x.com", "success": 1}).encode()
        path = _build_tar(tmp_path, {
            "_callback_payload.json": payload_bytes,
            "_completion_marker.json": _marker(),
            # Tar has y.com but payload says x.com — payload wins
            "storage/datasets/y.com/a.json": b'{}',
        })
        with self._open_tar(path) as tar:
            members = tar.getmembers()
            payload = ga._read_json_member(tar, "_callback_payload.json")
            result = ga._resolve_domain_name(tar, members, payload)
        assert result == "x.com"

    def test_falls_back_to_status_snapshot_domain(self, tmp_path):
        """Priority 2: when payload lacks 'domain', read it from _status_snapshot.json."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=1),
            "_completion_marker.json": _marker(),
            "_status_snapshot.json": _snapshot(domain="x.com"),
            # No dataset dir to infer from — resolver must use the snapshot
        })
        with self._open_tar(path) as tar:
            members = tar.getmembers()
            payload = ga._read_json_member(tar, "_callback_payload.json")
            result = ga._resolve_domain_name(tar, members, payload)
        assert result == "x.com"

    def test_infers_from_tar_when_no_metadata_source(self, tmp_path):
        """Priority 3: neither payload nor snapshot has domain — infer from tar."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=1),
            "_completion_marker.json": _marker(),
            # No snapshot; tar has a dataset dir
            "storage/datasets/example.com/a.json": b'{}',
        })
        with self._open_tar(path) as tar:
            members = tar.getmembers()
            payload = ga._read_json_member(tar, "_callback_payload.json")
            result = ga._resolve_domain_name(tar, members, payload)
        assert result == "example.com"

    def test_skips_special_prefix_dirs_during_inference(self, tmp_path):
        """When tar has nfr-/error-/update- dirs AND a main domain dir,
        the resolver must skip the special-prefix ones and pick the main domain."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=1),
            "_completion_marker.json": _marker(),
            "storage/datasets/error-foo.com/e.json": b'{}',
            "storage/datasets/nfr-bar.com/n.json": b'{}',
            "storage/datasets/update-baz.com/u.json": b'{}',
            "storage/datasets/example.com/a.json": b'{}',
        })
        with self._open_tar(path) as tar:
            members = tar.getmembers()
            payload = ga._read_json_member(tar, "_callback_payload.json")
            result = ga._resolve_domain_name(tar, members, payload)
        assert result == "example.com"

    def test_returns_none_when_no_source_available(self, tmp_path):
        """Edge case: no payload.domain, no snapshot, only special-prefix dataset dirs.
        Resolver returns None; inspect_archive classifies as OK with a warning."""
        path = _build_tar(tmp_path, {
            "_callback_payload.json": _payload(success=0),
            "_completion_marker.json": _marker(),
            # Only special-prefix dataset dirs — resolver can't infer a main domain
            "storage/datasets/error-foo.com/e.json": b'{}',
            "storage/datasets/nfr-bar.com/n.json": b'{}',
        })
        with self._open_tar(path) as tar:
            members = tar.getmembers()
            payload = ga._read_json_member(tar, "_callback_payload.json")
            result = ga._resolve_domain_name(tar, members, payload)
        assert result is None

        # And inspect_archive must classify this as OK with a warning (not MISSING_PAYLOAD)
        category, details = ga.inspect_archive(path)
        assert category == ga.OK
        assert "warning" in details
        assert "domain could not be resolved" in details["warning"]
