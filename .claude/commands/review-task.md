# /review-task — Tech Lead Task Review

Review a dev's completed work or the current state of a service/feature. Combines full state analysis with diff awareness in a single pass.

## Input

The user provides:
- **What to review**: a service name, a directory, a feature, or "current branch"
- **Acceptance criteria** (optional): specific requirements the work should meet
- **Ticket/task reference** (optional): description of what was requested

If no acceptance criteria are given, review against all project rules.

## Process

### Step 1 — Scope the review

Identify the target files:
- Read the full service/directory to understand the **current state** (main.py, routers, schemas, config, Dockerfile, tests/, CLAUDE.md).
- Check for a branch diff: `git diff origin/main...HEAD --name-only`. If changes exist, also note **what specifically changed** to assess the delta.

Both perspectives are used together — the state gives the bigger picture, the diff highlights what was introduced.

### Step 2 — Run the review chain

For each file/service in scope, evaluate against ALL dimensions:

| # | Dimension | Source | What to Check |
|---|-----------|--------|---------------|
| 1 | **Code quality** | SOLID/DRY/KISS | Structure, duplication, unnecessary complexity |
| 2 | **Security** | `.claude/rules/security.md` | Hardcoded URLs/secrets, input validation, CORS, JWT |
| 3 | **Docker** | `.claude/rules/docker-security.md` | Base image pinned, no root, healthcheck, no secrets in ENV |
| 4 | **Impact** | `.claude/rules/impact-awareness.md` | Shared components affected, trade-offs, blast radius |
| 5 | **Test coverage** | Service `tests/` directory | Do tests exist? Critical paths covered? Test quality? |
| 6 | **CLAUDE.md accuracy** | Service CLAUDE.md vs actual code | Is the documentation up to date with the implementation? |
| 7 | **Acceptance criteria** | User-provided or inferred | Does the implementation meet what was requested? |

If reviewing a diff, also check:
- Are the changes minimal and focused (no unrelated modifications)?
- Are new dependencies justified?
- Are new files following project naming conventions?

### Step 3 — Produce the verdict

```
## Task Review: "<target>"

### Verdict: [APPROVED / CHANGES REQUESTED / BLOCKED]

### State Assessment
- Overall service health: [Good / Needs attention / Poor]
- Test coverage: [X test files, Y endpoints covered / None]
- CLAUDE.md: [Up to date / Stale — needs update]
- Docker compliance: [Compliant / Issues found]

### Changes Introduced (if branch diff exists)
- Files changed: N (list)
- Nature: [Feature / Bug fix / Refactor / Config change]
- Scope: [Focused / Contains unrelated changes]

### Findings

#### 🔴 Critical (must fix before approval)
- [finding with file:line reference]

#### 🟡 Changes Requested (should fix)
- [finding with file:line reference]

#### 🔵 Suggestions (optional improvements)
- [finding with file:line reference]

### Acceptance Criteria Check
| Criteria | Status |
|----------|--------|
| [criterion 1] | ✅ Met / ❌ Not met / ⚠️ Partial |

### Summary
One paragraph: overall assessment, key strengths, key concerns.
```

## Verdict Rules

| Verdict | Condition |
|---------|-----------|
| **APPROVED** | Zero critical findings, zero changes requested, acceptance criteria met |
| **CHANGES REQUESTED** | Zero critical findings, but warnings or unmet criteria exist |
| **BLOCKED** | One or more critical findings — must be resolved |

## Verification Before Verdict

Before issuing ANY verdict, run verification:
1. **Run tests** for every service in scope — read the output, do not assume "should pass."
2. **Check build** — verify syntax/compilation passes for all changed files.
3. **Evidence required** — every PASS in the State Assessment must have a command output backing it. Never use "should," "probably," or "seems to" in a verdict.

If verification cannot be run (remote-only service), explicitly note: "⚠️ Verification skipped — remote-only service. Verdict based on static analysis only."

## Rules

- Be exhaustive — perform multiple internal passes before producing output (same as code-reviewer).
- Read the actual code, not just CLAUDE.md descriptions.
- If the scope is large (3+ services), use sub-agents for parallel review.
- If acceptance criteria are vague, state your interpretation and proceed.
- End with: **"Would you like me to fix any of the findings above?"**
