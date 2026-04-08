#!/bin/bash
# PreToolUse hook: block production code edits if no corresponding test file exists.
# Adapted from claude-code-templates/tdd-gate for RAG-HP-PUB.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

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
    config.*|credentials.*|settings.*|Dockerfile|docker-compose*|*.yml|*.yaml|*.toml|*.json|*.md|*.txt|*.cfg|*.ini|main.py|__init__.py) exit 0 ;;
esac

# Skip known non-testable paths
case "$FILE_PATH" in
    *migrations*|*schemas*|*.claude*|*protos/*|*docs/*|*hooks/*) exit 0 ;;
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

# If not found locally, search project-wide (limited depth)
if [ "$FOUND" -eq 0 ]; then
    RESULT=$(find "$CLAUDE_PROJECT_DIR" -maxdepth 6 \( -name "test_${STEM}.*" -o -name "${STEM}_test.*" -o -name "${STEM}.test.*" -o -name "${STEM}.spec.*" \) -not -path "*node_modules*" -not -path "*.venv*" -print -quit 2>/dev/null)
    if [ -n "$RESULT" ]; then
        FOUND=1
    fi
fi

if [ "$FOUND" -eq 0 ]; then
    echo "⚠️ TDD Gate: No test file found for '$BASENAME'. Write a test first, or use @test-writer to generate one." >&2
    exit 2
fi

exit 0
