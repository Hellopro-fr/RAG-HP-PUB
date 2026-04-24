"""Scoped AST-only rebuild of the RAG-HP-PUB graphify graph.

This script replaces graphify's default `_rebuild_code` path. The stock function
rescans the entire current-working-directory, which in this 2129-file monorepo
pulls the `apps-microservices/` tree into the backbone graph and explodes
`graph.json`. See docs/graphify-guide-en.md section "Why no git hooks?" for the
full reasoning.

Behaviour:
    1. Derive graph scope from `graphify-out/graph.json` — every node's
       `source_file` attribute is collected into a set of in-scope paths.
       `graph.json` is tracked in git, so every teammate has the same scope
       after `git pull`. `manifest.json` is intentionally gitignored (its
       mtime values are local-only, see the upstream team-workflow doc) so it
       cannot be relied on post-clone.
    2. Intersect the list of changed files (argv[1:] or $GRAPHIFY_CHANGED env
       var) with that scope. Files outside it are ignored, so AST extraction
       never expands graph scope.
    3. For code files in the intersection: run `graphify.extract.extract` on
       that subset only.
    4. Merge into the existing graph without dropping anything:
         - freshly extracted AST nodes are added; when an ID already exists
           (same filestem+entity), its attributes are refreshed in place;
         - freshly extracted AST edges are appended (NetworkX dedups them
           when the graph is rebuilt);
         - semantic nodes (docs/papers/images) and their incoming cross-links
           are preserved untouched.
       Not dropping nodes leaves an orphan behind when a function is removed
       from source; that staleness is rare and preferred over silently losing
       cross-links from doc nodes that pointed at the old file-level ID.
    5. Preserve community labels from `graphify-out/labels.json` (tracked) so
       human-assigned community names survive rebuilds.
    6. Regenerate `graph.json`, `graph.html`, `GRAPH_REPORT.md`.
    7. For non-code files in the intersection, touch
       `graphify-out/.needs_update` so the operator knows semantic
       re-extraction (LLM) is required. The hook itself never spends LLM
       tokens.

Invocation:
    python scripts/graphify_rebuild_scoped.py <changed_file>...
    # or
    GRAPHIFY_CHANGED="$(git diff --name-only HEAD~1 HEAD)" \
        python scripts/graphify_rebuild_scoped.py

Designed to be called from a git post-commit hook; see
`scripts/graphify-post-commit.sh` and `scripts/install-graphify-hook.sh`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".kts", ".scala",
    ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp",
    ".rb", ".swift", ".cs", ".php", ".lua", ".toc",
}

REPO_ROOT = Path.cwd().resolve()
GRAPH_DIR = REPO_ROOT / "graphify-out"
GRAPH_JSON = GRAPH_DIR / "graph.json"
MANIFEST_JSON = GRAPH_DIR / "manifest.json"
LABELS_JSON = GRAPH_DIR / "labels.json"
REPORT_MD = GRAPH_DIR / "GRAPH_REPORT.md"
GRAPH_HTML = GRAPH_DIR / "graph.html"
NEEDS_UPDATE_FLAG = GRAPH_DIR / ".needs_update"


def _resolve(path_str: str) -> Path:
    """Resolve a possibly-relative path against the repo root."""
    p = Path(path_str)
    if not p.is_absolute():
        p = REPO_ROOT / p
    try:
        return p.resolve()
    except OSError:
        return p


def _collect_changed() -> list[str]:
    """Gather changed files from argv then fall back to GRAPHIFY_CHANGED env."""
    if len(sys.argv) > 1:
        return [a for a in sys.argv[1:] if a.strip()]
    env = os.environ.get("GRAPHIFY_CHANGED", "")
    return [line.strip() for line in env.splitlines() if line.strip()]


def _load_scope_paths() -> set[str]:
    """Return the set of absolute path strings currently in the graph.

    Prefers `graph.json` (tracked, available to every teammate). Falls back
    to `manifest.json` if graph is unreadable — the fallback path mostly
    matters during first-time graph seeding when graph.json does not yet
    exist.
    """
    if GRAPH_JSON.exists():
        try:
            graph = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            graph = None
        if graph:
            result: set[str] = set()
            for node in graph.get("nodes", []):
                source_file = node.get("source_file")
                if not source_file:
                    continue
                source_path = Path(source_file)
                if not source_path.is_absolute():
                    source_path = REPO_ROOT / source_path
                try:
                    result.add(str(source_path.resolve()))
                except OSError:
                    continue
            if result:
                return result

    if MANIFEST_JSON.exists():
        manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
        result_mf: set[str] = set()
        if isinstance(manifest, dict):
            for key, value in manifest.items():
                if isinstance(value, list):
                    for item in value:
                        result_mf.add(str(Path(item).resolve()))
                else:
                    result_mf.add(str(Path(key).resolve()))
        return result_mf
    return set()


# Backwards-compatible alias for existing tests.
_load_manifest_paths = _load_scope_paths


def _load_graph() -> dict:
    if not GRAPH_JSON.exists():
        raise SystemExit("graph.json missing - run /graphify . first to seed the graph")
    return json.loads(GRAPH_JSON.read_text(encoding="utf-8"))


def _load_labels(communities: dict) -> dict:
    if LABELS_JSON.exists():
        raw = json.loads(LABELS_JSON.read_text(encoding="utf-8"))
        return {int(k): v for k, v in raw.items()}
    return {cid: f"Community {cid}" for cid in communities}


def main() -> int:
    changed = _collect_changed()
    if not changed:
        print("[graphify hook] no changed files provided", flush=True)
        return 0

    scope_paths = _load_scope_paths()
    if not scope_paths:
        print("[graphify hook] no graph or manifest - skipping rebuild", flush=True)
        return 0

    in_scope_changed: list[Path] = []
    for raw_path in changed:
        resolved = _resolve(raw_path)
        if str(resolved) in scope_paths:
            in_scope_changed.append(resolved)

    if not in_scope_changed:
        return 0

    code_changed = [p for p in in_scope_changed if p.suffix.lower() in CODE_EXTENSIONS]
    doc_changed = [p for p in in_scope_changed if p not in code_changed]

    if doc_changed:
        NEEDS_UPDATE_FLAG.touch()
        print(
            f"[graphify hook] {len(doc_changed)} doc/config file(s) in scope changed - "
            "run `/graphify --update` in a Claude Code session for semantic refresh",
            flush=True,
        )

    if not code_changed:
        return 0

    print(
        f"[graphify hook] AST-rebuilding {len(code_changed)} code file(s) in graph scope",
        flush=True,
    )

    from graphify.extract import extract
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.report import generate
    from graphify.export import to_json, to_html

    new_ast = extract(code_changed)

    existing = _load_graph()

    def _edge_list(graph_dict):
        return graph_dict.get("links", graph_dict.get("edges", []))

    # Merge without dropping: refresh in-place by ID, append new. NetworkX
    # dedupes edges at graph build time. Cross-links from semantic nodes to
    # any file-level ID we already produced are preserved because those
    # targets still exist.
    new_by_id = {n["id"]: n for n in new_ast.get("nodes", [])}
    merged_nodes = []
    seen_ids: set[str] = set()
    for node in existing.get("nodes", []):
        nid = node["id"]
        if nid in new_by_id:
            merged_nodes.append(new_by_id[nid])
        else:
            merged_nodes.append(node)
        seen_ids.add(nid)
    for nid, node in new_by_id.items():
        if nid not in seen_ids:
            merged_nodes.append(node)
            seen_ids.add(nid)

    merged = {
        "nodes": merged_nodes,
        "edges": list(_edge_list(existing)) + new_ast.get("edges", []),
        "hyperedges": existing.get("hyperedges", []),
        "input_tokens": 0,
        "output_tokens": 0,
    }

    graph = build_from_json(merged)
    communities = cluster(graph)
    cohesion = score_all(graph, communities)
    gods = god_nodes(graph)
    surprises = surprising_connections(graph, communities)
    labels = _load_labels(communities)
    questions = suggest_questions(graph, communities, labels)

    detection = {
        "total_files": len(scope_paths),
        "total_words": 0,
        "needs_graph": True,
        "warning": None,
        "files": {"code": [], "document": [], "paper": [], "image": [], "video": []},
    }
    tokens = {"input": 0, "output": 0}

    report = generate(
        graph,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection,
        tokens,
        "scoped rebuild (scope derived from graphify-out/graph.json)",
        suggested_questions=questions,
    )
    REPORT_MD.write_text(report, encoding="utf-8")
    to_json(graph, communities, str(GRAPH_JSON))
    to_html(graph, communities, str(GRAPH_HTML), community_labels=labels)

    print(
        f"[graphify hook] rebuilt: {graph.number_of_nodes()} nodes, "
        f"{graph.number_of_edges()} edges, {len(communities)} communities",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
