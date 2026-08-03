"""Self-check for .claude/hooks/dangerous-command-blocker.py regexes.

Run: python test_dangerous_command_blocker.py  -> PASS/FAIL per case, exit 1 on failure.

These are the 7 scripts that enforce this repo's policy, and until now none of
them had a test. The cases below pin the two failure modes that were measured on
this file: legitimate paths being refused (worktrees, /tmp, quoted patterns in a
commit message) and the real catastrophic form slipping through (`rm -r -f /`).
"""
import importlib.util
import os
import re
import sys

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "dangerous-command-blocker.py")
SPEC = importlib.util.spec_from_file_location("blocker", HOOK)
blocker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(blocker)


def decide(command):
    """Mirror main()'s decision order without touching stdin/stdout."""
    command = blocker.strip_literal_blocks(command)
    for pattern in blocker.CATASTROPHIC:
        if re.search(pattern, command, re.IGNORECASE):
            return "catastrophic"
    for pattern in blocker.FORCE_PUSH:
        if re.search(pattern, command, re.IGNORECASE):
            return "force_push"
    for pattern in blocker.CRITICAL_PATHS:
        if re.search(pattern, command, re.IGNORECASE):
            if any(re.search(wp, command, re.IGNORECASE) for wp in blocker.WHITELIST):
                return "allow"
            return "critical_path"
    return "allow"


CASES = [
    # --- the regression that motivated this test: legitimate paths ---
    # worktrees are created and removed on every feature (see the team primer)
    ("rm -rf /d/DevHellopro/Worktrees/rag-feature-x", "allow"),
    ("rm -rf /tmp/build", "allow"),
    ("rm -rf ./node_modules", "allow"),
    ("rm -rf apps-microservices/foo/dist", "allow"),
    # --- ...while the real catastrophic forms must still be caught ---
    ("rm -rf /", "catastrophic"),
    ("rm -fr /", "catastrophic"),
    ("rm -r -f /", "catastrophic"),
    ("rm --recursive --force /", "catastrophic"),
    ("rm -rf ~", "catastrophic"),
    ("mkfs.ext4 /dev/sda1", "catastrophic"),
    ("Remove-Item -Recurse -Force C:/", "catastrophic"),
    ("rd /s /q C:", "catastrophic"),
    # --- force push, anchored on "git push" ---
    ("git push --force", "force_push"),
    ("git push -f origin features/poc", "force_push"),
    ("git push origin main --force-with-lease", "force_push"),
    ("git push origin features/poc", "allow"),
    ("git push", "allow"),
    # a branch whose name contains -f must not trip the guard
    ("git push origin fix-flaky-test", "allow"),
    # --- commands with substitutions must not be denied (the `if` fail-open) ---
    ("echo $i", "allow"),
    ("for f in a b; do echo \"$f\"; done", "allow"),
    ("docker compose -f docker-compose.yml config", "allow"),
    # --- critical paths of THIS repo ---
    ("rm .claude/rules/security.md", "critical_path"),
    ("rm protos/catalog.proto", "critical_path"),
    ("rm libs/common-utils/src/foo.py", "critical_path"),
    # ...but a recoverable removal is whitelisted
    ("git rm .claude/rules/security.md", "allow"),
    ("git rm -r protos/legacy/", "allow"),
    # --- literal blocks are data, not commands ---
    ("git commit -m 'fix: the rm -rf / regex was too broad'", "allow"),
    ("git commit -m @'\nfix: mkfs pattern reworded\n'@", "allow"),
    ('git commit -m "docs: rm -rf / in prose"', "allow"),
    # ...but an interpolating body can still execute, so it stays scanned
    ('git commit -m "oops $(rm -rf /)"', "catastrophic"),
    ("git commit -m 'wip'; rm -rf /", "catastrophic"),
]

failures = 0
for command, expected in CASES:
    got = decide(command)
    if got == expected:
        print(f"PASS: {command!r} -> {got}")
    else:
        failures += 1
        print(f"FAIL: {command!r} -> got {got!r}, expected {expected!r}")

print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
sys.exit(1 if failures else 0)
