#!/usr/bin/env python3
"""PreToolUse hook: validate conventional commit message format.
Adapted from claude-code-templates/conventional-commits for RAG-HP-PUB.
"""
import json
import re
import sys

PATTERN = r'^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)(\(.+\))?:\s.+'

VALID_TYPES = [
    'feat', 'fix', 'docs', 'style', 'refactor',
    'perf', 'test', 'chore', 'ci', 'build', 'revert',
]


def extract_commit_message(command):
    """Extract commit message from git commit command."""
    # Check heredoc FIRST (before simple quotes, which would match the heredoc wrapper)
    match = re.search(r'-m\s+"\$\(cat\s+<<[\'"]?EOF[\'"]?\n(.+?)\nEOF', command, re.DOTALL)
    if match:
        return match.group(1).strip().split('\n')[0]

    # Match -m "..." or -m '...'
    match = re.search(r'-m\s+["\'](.+?)["\']', command)
    if match:
        return match.group(1)

    return None


def main():
    hook_input = json.loads(sys.stdin.read())
    tool_input = hook_input.get('tool_input', {})
    command = tool_input.get('command', '')

    if 'git commit' not in command:
        sys.exit(0)

    # Skip --amend without -m (reuses previous message)
    if '--amend' in command and '-m' not in command:
        sys.exit(0)

    message = extract_commit_message(command)
    if not message:
        sys.exit(0)

    # Get first line only
    first_line = message.split('\n')[0].strip('\r\n \t')

    if re.match(PATTERN, first_line):
        sys.exit(0)

    reason = (
        f"Commit message does not follow Conventional Commits format.\n"
        f"Got: '{first_line}'\n"
        f"Expected: type(scope): description\n"
        f"Valid types: {', '.join(VALID_TYPES)}\n"
        f"Example: feat(api-gateway): add health check endpoint"
    )
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == '__main__':
    main()
