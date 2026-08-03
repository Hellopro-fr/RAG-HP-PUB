#!/bin/bash
# PreToolUse hook: WARN when production code is edited with no corresponding test.
#
# Advisory by default — it injects a reminder into the model's context and lets
# the edit through. Rationale, measured 2026-08-03 on a 60-file sample of real
# production files: re-arming it as a hard block refused 33% of them. A gate that
# refuses one edit in three gets disabled within the week (that is exactly what
# happened in the sibling repo: two successive "Exclusion" commits).
#
# To make it blocking once coverage is higher: set TDD_GATE_STRICT=1.
#
# Adapted from claude-code-templates/tdd-gate for RAG-HP-PUB.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''))
except Exception:
    print('')
" 2>/dev/null)

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Extract extension
EXT="${FILE_PATH##*.}"

# Only check production code extensions
case "$EXT" in
    py|rs|ts|tsx|js|jsx|go|java|kt|rb|php) ;;
    *) exit 0 ;;
esac

BASENAME=$(basename "$FILE_PATH")
DIRNAME=$(dirname "$FILE_PATH")

# Skip test files themselves
case "$BASENAME" in
    test_*|*_test.*|*.test.*|*.spec.*|*Test.*|conftest.py) exit 0 ;;
esac

# Skip config, infrastructure, and documentation files
case "$BASENAME" in
    config.*|*.config.*|credentials.*|settings.*|Dockerfile|docker-compose*|*.yml|*.yaml|*.toml|*.json|*.md|*.txt|*.cfg|*.ini|main.py|__init__.py) exit 0 ;;
esac

# Skip known non-testable paths
#
# Cross-workspace exemption rationale:
# When this RAG-HP-PUB session has additional working directories added (e.g.
# `D:/DevHellopro/Marketplace`), Write/Edit calls into those sibling repos
# still trigger this hook — `CLAUDE_PROJECT_DIR` is bound to RAG-HP-PUB at
# session start. To avoid forcing RAG-HP-PUB's TDD policy onto unrelated
# projects with their own conventions (Marketplace is legacy PHP with no test
# infra by design), we skip paths anchored on common folder names used in
# this DevHellopro workspace layout.
#
# Patterns are case-sensitive substring globs, and must name the SIBLING repos —
# never a shared parent folder.
#
# TRAP, fixed 2026-08-03: this list used to carry `*Hellopro*`, meant to cover
# `Hellopro-fr/`. But this clone lives under `D:/DevHellopro/Workspaces/...`, so
# every absolute path matched it — and Write/Edit always pass absolute paths.
# The hook was therefore inert on its own repo since that pattern was added,
# while still looking active. Verified: same file, relative path -> exit 2,
# absolute path -> exit 0.
#
# If your clone uses different folder names, add a pattern for the sibling repo
# itself (`*/my-other-repo/*`), not for the directory that contains them all.
case "$FILE_PATH" in
    *migrations*|*schemas*|*.claude*|*protos/*|*docs/*|*hooks/*|*Marketplace*|*meps-app*) exit 0 ;;
esac

# Search for a corresponding test file
STEM="${BASENAME%.*}"

# Check common test locations
FOUND=0
for TEST_DIR in "$DIRNAME" "$DIRNAME/tests" "$DIRNAME/../tests" "$DIRNAME/../test" "$DIRNAME/../__tests__"; do
    if [ -d "$TEST_DIR" ]; then
        for PATTERN in "test_${STEM}.*" "${STEM}_test.*" "${STEM}.test.*" "${STEM}.spec.*" "${STEM}Test.*"; do
            if ls "$TEST_DIR"/$PATTERN 1>/dev/null 2>&1; then
                FOUND=1
                break 2
            fi
        done
    fi
done

# If not found locally, search the SERVICE the file belongs to — not the whole
# monorepo. A test named foo_test.go in service A must not excuse foo.go in
# service B.
if [ "$FOUND" -eq 0 ]; then
    SERVICE_ROOT=$(echo "$DIRNAME" | sed -E 's#^(.*/(apps-microservices|libs)/[^/]+)/.*#\1#')
    [ -d "$SERVICE_ROOT" ] || SERVICE_ROOT="$DIRNAME"
    RESULT=$(find "$SERVICE_ROOT" -maxdepth 6 \( -name "test_${STEM}.*" -o -name "${STEM}_test.*" -o -name "${STEM}.test.*" -o -name "${STEM}.spec.*" \) -not -path "*node_modules*" -not -path "*.venv*" -print -quit 2>/dev/null)
    if [ -n "$RESULT" ]; then
        FOUND=1
    fi
fi

if [ "$FOUND" -eq 0 ]; then
    MSG="TDD Gate: no test found for '$BASENAME'. Conventions: Go -> ${STEM}_test.go beside the file; Python -> tests/test_${STEM}.py; crawler-service -> src/${STEM}.test.ts (node:test); other TS/Vue -> ${STEM}.spec.ts (vitest). The test-writer agent can draft one."
    if [ -n "$TDD_GATE_STRICT" ]; then
        echo "⚠️ $MSG" >&2
        exit 2
    fi
    # Advisory: reach the model without refusing the edit.
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"%s"}}\n' "$MSG"
fi

exit 0
