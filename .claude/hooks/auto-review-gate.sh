#!/bin/bash
# Stop hook: lightweight gate that only outputs review context when files were actually modified.
# If no files changed → silent exit (no extra inference cost).
# If files changed → outputs review instructions as context for Claude to read.
# Also runs scope-guard check inline.

CHANGED=$( { git diff --name-only HEAD 2>/dev/null; git diff --name-only --cached 2>/dev/null; } | sort -u | grep -v '^$')

if [ -z "$CHANGED" ]; then
    # No files modified — skip entirely (fast, no inference)
    exit 0
fi

# Files were modified — output review context
echo "Files modified in this session:"
echo "$CHANGED"
echo ""
echo "Check if any of these apply:"
echo "1. CLAUDE.md refresh needed? If you created new files, added endpoints, changed service structure, or modified shared libs — check if the relevant CLAUDE.md needs updating. If yes, propose the update to the user."
echo "2. Auto-review needed? If you wrote or edited source code (not docs/comments/config only), do a quick self-review for SOLID/DRY/KISS violations, security concerns per .claude/rules/security.md, and impact on shared components per .claude/rules/impact-awareness.md."

# Delegate scope-guard check instead of duplicating logic
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/scope-guard.sh" ]; then
    bash "$SCRIPT_DIR/scope-guard.sh"
fi

exit 0