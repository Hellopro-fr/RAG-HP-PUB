#!/usr/bin/env python3
"""PreToolUse hook: block dangerous shell commands.
Adapted from claude-code-templates/dangerous-command-blocker for RAG-HP-PUB.
"""
import json
import re
import sys

# Level 1: Catastrophic — always block
CATASTROPHIC = [
    r'rm\s+(-[a-zA-Z]*)?f?r?f?\s+/',           # rm on root
    r'rm\s+(-[a-zA-Z]*)?f?r?f?\s+~',            # rm on home
    r'rm\s+-rf\s+\*',                             # rm -rf *
    r'\bdd\b.*\bof=/dev/',                         # dd to device
    r'\bmkfs\b',                                   # format filesystem
    r'\bmkswap\b',                                 # create swap
    r'\bfdisk\b',                                  # partition editor
    r':\(\)\s*\{\s*:\|:\s*&\s*\}\s*;:',          # fork bomb
    r'>\s*/dev/sd[a-z]',                           # write to disk device
    r'chmod\s+777\s+/',                            # chmod 777 root
    r'git\s+reset\s+--hard\s+HEAD~',             # destructive git reset
]

# Level 2: Critical path protection — block
CRITICAL_PATHS = [
    r'(rm|mv)\s+.*\.claude/',                      # .claude/ directory
    r'(rm|mv)\s+.*\.git/',                         # .git directory
    r'(rm|mv)\s+.*\.env($|\s)',                    # .env files
    r'(rm|mv)\s+.*docker-compose\.yml',            # compose file
    r'(rm|mv)\s+.*Cargo\.toml',                    # Rust manifest
    r'(rm|mv)\s+.*requirements\.txt',              # Python deps
    r'(rm|mv)\s+.*package\.json',                  # Node.js manifest
    r'(rm|mv)\s+.*package-lock\.json',             # Node.js lockfile
    r'(rm|mv)\s+.*protos/',                        # Proto definitions
    r'(rm|mv)\s+.*libs/common-utils/',             # Shared Python lib
]

# Level 3: Suspicious — warn only
SUSPICIOUS = [
    r'rm\s+.*\*',                                  # rm with wildcards
    r'find\s+.*-delete',                           # find -delete
    r'xargs\s+rm',                                 # piped rm
    r'git\s+clean\s+-[a-zA-Z]*f',                 # git clean -f
    r'git\s+checkout\s+--\s+\.',                   # git checkout -- .
    r'DROP\s+(TABLE|DATABASE)',                     # SQL destructive
    r'TRUNCATE\s+TABLE',                           # SQL truncate
]


def main():
    hook_input = json.loads(sys.stdin.read())
    tool_input = hook_input.get('tool_input', {})
    command = tool_input.get('command', '')

    if not command:
        sys.exit(0)

    # Level 1: Catastrophic
    for pattern in CATASTROPHIC:
        if re.search(pattern, command, re.IGNORECASE):
            print(f"🔴 BLOCKED: Catastrophic command detected: {command}", file=sys.stderr)
            sys.exit(2)

    # Level 2: Critical paths
    for pattern in CRITICAL_PATHS:
        if re.search(pattern, command, re.IGNORECASE):
            print(f"🔴 BLOCKED: Command targets critical path: {command}", file=sys.stderr)
            sys.exit(2)

    # Level 3: Suspicious (warn only)
    for pattern in SUSPICIOUS:
        if re.search(pattern, command, re.IGNORECASE):
            print(f"⚠️ WARNING: Suspicious command pattern: {command}", file=sys.stderr)
            break

    sys.exit(0)


if __name__ == '__main__':
    main()
