#!/usr/bin/env python3
"""PreToolUse hook: block dangerous shell commands.
Adapted from claude-code-templates/dangerous-command-blocker for RAG-HP-PUB.
"""
import json
import re
import sys

# Level 1: Catastrophic — always block
CATASTROPHIC = [
    # rm on root / home, any flag order or spelling. The lookahead means "the
    # slash ends the path": it must NOT swallow `rm -rf /tmp/build` nor
    # `rm -rf /d/DevHellopro/Worktrees/feature-x` (both were blocked before, and
    # worktrees are created and removed on every feature), but it must still fire
    # when a shell metacharacter follows, e.g. $(rm -rf /).
    r'''\brm\s+(-[-a-zA-Z]+\s+)*/(?=[\s;)|&*'"]|$)''',
    r'''\brm\s+(-[-a-zA-Z]+\s+)*~/?(?=[\s;)|&*'"]|$)''',
    r'rm\s+-rf\s+\*',                             # rm -rf *
    r'Remove-Item\s+(-\w+\s+)*[A-Za-z]:[\\/]?\s*$',  # PowerShell: wipe a drive
    r'\brd\s+/s\b',                                # cmd: recursive dir delete
    r'\bdel\s+/[fsq]\b',                           # cmd: forced delete
    r'\bFormat-Volume\b',                          # PowerShell: format
    r'\bdd\b[^;|&]*\bof=/dev/',                        # dd to device
    r'\bmkfs\b',                                   # format filesystem
    r'\bmkswap\b',                                 # create swap
    r'\bfdisk\b',                                  # partition editor
    r':\(\)\s*\{\s*:\|:\s*&\s*\}\s*;:',          # fork bomb
    r'>\s*/dev/sd[a-z]',                           # write to disk device
    r'chmod\s+777\s+/',                            # chmod 777 root
    r'git\s+reset\s+--hard\s+HEAD~',             # destructive git reset
]

# Level 1-bis: Force push — block.
# Anchored on "git push" so the pattern cannot leak onto unrelated commands, and
# [^;|&]* keeps it inside a single command of a compound line. Replaces the two
# inline `if: Bash(git push *-f*)` hooks that used to live in settings.json: the
# `if` filter is documented as best-effort and fails OPEN on $(), backticks or
# $VAR, so those hooks denied unrelated commands while letting the real thing by.
FORCE_PUSH = [
    r'git\s+push\b[^;|&]*\s--force\b',
    r'git\s+push\b[^;|&]*\s--force-with-lease\b',
    r'git\s+push\b[^;|&]*\s-f\b',
]

# Whitelist: recoverable removals, allowed despite matching CRITICAL_PATHS.
# `git rm` on a tracked file is undoable (git checkout / git revert); plain `rm`
# is not. Without this, routine config work on .claude/ or protos/ is blocked.
WHITELIST = [
    r'\bgit\s+rm\b',
]

# Level 2: Critical path protection — block
CRITICAL_PATHS = [
    r'(rm|mv)\s+[^;|&]*\.claude/',                      # .claude/ directory
    r'(rm|mv)\s+[^;|&]*\.git/',                         # .git directory
    r'(rm|mv)\s+[^;|&]*\.env($|\s)',                    # .env files
    r'(rm|mv)\s+[^;|&]*docker-compose\.yml',            # compose file
    r'(rm|mv)\s+[^;|&]*Cargo\.toml',                    # Rust manifest
    r'(rm|mv)\s+[^;|&]*requirements\.txt',              # Python deps
    r'(rm|mv)\s+[^;|&]*package\.json',                  # Node.js manifest
    r'(rm|mv)\s+[^;|&]*package-lock\.json',             # Node.js lockfile
    r'(rm|mv)\s+[^;|&]*protos/',                        # Proto definitions
    r'(rm|mv)\s+[^;|&]*libs/common-utils/',             # Shared Python lib
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


def strip_literal_blocks(command):
    """Drop text that is data, not an executable command.

    Commit messages, docs and analysis one-liners routinely quote dangerous
    patterns ("rm -rf /", "mkfs") while executing nothing; scanning them produced
    false denials. Only NON-interpolating blocks are stripped -- a PowerShell
    @"..."@ here-string, an unquoted <<EOF heredoc or a "-m" body containing $ or
    a backtick can still execute, so those keep being scanned.
    """
    command = re.sub(r"@'.*?'@", ' ', command, flags=re.DOTALL)
    command = re.sub(r"<<-?\s*'(\w+)'.*?^\1", ' ', command,
                     flags=re.DOTALL | re.MULTILINE)
    command = re.sub(r"-m\s+'[^']*'", ' ', command, flags=re.DOTALL)
    command = re.sub(r'-m\s+"[^"$`]*"', ' ', command, flags=re.DOTALL)
    return command


def main():
    hook_input = json.loads(sys.stdin.read())
    tool_input = hook_input.get('tool_input', {})
    command = tool_input.get('command', '')

    if not command:
        sys.exit(0)

    command = strip_literal_blocks(command)

    def deny(reason):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason
        }}))
        sys.exit(2)

    # Level 1: Catastrophic
    for pattern in CATASTROPHIC:
        if re.search(pattern, command, re.IGNORECASE):
            deny(f"BLOCKED: Catastrophic command detected: {command}")

    # Level 1-bis: Force push
    for pattern in FORCE_PUSH:
        if re.search(pattern, command, re.IGNORECASE):
            deny("BLOCKED: Force push. Use a regular push, or ask the user for "
                 f"explicit permission: {command}")

    # Level 2: Critical paths (recoverable removals are whitelisted)
    for pattern in CRITICAL_PATHS:
        if re.search(pattern, command, re.IGNORECASE):
            if any(re.search(wp, command, re.IGNORECASE) for wp in WHITELIST):
                break
            deny(f"BLOCKED: Command targets critical path: {command}")

    # Level 3: Suspicious (warn only)
    for pattern in SUSPICIOUS:
        if re.search(pattern, command, re.IGNORECASE):
            print(f"WARNING: Suspicious command pattern: {command}", file=sys.stderr)
            break

    sys.exit(0)


if __name__ == '__main__':
    main()
