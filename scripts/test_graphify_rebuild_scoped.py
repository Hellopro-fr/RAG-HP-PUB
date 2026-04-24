"""Tests for scripts/graphify_rebuild_scoped.py.

Focus: the pure helpers that can be tested without running the full graphify
pipeline (which needs a real graph.json and manifest).

Heavy integration — actually rebuilding a graph — is verified manually the
first time the hook fires on a real commit, not in CI.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import graphify_rebuild_scoped as rebuild  # noqa: E402


def test_code_extensions_include_common_stacks():
    """Contract: the extension set must cover every language currently in the repo."""
    expected = {".py", ".ts", ".js", ".rs", ".go"}
    assert expected.issubset(rebuild.CODE_EXTENSIONS)


def test_collect_changed_uses_argv(monkeypatch):
    monkeypatch.setattr(rebuild, "sys", type("S", (), {"argv": ["prog", "a.py", "b.ts"]}))
    assert rebuild._collect_changed() == ["a.py", "b.ts"]


def test_collect_changed_falls_back_to_env(monkeypatch):
    monkeypatch.setattr(rebuild, "sys", type("S", (), {"argv": ["prog"]}))
    monkeypatch.setenv("GRAPHIFY_CHANGED", "x.py\n\n y.rs\n")
    assert rebuild._collect_changed() == ["x.py", "y.rs"]


def test_collect_changed_returns_empty_when_nothing(monkeypatch):
    monkeypatch.setattr(rebuild, "sys", type("S", (), {"argv": ["prog"]}))
    monkeypatch.delenv("GRAPHIFY_CHANGED", raising=False)
    assert rebuild._collect_changed() == []


def test_resolve_absolute_passthrough(tmp_path):
    absolute = tmp_path / "some_file.py"
    absolute.write_text("x = 1")
    resolved = rebuild._resolve(str(absolute))
    assert resolved == absolute.resolve()


def test_resolve_relative_uses_repo_root(monkeypatch, tmp_path):
    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    (fake_root / "libs" / "pkg").mkdir(parents=True)
    (fake_root / "libs" / "pkg" / "mod.py").write_text("x = 1")
    monkeypatch.setattr(rebuild, "REPO_ROOT", fake_root)
    result = rebuild._resolve("libs/pkg/mod.py")
    assert result == (fake_root / "libs" / "pkg" / "mod.py").resolve()


def test_load_manifest_paths_handles_flat_dict(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "/abs/path/a.py": 1234.5,
                "/abs/path/b.ts": 2345.6,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rebuild, "MANIFEST_JSON", manifest_path)
    paths = rebuild._load_manifest_paths()
    assert str(Path("/abs/path/a.py").resolve()) in paths
    assert str(Path("/abs/path/b.ts").resolve()) in paths


def test_load_manifest_paths_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "MANIFEST_JSON", tmp_path / "nope.json")
    assert rebuild._load_manifest_paths() == set()


def test_load_labels_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "LABELS_JSON", tmp_path / "labels.json")
    communities = {0: [], 1: [], 2: []}
    labels = rebuild._load_labels(communities)
    assert labels == {0: "Community 0", 1: "Community 1", 2: "Community 2"}


def test_load_labels_reads_json(tmp_path, monkeypatch):
    path = tmp_path / "labels.json"
    path.write_text(json.dumps({"0": "Redis Cache", "1": "DLQ Archiver"}))
    monkeypatch.setattr(rebuild, "LABELS_JSON", path)
    labels = rebuild._load_labels({0: [], 1: []})
    assert labels == {0: "Redis Cache", 1: "DLQ Archiver"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
