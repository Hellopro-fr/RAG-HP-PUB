#!/bin/sh
# graphify post-commit hook (scoped variant for RAG-HP-PUB)
# Installed to .git/hooks/post-commit by scripts/install-graphify-hook.sh
#
# Unlike `graphify hook install` from the upstream CLI, this hook
# delegates rebuild logic to scripts/graphify_rebuild_scoped.py, which
# enforces manifest-based scope. See docs/graphify-guide-en.md section
# "Why no git hooks?" for why the default hook is unsafe here.

# Skip during rebase/merge/cherry-pick so --continue is not blocked.
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null)
[ -d "$GIT_DIR/rebase-merge" ] && exit 0
[ -d "$GIT_DIR/rebase-apply" ] && exit 0
[ -f "$GIT_DIR/MERGE_HEAD" ] && exit 0
[ -f "$GIT_DIR/CHERRY_PICK_HEAD" ] && exit 0

# No graph, no work.
[ -f graphify-out/graph.json ]    || exit 0
[ -f graphify-out/manifest.json ] || exit 0

CHANGED=$(git diff --name-only HEAD~1 HEAD 2>/dev/null || git diff --name-only HEAD 2>/dev/null)
[ -z "$CHANGED" ] && exit 0

# Pick a Python interpreter that has graphify available.
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
    # graphify not installed for this user - silent noop, do not block commit.
    exit 0
fi

export GRAPHIFY_CHANGED="$CHANGED"
"$PYTHON" scripts/graphify_rebuild_scoped.py || true
