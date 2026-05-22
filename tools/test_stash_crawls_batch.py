# tools/test_stash_crawls_batch.py
"""Unit tests for tools/stash_crawls_batch.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from stash_crawls_batch import (  # noqa: E402
    BatchState,
    FatalError,
    load_work_list,
    parse_line,
    parse_size,
)


def test_parse_size_units():
    assert parse_size("106M") == 106 * 1024**2
    assert parse_size("1.1G") == int(1.1 * 1024**3)
    assert parse_size("21G") == 21 * 1024**3
    assert parse_size("500K") == 500 * 1024
    assert parse_size("2T") == 2 * 1024**4


def test_parse_line_skips_markers():
    assert parse_line("106M\t6511 → Done\n") is None
    assert parse_line("21G\t5821 → Supprimé\n") is None
    assert parse_line("5.2G\t6434 → Done") is None


def test_parse_line_handles_blank_and_malformed():
    assert parse_line("") is None
    assert parse_line("\n") is None
    assert parse_line("no-tab-here 6271\n") is None
    assert parse_line("106M\tabc\n") is None  # non-digit id
    assert parse_line("139M\t6271\n") == (139 * 1024**2, "6271")


def test_load_work_list_rejects_duplicates(tmp_path):
    input_file = tmp_path / "ids.txt"
    input_file.write_text("139M\t6271\n142M\t6271\n", encoding="utf-8")
    with pytest.raises(FatalError, match="Duplicate"):
        load_work_list(input_file, done=set())


def test_load_work_list_filters_done_and_sorts(tmp_path):
    input_file = tmp_path / "ids.txt"
    input_file.write_text(
        "20G\t6080\n"
        "106M\t6511 → Done\n"
        "139M\t6271\n"
        "142M\t6299\n"
        "17G\t5621\n",
        encoding="utf-8",
    )
    work = load_work_list(input_file, done={"6299"})
    assert [crawl_id for _, crawl_id in work] == ["6271", "5621", "6080"]


def test_batch_state_append_done_and_classes(tmp_path):
    input_file = tmp_path / "ids.txt"
    input_file.write_text("139M\t6271\n", encoding="utf-8")
    state = BatchState(input_file)

    state.append("done", "6271")
    state.append("skipped", "6299", "409 already stashed")
    state.append("notfound", "9999")

    done_lines = (tmp_path / "ids.txt.stash_done.txt").read_text().splitlines()
    assert done_lines == ["6271"]
    assert "6271" in state.done

    skipped = (tmp_path / "ids.txt.stash_skipped.txt").read_text()
    assert skipped.startswith("6299\t409 already stashed\t")
    assert len(skipped.strip().split("\t")) == 3

    notfound = (tmp_path / "ids.txt.stash_notfound.txt").read_text()
    assert notfound.startswith("9999\t")


def test_batch_state_loads_existing_done(tmp_path):
    input_file = tmp_path / "ids.txt"
    input_file.write_text("139M\t6271\n", encoding="utf-8")
    (tmp_path / "ids.txt.stash_done.txt").write_text("100\n200\n300\n")

    state = BatchState(input_file)
    assert state.done == {"100", "200", "300"}
