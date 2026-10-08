"""Self-check for .claude/hooks/secret-scanner.py.

The cases that matter:
- this hook runs BEFORE the command, so on `git add . && git commit` nothing is
  staged yet. Looking only at the index returned an empty list and the secret
  went in unscanned. What the command is about to stage must be scanned too;
- the scan must run in the repository the command TARGETS (`git -C <dir>`,
  `cd <dir> && ...`), not in the hook's working directory (A195): the old hook
  let `git -C <repo> add .` through unscanned, and blocked a commit of another
  repository on a file of this one.

Run: python test_secret_scanner.py   -> PASS/FAIL per case, exit 1 on failure.
     SECRET_SCANNER_HOOK=<other copy> python test_secret_scanner.py --e2e-only
         -> the end-to-end section alone, against another copy of the hook
            (an older version, or the copy of another repository being ported).
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

HOOK = os.environ.get("SECRET_SCANNER_HOOK") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "secret-scanner.py")
E2E_ONLY = "--e2e-only" in sys.argv

failures = 0


def check(label, got, expected):
    global failures
    if got == expected:
        print(f"PASS: {label}")
    else:
        failures += 1
        print(f"FAIL: {label} -> got {got!r}, expected {expected!r}")


# Built at runtime so that this file never carries a matching literal.
SECRET_LINE = "OPENAI = 'sk-" + "A1b2C3d4" * 4 + "'\n"


def git(repo, *args):
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@t", "-c", "user.name=t",
                    "-c", "core.autocrlf=false"] + list(args),
                   check=True, capture_output=True)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def make_repo(root, name):
    repo = os.path.join(root, name).replace("\\", "/")
    os.makedirs(repo)
    git(repo, "init", "-q")
    write(f"{repo}/tracked.txt", "clean\n")
    write(f"{repo}/.gitignore", "*.log\n")
    git(repo, "add", "tracked.txt", ".gitignore")
    git(repo, "commit", "-qm", "init")
    return repo


def run_hook(command, cwd, tool="Bash"):
    """Exit code of the hook for `command` issued from `cwd`."""
    payload = json.dumps({"tool_name": tool, "cwd": cwd,
                          "tool_input": {"command": command}})
    res = subprocess.run([sys.executable, HOOK], input=payload.encode("utf-8"),
                         capture_output=True, cwd=cwd, timeout=120)
    return res.returncode


root = tempfile.mkdtemp(prefix="secret_scanner_")
try:
    # dirty: an untracked file carrying a secret. clean: nothing to find.
    dirty = make_repo(root, "dirty")
    clean = make_repo(root, "clean")
    write(f"{dirty}/leak.txt", SECRET_LINE)
    write(f"{dirty}/ok.txt", "nothing here\n")
    write(f"{clean}/ok.txt", "nothing here\n")

    # --- end to end: the hook process, as Claude Code runs it ---
    check("e2e: `git -C <dirty> add .` from another repo is scanned (A195-1)",
          run_hook(f"git -C {dirty} add .", clean), 2)
    check("e2e: `cd <dirty> && git add .` from another repo is scanned",
          run_hook(f"cd {dirty} && git add .", clean), 2)
    check("e2e: committing <clean> is not blocked by a file of the hook's cwd (A195-2)",
          run_hook(f"git -C {clean} add ok.txt && git -C {clean} commit -m wip", dirty), 0)
    check("e2e: `cd <clean> && git add` is scanned in <clean>, not in the hook's cwd (A195-2)",
          run_hook(f"cd {clean} && git add ok.txt && git commit -m wip", dirty), 0)
    check("e2e: the dominant idiom `git add . && git commit` is still scanned",
          run_hook("git add . && git commit -m wip", dirty), 2)
    check("e2e: PowerShell `Set-Location <dirty>; git add -A` is scanned",
          run_hook(f"Set-Location {dirty}; git add -A", clean, tool="PowerShell"), 2)
    check("e2e: a quoted `git add` in a grep pattern does not trigger",
          run_hook('grep -n "git add" notes.txt', dirty), 0)
    if E2E_ONLY:
        raise SystemExit

    spec = importlib.util.spec_from_file_location("scanner", HOOK)
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)

    def stages(command, cwd=clean, dialect="bash"):
        return [(t.prefix, t.stage) for t in scanner.plan_targets(command, dialect, cwd)]

    def prefix(*dirs):
        return ("git", "-C", clean) + tuple(x for d in dirs for x in ("-C", d))

    # --- what each command is about to stage ---
    check("plan: git add .", stages("git add ."), [(prefix(), ("dry-run", (".",)))])
    check("plan: git stage f", stages("git stage f"), [(prefix(), ("dry-run", ("f",)))])
    check("plan: git -C <dirty> add f",
          stages(f"git -C {dirty} add f"), [(prefix(dirty), ("dry-run", ("f",)))])
    check("plan: cd <dirty> && git add f",
          stages(f"cd {dirty} && git add f"),
          [(("git", "-C", os.path.normpath(dirty)), ("dry-run", ("f",)))])
    check("plan: bash -c 'cd <dirty> && git add f'",
          stages(f"bash -c 'cd {dirty} && git add f'"),
          [(("git", "-C", os.path.normpath(dirty)), ("dry-run", ("f",)))])
    check("plan: subshell cd does not leak out",
          [p for p, _ in stages(f"(cd {dirty} && git add a) && git add b")],
          [("git", "-C", os.path.normpath(dirty)), prefix()])
    check("plan: git add -A && git commit -m wip",
          stages("git add -A && git commit -m 'wip'"),
          [(prefix(), ("dry-run", ("-A",))), (prefix(), ("none", ()))])
    check("plan: redirection is not a pathspec",
          stages("git add f 2>&1"), [(prefix(), ("dry-run", ("f",)))])
    check("plan: env assignment before git",
          stages("PYTHONIOENCODING=utf-8 git commit -am wip"), [(prefix(), ("tracked", ()))])
    for cmd in ("git commit -am 'wip'", "git commit -a -m 'wip'", "git commit --all -m wip"):
        check(f"plan: {cmd}", stages(cmd), [(prefix(), ("tracked", ()))])
    for cmd in ("git commit -m 'wip'", "git commit -F msg.txt", "git commit --amend --no-edit",
                "git commit -m wip --author 'A <a@b>'"):
        check(f"plan: {cmd}", stages(cmd), [(prefix(), ("none", ()))])
    check("plan: git commit with a pathspec takes it from the working tree",
          stages("git commit -m wip src/a.php"), [(prefix(), ("dry-run", ("--", "src/a.php")))])
    check("plan: unresolvable argument falls back to the whole status",
          stages("git add $FILES"), [(prefix(), ("superset", ()))])
    check("plan: here-doc body is data, not a command",
          stages("git commit -F - <<'EOF'\nfix: git add . is no longer needed\nEOF"),
          [(prefix(), ("none", ()))])
    check("plan: unparseable command falls back to the former behaviour",
          stages("git commit -m \"it's"), [(("git", "-C", clean), ("superset", ()))])
    for cmd in ("git status", "git log --oneline -1", "git diff --cached", 'grep -n "git add" f'):
        check(f"plan: {cmd} -> nothing", stages(cmd), [])
    check("plan: PowerShell keeps backslashes in paths",
          stages("Set-Location " + dirty.replace("/", "\\") + "; git add f", dialect="powershell"),
          [(("git", "-C", os.path.normpath(dirty)), ("dry-run", ("f",)))])
    if os.name == "nt":
        check("plan: MSYS drive path /d/x -> D:/x",
              stages("git -C /d/x add f"), [(prefix("D:/x"), ("dry-run", ("f",)))])

    # --- what is actually read ---
    def findings(command, cwd):
        out = []
        for t in scanner.plan_targets(command, "bash", cwd):
            out += scanner.collect_findings(t)
        return sorted({os.path.basename(f[0].split("] ")[-1]) for f in out})

    check("scan: named paths only — an unrelated dirty file does not block (A195-5)",
          findings("git add ok.txt", dirty), [])
    check("scan: git add -A sees the untracked secret",
          findings("git add -A", dirty), ["leak.txt"])
    check("scan: a failing dry run falls back to the whole status",
          findings("git add no-such-file.txt", dirty), ["leak.txt"])
    write(f"{dirty}/forced.log", SECRET_LINE)
    check("scan: `git add -f` of an ignored file is scanned",
          findings("git add -f forced.log", dirty), ["forced.log"])
    write(f"{dirty}/sub/é accent.txt", SECRET_LINE)
    check("scan: a non-ASCII path is read, not skipped",
          findings("git add -- 'sub/é accent.txt'", dirty), ["é accent.txt"])
    write(f"{dirty}/tracked.txt", SECRET_LINE)
    check("scan: commit -a reads the tracked changes",
          findings("git commit -am wip", dirty), ["tracked.txt"])
    check("scan: commit with a pathspec reads it",
          findings("git commit -m wip tracked.txt", dirty), ["tracked.txt"])
    # The staged copy, not the working-tree one, is what gets committed.
    write(f"{clean}/staged.txt", SECRET_LINE)
    git(clean, "add", "staged.txt")
    write(f"{clean}/staged.txt", "cleaned after staging\n")
    check("scan: the index is read as staged content",
          findings("git commit -m wip", clean), ["staged.txt"])
    git(clean, "reset", "-q", "--", "staged.txt")
    write(f"{clean}/fix.patch", "+" + SECRET_LINE)
    check("scan: git apply --cached reads the patch file",
          findings("git apply --cached fix.patch", clean), ["fix.patch"])
    check("scan: git hash-object -w reads its input",
          findings(f"git hash-object -w {dirty}/leak.txt", clean), ["leak.txt"])

    # --- porcelain -z parsing: statuses, renames, odd names ---
    check("porcelain: modified + untracked",
          scanner.porcelain_paths(" M src/a.py\0?? notes.txt\0"), ["src/a.py", "notes.txt"])
    check("porcelain: rename keeps destination, skips source",
          scanner.porcelain_paths("R  new.py\0old.py\0?? x\0"), ["new.py", "x"])
    check("porcelain: space and accent kept verbatim",
          scanner.porcelain_paths("?? with space é.py\0"), ["with space é.py"])
    check("porcelain: blank input", scanner.porcelain_paths(""), [])

    # --- the scanner itself ---
    leaky = os.path.join(root, "config.py")
    write(leaky, 'AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n')
    env_lookup = os.path.join(root, "ok.py")
    write(env_lookup, 'API_KEY = os.environ["API_KEY"]\n')
    check("scan_file finds a hardcoded secret", len(scanner.scan_file(leaky)) > 0, True)
    check("scan_file is quiet on an env lookup", scanner.scan_file(env_lookup), [])
    fallback = os.path.join(root, "settings.py")
    write(fallback, 'REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")\n')
    check("scan_file skips an env-var fallback to an internal host",
          scanner.scan_file(fallback), [])
except SystemExit:
    pass
finally:
    shutil.rmtree(root, ignore_errors=True)

print(f"\n{'FAILED' if failures else 'OK'} — {failures} failure(s)")
sys.exit(1 if failures else 0)
