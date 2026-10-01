"""Self-check for .claude/hooks/secret-scanner.py.

The case that matters: this hook runs BEFORE the command, so on
`git add . && git commit` nothing is staged yet. Looking only at the index
returned an empty list and the secret went in unscanned. `stages_new_content`
is what closes that hole — any change to it must keep these cases passing.

Run: python test_secret_scanner.py   -> PASS/FAIL per case, exit 1 on failure.
"""
import importlib.util
import os
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "secret-scanner.py")
SPEC = importlib.util.spec_from_file_location("scanner", HOOK)
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)

failures = 0


def check(label, got, expected):
    global failures
    if got == expected:
        print(f"PASS: {label}")
    else:
        failures += 1
        print(f"FAIL: {label} -> got {got!r}, expected {expected!r}")


# --- the working tree must be scanned whenever the command stages content ---
for cmd in ("git add .",
            "git add -A && git commit -m 'wip'",
            "git add src/foo.py",
            "git commit -am 'wip'",
            "git commit -a -m 'wip'"):
    check(f"stages_new_content({cmd!r})", scanner.stages_new_content(cmd), True)

# --- ...and only then: a plain commit of an already-built index does not ---
for cmd in ("git commit -m 'wip'",
            "git commit -F msg.txt",
            "git status",
            "git log --oneline -1"):
    check(f"stages_new_content({cmd!r})", scanner.stages_new_content(cmd), False)

# --- porcelain parsing: statuses, renames, quoted paths ---
check("porcelain: modified + untracked",
      scanner.porcelain_paths(" M src/a.py\n?? notes.txt\n"),
      ["src/a.py", "notes.txt"])
check("porcelain: rename keeps destination",
      scanner.porcelain_paths("R  old.py -> new.py\n"),
      ["new.py"])
check("porcelain: quoted path",
      scanner.porcelain_paths('?? "with space.py"\n'),
      ["with space.py"])
check("porcelain: blank input", scanner.porcelain_paths(""), [])

# --- end to end: a real secret in a real file is detected ---
tmp = tempfile.mkdtemp(prefix="secret_scanner_")
leaky = os.path.join(tmp, "config.py")
with open(leaky, "w") as f:
    f.write('AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n')
clean = os.path.join(tmp, "ok.py")
with open(clean, "w") as f:
    f.write('API_KEY = os.environ["API_KEY"]\n')

check("scan_file finds a hardcoded secret", len(scanner.scan_file(leaky)) > 0, True)
check("scan_file is quiet on an env lookup", scanner.scan_file(clean), [])

print(f"\n{'FAILED' if failures else 'OK'} — {failures} failure(s)")
sys.exit(1 if failures else 0)
