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
                "/some/RAG-HP-PUB/libs/a.py": 1234.5,
                "/some/RAG-HP-PUB/libs/b.ts": 2345.6,
            }
        ),
        encoding="utf-8",
    )
    # Graph missing forces the fallback to manifest.
    monkeypatch.setattr(rebuild, "GRAPH_JSON", tmp_path / "no-graph.json")
    monkeypatch.setattr(rebuild, "MANIFEST_JSON", manifest_path)
    paths = rebuild._load_manifest_paths()
    assert "libs/a.py" in paths
    assert "libs/b.ts" in paths


def test_load_manifest_paths_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "GRAPH_JSON", tmp_path / "no-graph.json")
    monkeypatch.setattr(rebuild, "MANIFEST_JSON", tmp_path / "nope.json")
    assert rebuild._load_manifest_paths() == set()


def test_load_scope_paths_prefers_graph_over_manifest(tmp_path, monkeypatch):
    """graph.json is tracked; manifest.json is local-only. Graph wins."""
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "nodes": [
                    {"id": "n1", "source_file": "/some/RAG-HP-PUB/libs/a.py"},
                    {"id": "n2", "source_file": "/some/RAG-HP-PUB/libs/b.ts"},
                ],
                "links": [],
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"/some/RAG-HP-PUB/tools/should-not-win.py": 999.9}),
        encoding="utf-8",
    )
    monkeypatch.setattr(rebuild, "GRAPH_JSON", graph_path)
    monkeypatch.setattr(rebuild, "MANIFEST_JSON", manifest_path)

    paths = rebuild._load_scope_paths()
    assert "libs/a.py" in paths
    assert "libs/b.ts" in paths
    assert "tools/should-not-win.py" not in paths


def test_load_scope_paths_falls_back_to_manifest_when_graph_missing(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"/some/RAG-HP-PUB/tools/daemon.sh": 111.1}),
        encoding="utf-8",
    )
    monkeypatch.setattr(rebuild, "GRAPH_JSON", tmp_path / "no-graph.json")
    monkeypatch.setattr(rebuild, "MANIFEST_JSON", manifest_path)

    paths = rebuild._load_scope_paths()
    assert "tools/daemon.sh" in paths


def test_load_scope_paths_skips_nodes_without_source_file(tmp_path, monkeypatch):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "nodes": [
                    {"id": "has_src", "source_file": "/some/RAG-HP-PUB/libs/real.py"},
                    {"id": "no_src"},
                    {"id": "empty_src", "source_file": ""},
                    {"id": "none_src", "source_file": None},
                ],
                "links": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rebuild, "GRAPH_JSON", graph_path)
    monkeypatch.setattr(rebuild, "MANIFEST_JSON", tmp_path / "nope.json")

    paths = rebuild._load_scope_paths()
    assert paths == {"libs/real.py"}


def test_to_repo_relative_strips_rag_hp_pub_marker_cross_machine():
    """A graph captured at D:\\... must match a clone at C:\\... after normalization."""
    on_d = "D:\\DevHellopro\\Workspaces\\RAG-HP-PUB\\libs\\common-utils\\src\\foo.py"
    on_c = "C:/Users/randr/Documents/Workspaces/RAG-HP-PUB/libs/common-utils/src/foo.py"
    on_linux = "/home/dev/RAG-HP-PUB/libs/common-utils/src/foo.py"
    rel_input = "libs/common-utils/src/foo.py"
    expected = "libs/common-utils/src/foo.py"
    assert rebuild._to_repo_relative(on_d) == expected
    assert rebuild._to_repo_relative(on_c) == expected
    assert rebuild._to_repo_relative(on_linux) == expected
    assert rebuild._to_repo_relative(rel_input) == expected


def test_to_repo_relative_uses_last_marker_when_nested():
    """If `RAG-HP-PUB/` appears more than once, take the rightmost occurrence."""
    nested = "/some/RAG-HP-PUB/RAG-HP-PUB/libs/x.py"
    assert rebuild._to_repo_relative(nested) == "libs/x.py"


def test_load_scope_paths_handles_cross_machine_graph(tmp_path, monkeypatch):
    """graph.json captured on D:\\... is matched against clone at any other path."""
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "source_file": "D:\\DevHellopro\\Workspaces\\RAG-HP-PUB\\libs\\foo.py",
                    },
                    {
                        "id": "n2",
                        "source_file": "apps-microservices/crawler-service/main.py",
                    },
                ],
                "links": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rebuild, "GRAPH_JSON", graph_path)
    monkeypatch.setattr(rebuild, "MANIFEST_JSON", tmp_path / "no-manifest.json")

    paths = rebuild._load_scope_paths()
    assert "libs/foo.py" in paths
    assert "apps-microservices/crawler-service/main.py" in paths


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


