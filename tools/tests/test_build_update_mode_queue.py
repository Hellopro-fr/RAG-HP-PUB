"""Tests for tools/build_update_mode_queue.py."""
from __future__ import annotations

import pytest

import build_update_mode_queue as bq


class TestClassifyEntry:
    """Tests for the per-entry inclusion/exclusion logic."""

    def test_corrupted_goes_to_entries(self):
        entry = {
            "crawl_id": "1427",
            "object_name": "crawls/1427.tar.gz",
            "category": "CORRUPTED",
            "secondary_tags": [],
            "error": "EOFError: Compressed file ended before end-of-stream marker",
        }
        result = bq.classify_entry(
            entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30
        )
        assert result["bucket"] == "entries"
        assert result["reason"] == "CORRUPTED"
        assert "EOFError" in result["detail"]

    def test_major_under_delivery_goes_to_entries(self):
        entry = {
            "crawl_id": "1714",
            "object_name": "crawls/1714.tar.gz",
            "category": "ROW_COUNT_MISMATCH",
            "secondary_tags": [],
            "expected_count": 5789,
            "actual_count": 478,
        }
        result = bq.classify_entry(
            entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30
        )
        assert result["bucket"] == "entries"
        assert result["reason"] == "MAJOR_UNDER_DELIVERY"
        assert "5789" in result["detail"]
        assert "478" in result["detail"]

    def test_minor_under_delivery_goes_to_deferred(self):
        entry = {
            "crawl_id": "2754",
            "object_name": "crawls/2754.tar.gz",
            "category": "ROW_COUNT_MISMATCH",
            "secondary_tags": [],
            "expected_count": 267,
            "actual_count": 265,
        }
        result = bq.classify_entry(
            entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30
        )
        assert result["bucket"] == "deferred_to_phase2"
        assert result["reason"] == "MINOR_UNDER_DELIVERY"

    def test_excess_goes_to_deferred(self):
        entry = {
            "crawl_id": "3487",
            "object_name": "crawls/3487.tar.gz",
            "category": "ROW_COUNT_MISMATCH",
            "secondary_tags": [],
            "expected_count": 35,
            "actual_count": 1426,
        }
        result = bq.classify_entry(
            entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30
        )
        assert result["bucket"] == "deferred_to_phase2"
        assert result["reason"] == "EXCESS_LIKELY_CLASSIFIER_BUG"

    def test_expected_zero_goes_to_deferred(self):
        entry = {
            "crawl_id": "4398",
            "object_name": "crawls/4398.tar.gz",
            "category": "ROW_COUNT_MISMATCH",
            "secondary_tags": [],
            "expected_count": 0,
            "actual_count": 108,
        }
        result = bq.classify_entry(
            entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30
        )
        assert result["bucket"] == "deferred_to_phase2"
        assert result["reason"] == "EXPECTED_ZERO_LIKELY_CLASSIFIER_BUG"

    def test_tmp_sibling_row_mismatch_defers(self):
        """When a ROW_COUNT_MISMATCH main has a .tmp.tar.gz sibling, we defer
        because the tmp might carry unique data. Phase 2 inspects before deciding."""
        main = {
            "crawl_id": "4347",
            "object_name": "crawls/4347.tar.gz",
            "category": "ROW_COUNT_MISMATCH",
            "secondary_tags": ["DUPLICATE"],
            "expected_count": 1518,
            "actual_count": 424,
        }
        tmp = {
            "crawl_id": "4347",
            "object_name": "crawls/4347.tmp.tar.gz",
            "category": "WRONG_NAME",
            "secondary_tags": ["DUPLICATE"],
        }
        result = bq.classify_entry(
            main, all_entries=[main, tmp], exclude_ids=set(), deficit_threshold=0.30
        )
        assert result["bucket"] == "deferred_to_phase2"
        assert result["reason"] == "HOLD_TMP_SIBLING"

    def test_ok_entries_skipped(self):
        entry = {
            "crawl_id": "2409",
            "object_name": "crawls/2409.tar.gz",
            "category": "OK",
            "secondary_tags": [],
        }
        assert bq.classify_entry(
            entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30
        ) is None

    def test_wrong_name_skipped(self):
        """WRONG_NAME .tmp entries aren't queue material — they're dealt with
        elsewhere (Phase 1A replacement or Phase 2 inspection)."""
        entry = {
            "crawl_id": "5643",
            "object_name": "crawls/5643.tmp.tar.gz",
            "category": "WRONG_NAME",
            "secondary_tags": [],
        }
        assert bq.classify_entry(
            entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30
        ) is None

    def test_exclude_ids_filters_out(self):
        """A Phase 1A survivor that already has a fresh upload shouldn't be queued."""
        entry = {
            "crawl_id": "1806",
            "object_name": "crawls/1806.tar.gz",
            "category": "CORRUPTED",
            "secondary_tags": [],
            "error": "EOFError",
        }
        assert bq.classify_entry(
            entry, all_entries=[entry], exclude_ids={"1806"}, deficit_threshold=0.30
        ) is None

    def test_threshold_override(self):
        """Same entry lands in different buckets depending on the threshold."""
        entry = {
            "crawl_id": "4156",
            "object_name": "crawls/4156.tar.gz",
            "category": "ROW_COUNT_MISMATCH",
            "secondary_tags": [],
            "expected_count": 1627,
            "actual_count": 1280,  # 21.3% deficit
        }
        # Default 0.30 threshold -> deferred (21.3% < 30%)
        result_default = bq.classify_entry(
            entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.30
        )
        assert result_default["bucket"] == "deferred_to_phase2"
        # Lowered 0.10 threshold -> entries (21.3% > 10%)
        result_tight = bq.classify_entry(
            entry, all_entries=[entry], exclude_ids=set(), deficit_threshold=0.10
        )
        assert result_tight["bucket"] == "entries"
        assert result_tight["reason"] == "MAJOR_UNDER_DELIVERY"


class TestLoadExcludeIds:
    def test_empty_string_returns_empty_set(self):
        assert bq.load_exclude_ids("") == set()

    def test_none_returns_empty_set(self):
        assert bq.load_exclude_ids(None) == set()

    def test_comma_separated_parsed(self):
        assert bq.load_exclude_ids("1806,2517, 4683 ,") == {"1806", "2517", "4683"}
