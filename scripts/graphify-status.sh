#!/bin/sh
# graphify status — one-line summary of whether the graph is fresh.
#
# Usage:
#   bash scripts/graphify-status.sh           # human-friendly line
#   bash scripts/graphify-status.sh --quiet   # exit code only (0 fresh, 1 pending, 2 missing graph)
#
# Designed to be cheap to run from a shell prompt, status line, or git
# pre-push hook. No graphify install required — only reads files.

QUIET=0
if [ "$1" = "--quiet" ] || [ "$1" = "-q" ]; then
    QUIET=1
fi

if [ ! -f graphify-out/graph.json ]; then
    [ "$QUIET" -eq 0 ] && echo "[graphify] no graph in this repo (graphify-out/graph.json missing)"
    exit 2
fi

if [ -f graphify-out/.needs_update ]; then
    [ "$QUIET" -eq 0 ] && echo "[graphify] PENDING — semantic re-extraction needed. Run /graphify --update from a Claude Code session."
    exit 1
fi

if [ "$QUIET" -eq 0 ]; then
    # Soft staleness signal: AST may need refresh if files in scope are newer
    # than graph.json mtime. Cheap heuristic, not a hard requirement.
    if [ -n "$(find libs protos tools model-optimizer docs apps-microservices/crawler-service apps-microservices/graph-rag-api-recherche-rust-service -newer graphify-out/graph.json -name '*.py' -o -newer graphify-out/graph.json -name '*.ts' 2>/dev/null | head -n 1)" ]; then
        echo "[graphify] AST drift — at least one in-scope code file is newer than graph.json. Local hook will rebuild on next commit, or run python scripts/graphify_rebuild_scoped.py <files>."
        exit 0
    fi
    echo "[graphify] fresh — graph.json is up to date relative to in-scope files."
fi
exit 0
