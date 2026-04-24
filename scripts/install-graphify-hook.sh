#!/bin/sh
# Install the scoped graphify post-commit hook into .git/hooks/.
# Safe to re-run: overwrites the hook file. No .git config changes.

set -e

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$REPO_ROOT" ]; then
    echo "error: must be run inside the RAG-HP-PUB git repository" >&2
    exit 1
fi

SRC="$REPO_ROOT/scripts/graphify-post-commit.sh"
DST="$REPO_ROOT/.git/hooks/post-commit"

if [ ! -f "$SRC" ]; then
    echo "error: $SRC not found - are you on the right branch?" >&2
    exit 1
fi

cp "$SRC" "$DST"
chmod +x "$DST"

echo "[graphify hook] installed $DST"
echo "[graphify hook] source: $SRC"
echo ""
echo "This hook rebuilds AST-only on commits that touch files tracked in"
echo "graphify-out/manifest.json. It never expands graph scope and never"
echo "calls the LLM. See docs/graphify-guide-en.md for details."
echo ""
echo "To uninstall:  rm .git/hooks/post-commit"
