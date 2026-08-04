#!/usr/bin/env python3
"""PreToolUse hook: block dangerous shell commands.
Adapted from claude-code-templates/dangerous-command-blocker for RAG-HP-PUB.
"""
import json
import re
import sys

# Level 1: Catastrophic — always block
CATASTROPHIC = [
    # rm on root, on a top-level system directory, or on home. Any flag order or
    # spelling. The lookahead means "the target ends here": it must NOT swallow
    # `rm -rf /tmp/build` nor `rm -rf /d/DevHellopro/Worktrees/feature-x`
    # (worktrees are created and removed on every feature), but it MUST still
    # fire on `/etc`, `/usr`, `/home/*` and on `$(rm -rf /)`.
    # Anchoring on the bare slash alone is not enough — that was a real
    # regression: it let `rm -rf /etc` through.
    r'''\brm\s+(-[-a-zA-Z]+\s+)*/+(?=[\s;)|&*'"]|$)''',
    r'''\brm\s+(-[-a-zA-Z]+\s+)*/(bin|boot|dev|etc|home|lib|lib64|opt|proc'''
    r'''|root|sbin|srv|sys|usr|var)/?(?=[\s;)|&*'"]|$)''',
    r'''\brm\s+(-[-a-zA-Z]+\s+)*~/?(?=[\s;)|&*'"]|$)''',
    # a dot-directory directly under home: ~/.ssh, ~/.aws, ~/.config ...
    r'''\brm\s+(-[-a-zA-Z]+\s+)*~/\.[-\w.]+/?(?=[\s;)|&*'"]|$)''',
    r'rm\s+-rf\s+\*',                             # rm -rf *
    # PowerShell: wipe a drive. No `$` anchor -- trailing arguments (-Confirm:$false)
    # are the dominant form and used to disarm it.
    r'Remove-Item\s+(-\w+\s+)*[A-Za-z]:[\\/]?(?=\s|$)',
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
# Matched per FRAGMENT and anchored at its start, so that a command which merely
# MENTIONS the string (grep, echo, a doc edit) is not refused -- that is the very
# class of false positive this file exists to avoid.
FORCE_PUSH = [
    r'''^\s*git\s+(-C\s+\S+\s+)?push\b[^;|&]*\s(--force\b|--force-with-lease\b|-f\b)''',
    # refspec force: git push origin +main
    r'''^\s*git\s+(-C\s+\S+\s+)?push\b[^;|&]*\s\+\S''',
]

# Whitelist: recoverable removals, allowed despite matching CRITICAL_PATHS.
# `git rm` on a tracked file is undoable (git checkout / git revert); plain `rm`
# is not. Without this, routine config work on .claude/ or protos/ is blocked.
WHITELIST = [
    r'\bgit\s+rm\b',
]

# Level 2: Critical path protection — block
CRITICAL_PATHS = [
    r'\b(rm|mv|rmdir|del|Remove-Item|Move-Item)\s+[^;|&]*\.claude/',                      # .claude/ directory
    r'\b(rm|mv|rmdir|del|Remove-Item|Move-Item)\s+[^;|&]*\.git/',                         # .git directory
    r'\b(rm|mv|rmdir|del|Remove-Item|Move-Item)\s+[^;|&]*\.env($|\s)',                    # .env files
    r'\b(rm|mv|rmdir|del|Remove-Item|Move-Item)\s+[^;|&]*docker-compose\.yml',            # compose file
    r'\b(rm|mv|rmdir|del|Remove-Item|Move-Item)\s+[^;|&]*Cargo\.toml',                    # Rust manifest
    r'\b(rm|mv|rmdir|del|Remove-Item|Move-Item)\s+[^;|&]*requirements\.txt',              # Python deps
    r'\b(rm|mv|rmdir|del|Remove-Item|Move-Item)\s+[^;|&]*package\.json',                  # Node.js manifest
    r'\b(rm|mv|rmdir|del|Remove-Item|Move-Item)\s+[^;|&]*package-lock\.json',             # Node.js lockfile
    r'\b(rm|mv|rmdir|del|Remove-Item|Move-Item)\s+[^;|&]*protos/',                        # Proto definitions
    r'\b(rm|mv|rmdir|del|Remove-Item|Move-Item)\s+[^;|&]*libs/common-utils/',             # Shared Python lib
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


def fragments(command):
    """Split a compound line into the individual commands it runs.

    CRITICAL_PATHS is matched per fragment so that a whitelisted `git rm` in one
    command cannot excuse a plain `rm` in the next: `git rm README.md && rm -rf
    .claude/` must still be refused.
    """
    return re.split(r';|&&|\|\||\|', command)


def strip_commit_message(command):
    """Drop a commit message BODY, which is an argument and never executes.

    Commit messages routinely quote dangerous patterns ("rm -rf /", "mkfs")
    while running nothing, and scanning them produced false denials.

    Everything stripped here is anchored to the `-m` flag on purpose. An earlier
    version stripped any quoted-delimiter heredoc, which was WRONG: `bash <<'EOF'`
    EXECUTES its body -- the quoted delimiter suppresses interpolation, not
    execution -- so that version let an entire script through unscanned.
    """
    # -m followed by a PowerShell literal here-string
    command = re.sub(r"-m\s+@'.*?'@", ' ', command, flags=re.DOTALL)
    # -m "$(cat <<'EOF' ... EOF)" — the heredoc feeds git, not a shell
    command = re.sub(r"""-m\s+"?\$\(\s*cat\s*<<-?\s*'(\w+)'.*?^\1\s*\)"?""",
                     ' ', command, flags=re.DOTALL | re.MULTILINE)
    # -m 'single quoted'
    command = re.sub(r"-m\s+'[^']*'", ' ', command, flags=re.DOTALL)
    # -m "double quoted", only when it cannot interpolate
    command = re.sub(r'-m\s+"[^"$`]*"', ' ', command, flags=re.DOTALL)
    return command


def main():
    hook_input = json.loads(sys.stdin.read())
    tool_input = hook_input.get('tool_input', {})
    command = tool_input.get('command', '')

    if not command:
        sys.exit(0)

    command = strip_commit_message(command)

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

    # Level 1-bis: Force push (per fragment, anchored at its start)
    for pattern in FORCE_PUSH:
        for fragment in fragments(command):
            if re.search(pattern, fragment, re.IGNORECASE):
                deny("BLOCKED: Force push. Use a regular push, or ask the user "
                     f"for explicit permission: {fragment.strip()}")

    # Level 2: Critical paths (recoverable removals are whitelisted, per fragment)
    for pattern in CRITICAL_PATHS:
        for fragment in fragments(command):
            if re.search(pattern, fragment, re.IGNORECASE):
                if any(re.search(wp, fragment, re.IGNORECASE) for wp in WHITELIST):
                    continue
                deny(f"BLOCKED: Command targets critical path: {fragment.strip()}")

    # Level 3: Suspicious (warn only)
    for pattern in SUSPICIOUS:
        if re.search(pattern, command, re.IGNORECASE):
            print(f"WARNING: Suspicious command pattern: {command}", file=sys.stderr)
            break

    sys.exit(0)


if __name__ == '__main__':
    main()
