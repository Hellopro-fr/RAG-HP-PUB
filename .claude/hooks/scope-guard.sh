#!/bin/bash
# Stop hook: warn if files were modified outside the declared scope.
# Adapted from claude-code-templates/scope-guard for RAG-HP-PUB.
# Non-blocking: always exits 0, prints warnings to stderr.

SPEC_FILE=""
if [ -n "$CLAUDE_PROJECT_DIR" ]; then
    SPEC_FILE=$(git -C "$CLAUDE_PROJECT_DIR" diff --name-only HEAD~5 HEAD 2>/dev/null | grep -E '\.spec\.md$' | head -1)
    if [ -n "$SPEC_FILE" ]; then
        SPEC_FILE="$CLAUDE_PROJECT_DIR/$SPEC_FILE"
    fi
fi

if [ -z "$SPEC_FILE" ]; then
    SPEC_FILE=$(git -C "$CLAUDE_PROJECT_DIR" diff --name-only HEAD~5 HEAD 2>/dev/null | grep -E '^docs/superpowers/.*\.md$' | head -1)
    if [ -n "$SPEC_FILE" ]; then
        SPEC_FILE="$CLAUDE_PROJECT_DIR/$SPEC_FILE"
    fi
fi

if [ -z "$SPEC_FILE" ]; then
    exit 0
fi

# Extract declared files from spec (lines starting with - Create: or - Modify: or file paths)
DECLARED_FILES=$(grep -oP '(?:Create|Modify|Update):\s*`([^`]+)`' "$SPEC_FILE" 2>/dev/null | sed 's/.*`\(.*\)`.*/\1/')

if [ -z "$DECLARED_FILES" ]; then
    exit 0
fi

# Get all modified files (staged + unstaged)
MODIFIED_FILES=$(git diff --name-only HEAD 2>/dev/null; git diff --name-only --cached 2>/dev/null)
MODIFIED_FILES=$(echo "$MODIFIED_FILES" | sort -u)

if [ -z "$MODIFIED_FILES" ]; then
    exit 0
fi

# Check for out-of-scope files
OUT_OF_SCOPE=""
while IFS= read -r modified; do
    [ -z "$modified" ] && continue

    # Skip common non-scope files
    case "$modified" in
        *.test.*|*test_*|*_test.*|*.spec.*|conftest.py) continue ;;
        *.md|*.yml|*.yaml|*.json|*.toml|*.cfg|*.txt) continue ;;
        .claude/*|docs/*|.github/*) continue ;;
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
done <<< "$MODIFIED_FILES"

if [ -n "$OUT_OF_SCOPE" ]; then
    echo -e "⚠️ Scope Guard: Files modified outside declared spec scope:$OUT_OF_SCOPE\nSpec file: $SPEC_FILE" >&2
fi

exit 0