def test_main_survives_html_viz_node_cap(tmp_path, monkeypatch):
    """The retired HTML export must never break the scoped rebuild.

    Upstream graphify.export.to_html raises ValueError past 5000 nodes; the
    real graph is beyond that for good (HTML viz retired). A rebuild that has
    already written graph.json/GRAPH_REPORT.md must exit 0, not crash — the
    crash also fails the CI auto-rebuild job before its commit step.
    """
    import graphify.export as gexport

    fake_root = tmp_path / "repo"
    (fake_root / "libs").mkdir(parents=True)
    (fake_root / "libs" / "mod.py").write_text("def f():\n    return 1\n")

    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    graph_json = graph_dir / "graph.json"
    graph_json.write_text(
        json.dumps(
            {
                "nodes": [{"id": "mod_f", "source_file": "libs/mod.py"}],
                "links": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(rebuild, "REPO_ROOT", fake_root)
    monkeypatch.setattr(rebuild, "GRAPH_DIR", graph_dir)
    monkeypatch.setattr(rebuild, "GRAPH_JSON", graph_json)
    monkeypatch.setattr(rebuild, "MANIFEST_JSON", graph_dir / "manifest.json")
    monkeypatch.setattr(rebuild, "LABELS_JSON", graph_dir / "labels.json")
    monkeypatch.setattr(rebuild, "REPORT_MD", graph_dir / "GRAPH_REPORT.md")
    monkeypatch.setattr(rebuild, "GRAPH_HTML", graph_dir / "graph.html", raising=False)
    monkeypatch.setattr(rebuild, "NEEDS_UPDATE_FLAG", graph_dir / ".needs_update")
    monkeypatch.setattr(rebuild, "sys", type("S", (), {"argv": ["prog", "libs/mod.py"]}))

    def _cap_blown(*args, **kwargs):
        raise ValueError("Graph has 7446 nodes - too large for HTML viz.")

    monkeypatch.setattr(gexport, "to_html", _cap_blown)

    assert rebuild.main() == 0
    assert (graph_dir / "GRAPH_REPORT.md").exists()
    rebuilt = json.loads(graph_json.read_text(encoding="utf-8"))
    assert rebuilt.get("nodes")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# --- preserve-and-place partition -------------------------------------------
# Regression guard for the label-rot defect measured 2026-08-07: the hook used
# cluster(graph) on every commit, renumbering communities while labels.json
# stayed keyed by id. One run moved 81% of nodes to a different id, silently
# invalidating every human label in the file.


def _line_graph(n=6):
    import networkx as nx

    g = nx.Graph()
    g.add_nodes_from(range(n))
    g.add_edges_from((i, i + 1) for i in range(n - 1))
    return g


def test_preserve_and_place_keeps_existing_community_ids():
    """The committed partition must survive verbatim - that is the whole point."""
    g = _line_graph(4)
    prior = [{"id": i, "community": 7 if i < 2 else 9} for i in range(4)]
    out = rebuild._preserve_and_place(g, prior)
    assert {c: sorted(v) for c, v in out.items()} == {7: [0, 1], 9: [2, 3]}


def test_preserve_and_place_places_new_node_with_its_neighbours():
    g = _line_graph(4)
    g.add_edge(3, 99)  # 99 is new: no community yet
    prior = [{"id": i, "community": 7 if i < 2 else 9} for i in range(4)]
    out = rebuild._preserve_and_place(g, prior)
    assert 99 in out[9], "a new node must join the community of its neighbours"


def test_preserve_and_place_refreshed_node_keeps_its_community():
    """A re-extracted AST node arrives with no community; it must not be re-placed
    into a different one just because the extraction dropped the attribute."""
    g = _line_graph(4)
    prior = [{"id": i, "community": 7 if i < 2 else 9} for i in range(4)]
    g.nodes[0].pop("community", None)
    out = rebuild._preserve_and_place(g, prior)
    assert 0 in out[7]


def test_preserve_and_place_isolated_new_node_gets_fresh_id():
    g = _line_graph(2)
    g.add_node("lonely")
    prior = [{"id": i, "community": 3} for i in range(2)]
    out = rebuild._preserve_and_place(g, prior)
    assert "lonely" in out[4], "an unreachable new node gets the next free id"


def test_preserve_and_place_falls_back_to_cluster_on_seed():
    """No prior partition at all (first ever build) -> real clustering."""
    g = _line_graph(4)
    out = rebuild._preserve_and_place(g, [])
    assert out and all(isinstance(v, list) for v in out.values())
    assert sum(len(v) for v in out.values()) == 4


def test_preserve_and_place_ignores_prior_nodes_absent_from_graph():
    g = _line_graph(2)
    prior = [{"id": 0, "community": 5}, {"id": 1, "community": 5},
             {"id": "deleted", "community": 5}]
    out = rebuild._preserve_and_place(g, prior)
    assert sorted(out[5]) == [0, 1]
