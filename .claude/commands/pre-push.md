# /pre-push — Pre-Push Verification Checklist

Run this checklist before pushing code to the remote repository.

## Process

For EACH service that was modified in the current session:

### Step 1 — Identify changed files
Run `git diff --name-only origin/main...HEAD` to find all files changed in the current branch.
Group them by service directory.

### Step 2 — Per-service checks

For each affected service:

**Python services:**
1. Check syntax: `python -m py_compile <modified_files>`
2. Check imports: verify no circular imports, no unused imports visible
3. Run tests if they exist: `pytest apps-microservices/<service>/tests/ -v --tb=short -x`
4. If no tests exist, flag: "⚠️ No tests found for <service>. Consider using @test-writer."

**Rust services:**
1. `cargo check --manifest-path apps-microservices/<service>/Cargo.toml`
2. `cargo test --manifest-path apps-microservices/<service>/Cargo.toml` (if tests exist)

**TypeScript/Node.js services:**
1. Check if lint script exists in package.json, run it
2. Check if test script exists in package.json, run it

**Shared libraries (libs/):**
1. Check syntax and imports
2. Run tests if they exist
3. Flag: "⚠️ Changes to libs/ affect multiple services. Review downstream impact."

### Step 3 — Code review
Review all changed files for SOLID/DRY/KISS violations, security issues, and performance concerns.
Note: This step is a manual review by the main agent — do NOT delegate to `@code-reviewer` (it lacks Bash access needed for this workflow context).

### Step 4 — Summary
Display a summary table:
| Service | Syntax | Tests | Review | Status |
|---------|--------|-------|--------|--------|

End with: "All checks passed. Safe to push." or "⚠️ Issues found. Fix before pushing."
