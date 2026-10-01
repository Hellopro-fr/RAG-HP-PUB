#!/bin/bash
# Install the scoped graphify post-commit + post-merge hooks into .git/hooks/.
# Safe to re-run: overwrites the hook files. No .git config changes.

set -e

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$REPO_ROOT" ]; then
    echo "error: must be run inside the RAG-HP-PUB git repository" >&2
    exit 1
fi

install_hook() {
    local hook_name=$1
    local src="$REPO_ROOT/scripts/graphify-${hook_name}.sh"
    local dst="$REPO_ROOT/.git/hooks/${hook_name}"

    if [ ! -f "$src" ]; then
        echo "error: $src not found - are you on the right branch?" >&2
        return 1
    fi

    cp "$src" "$dst"
    chmod +x "$dst"

    echo "[graphify hook] installed $dst"
    echo "[graphify hook] source: $src"
}

install_hook post-commit || exit 1
install_hook post-merge  || exit 1

echo ""
echo "Both hooks rebuild AST-only on in-scope changes (scope derived from"
echo "graphify-out/graph.json). They never expand graph scope and never"
echo "call the LLM. See docs/graphify-guide-en.md for details."
echo ""
echo "  post-commit: fires after every \`git commit\`."
echo "  post-merge:  fires after every \`git pull\` / \`git merge\` that"
echo "               advances HEAD, so pulled changes from teammates are"
echo "               reflected in graph.json without a manual rebuild."
echo ""
echo "To uninstall:  rm .git/hooks/post-commit .git/hooks/post-merge"
