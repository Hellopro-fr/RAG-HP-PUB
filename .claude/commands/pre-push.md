# /pre-push — Pre-Push Verification Checklist

Run this checklist before pushing code to the remote repository.

## Process

### Step 1 — Identify changed files
Run `git diff --name-only origin/main...HEAD`. Group by service directory.

### Step 2 — Per-service checks

Detect each service's stack per `.claude/rules/stack-detection.md`, then run syntax checks and tests.

For shared libraries (`libs/`): flag downstream impact per `.claude/rules/impact-awareness.md`.

### Step 3 — Code review
Review all changed files for SOLID/DRY/KISS violations, security issues, and performance concerns.

### Step 4 — Verification discipline

- Every check must have a concrete PASS or FAIL from running the actual command.
- If claiming "tests pass", show the output. No "should be fine" without evidence.

### Step 5 — Summary

| Service | Syntax | Tests | Review | Status |
|---------|--------|-------|--------|--------|

End with: "All checks passed. Safe to push." or "Issues found. Fix before pushing."
