#!/bin/bash
# Stop hook: lightweight gate that only outputs review context when files were actually modified.
# If no files changed → silent exit (no extra inference cost).
# If files changed → outputs review instructions as context for Claude to read.
# Also runs scope-guard check inline.

CHANGED=$(git diff --name-only 2>/dev/null; git diff --name-only --cached 2>/dev/null)
CHANGED=$(echo "$CHANGED" | sort -u | grep -v '^$')

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

# Run scope-guard inline
SPEC_FILE=""
if [ -n "$CLAUDE_PROJECT_DIR" ]; then
    SPEC_FILE=$(find "$CLAUDE_PROJECT_DIR" -maxdepth 3 -name "*.spec.md" -newer "$CLAUDE_PROJECT_DIR/.git/HEAD" 2>/dev/null | head -1)
    if [ -z "$SPEC_FILE" ]; then
        SPEC_FILE=$(find "$CLAUDE_PROJECT_DIR/docs/superpowers" -maxdepth 2 -name "*.md" -newer "$CLAUDE_PROJECT_DIR/.git/HEAD" 2>/dev/null | head -1)
    fi
fi

if [ -n "$SPEC_FILE" ]; then
    DECLARED_FILES=$(grep -oP '(?:Create|Modify|Update):\s*`([^`]+)`' "$SPEC_FILE" 2>/dev/null | sed 's/.*`\(.*\)`.*/\1/')
    if [ -n "$DECLARED_FILES" ]; then
        OUT_OF_SCOPE=""
        while IFS= read -r modified; do
            [ -z "$modified" ] && continue
            case "$modified" in
                *.test.*|*test_*|*_test.*|*.spec.*|conftest.py|*.md|*.yml|*.yaml|*.json|*.toml|.claude/*|docs/*) continue ;;
            esac
            FOUND=0
            while IFS= read -r declared; do
                [ -z "$declared" ] && continue
                if [ "$modified" = "$declared" ] || echo "$modified" | grep -q "$declared"; then
                    FOUND=1
                    break
                fi
            done <<< "$DECLARED_FILES"
            if [ "$FOUND" -eq 0 ]; then
                OUT_OF_SCOPE="$OUT_OF_SCOPE\n  - $modified"
            fi
        done <<< "$CHANGED"
        if [ -n "$OUT_OF_SCOPE" ]; then
            echo ""
            echo -e "Scope Guard: Files modified outside declared spec scope:$OUT_OF_SCOPE"
        fi
    fi
fi

exit 0