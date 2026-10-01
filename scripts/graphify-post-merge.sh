#!/bin/sh
# graphify post-merge hook (scoped, for RAG-HP-PUB)
# Installed to .git/hooks/post-merge by scripts/install-graphify-hook.sh
#
# Fires after `git pull`, `git merge`, and after `git checkout` of a
# different branch when the merge strategy applies. Rebuilds the graph
# AST for in-scope files the merge absorbed, so pulled changes are
# reflected in graph.json immediately. Same scope logic as the
# post-commit variant — delegates to scripts/graphify_rebuild_scoped.py.

GIT_DIR=$(git rev-parse --git-dir 2>/dev/null)
[ -d "$GIT_DIR/rebase-merge" ] && exit 0
[ -d "$GIT_DIR/rebase-apply" ] && exit 0

# A worktree is a transient branch checkout: rebuilding the graph there dirties
# TRACKED files (graph.json, GRAPH_REPORT.md) and produces a graph OF THE BRANCH,
# which can then be committed into it and conflict on a 47k-line JSON. The graph
# belongs to the main checkout. --git-dir and --git-common-dir differ only in a
# worktree. Added 2026-08-18 after measuring both meps-app trees dirty at once.
[ "$(git rev-parse --git-dir)" != "$(git rev-parse --git-common-dir)" ] && exit 0

# No graph yet, nothing to rebuild.
[ -f graphify-out/graph.json ] || exit 0

# $1 is 1 when the merge produced new content (squashed merge), 0 for a
# fast-forward. In both cases HEAD moved, so ORIG_HEAD..HEAD is the right
# diff.
CHANGED=$(git diff --name-only ORIG_HEAD HEAD 2>/dev/null)
[ -z "$CHANGED" ] && exit 0

PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c "import graphify" >/dev/null 2>&1; then
            PYTHON="$candidate"
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    exit 0
fi

export GRAPHIFY_CHANGED="$CHANGED"
"$PYTHON" scripts/graphify_rebuild_scoped.py || true
