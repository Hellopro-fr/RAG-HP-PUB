"""Self-check for .claude/hooks/tdd-gate.sh.

The case that matters most is the ABSOLUTE path: Write/Edit always pass one, and
an exclusion pattern matching the shared parent directory made this hook inert on
its own repo while it still looked active. Any change to the skip list must keep
`test_absolute_path_is_not_exempt` passing.

Run: python test_tdd_gate.py   -> PASS/FAIL per case, exit 1 on any failure.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile


def find_bash():
    """Git Bash, not WSL — `bash` on PATH resolves to WSL on these machines."""
    for candidate in (r"C:\Program Files\Git\bin\bash.exe",
                      r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if os.path.exists(candidate):
            return candidate
    found = shutil.which("bash")
    if found and "system32" not in found.lower():
        return found
    print("SKIP: no Git Bash found; the hook cannot be exercised here.")
    sys.exit(0)


# tests/ -> hooks/ -> .claude/ -> repo root
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
HOOK = ".claude/hooks/tdd-gate.sh"
BASH = find_bash()

ALLOW, BLOCK = 0, 2


def run(file_path, strict=False):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": REPO}
    if strict:
        env["TDD_GATE_STRICT"] = "1"
    else:
        env.pop("TDD_GATE_STRICT", None)
    proc = subprocess.run(
        [BASH, HOOK], cwd=REPO,
        input=json.dumps({"tool_input": {"file_path": file_path}}),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
    )
    return proc.returncode, proc.stdout


tmp = tempfile.mkdtemp(prefix="tdd_gate_")
covered = os.path.join(tmp, "facetCap.ts")
open(covered, "w").close()
open(os.path.join(tmp, "facetCap.test.ts"), "w").close()
naked = os.path.join(tmp, "orphan.ts")
open(naked, "w").close()

# (path, strict?, expected_exit, expect_advisory_json)
CASES = [
    # THE regression: an absolute path must not be exempted by the skip list
    (naked, True, BLOCK, False),
    # advisory by default: same file, same absence of test, edit allowed
    (naked, False, ALLOW, True),
    # a co-located test satisfies the gate in both modes
    (covered, True, ALLOW, False),
    (covered, False, ALLOW, False),
    # sibling repos keep their own conventions
    (os.path.join(REPO.replace("Workspaces\\RAG-HP-PUB", "Marketplace"),
                  "BO", "fonctions", "fonctions_hellopro.php"), True, ALLOW, False),
    # non-production files are never gated
    (os.path.join(REPO, "CLAUDE.md"), True, ALLOW, False),
    (os.path.join(REPO, "docker-compose.yml"), True, ALLOW, False),
    (os.path.join(REPO, ".claude", "hooks", "tdd-gate.sh"), True, ALLOW, False),
    (os.path.join(tmp, "orphan.test.ts"), True, ALLOW, False),
]

failures = 0
for path, strict, expected_exit, expect_json in CASES:
    code, out = run(path, strict)
    has_json = "additionalContext" in out
    label = f"{os.path.basename(path)}{' [strict]' if strict else ''}"
    if code == expected_exit and has_json == expect_json:
        print(f"PASS: {label} -> exit {code}, advisory={has_json}")
    else:
        failures += 1
        print(f"FAIL: {label} -> exit {code} advisory={has_json}, "
              f"expected exit {expected_exit} advisory={expect_json}")

print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
sys.exit(1 if failures else 0)
