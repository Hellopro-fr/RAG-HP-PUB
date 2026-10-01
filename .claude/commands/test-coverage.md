---
description: Recense les tests par service (Go, Python, vitest, node:test) et classe chacun bien testé / minimal / sans test
allowed-tools: Read, Grep, Glob, Bash
---
# /test-coverage — Test Coverage Report Across Services

Report the current state of test coverage across all services in the monorepo.

## Process

### Step 1 — Scan all services

For each directory in `apps-microservices/`:
1. Detect the stack per `.claude/rules/stack-detection.md`.
2. Look for tests in BOTH layouts: a `tests/` directory (Python), and `*_test.go` files **beside the code** (Go — this is the largest test population in the repo, 243 files, and a directory-only check misses all of them).
3. Count test functions: `func Test` (Go), `def test_` (Python), `it(`/`test(` (vitest and node:test), `#[test]` (Rust).
4. Check the runner actually configured: `conftest.py`/`pytest.ini` (Python), `go.mod` (Go), the `test` script of `package.json` — `vitest run` for the frontends and libs, `node --import tsx --test` for crawler-service. There is no Jest in this repo.

### Step 2 — Categorize services

| Category | Criteria |
|----------|----------|
| **Well-tested** | Has tests directory + 3 or more test files |
| **Minimal tests** | Has tests directory + 1-2 test files |
| **No tests** | No tests directory or empty |

### Step 3 — Report

```
## Test Coverage Report

**Date:** YYYY-MM-DD
**Total services:** N

### Summary
| Category | Count | Percentage |
|----------|-------|------------|
| Well-tested | X | Y% |
| Minimal tests | X | Y% |
| No tests | X | Y% |

### Well-Tested Services
| Service | Stack | Test Files | Test Functions |
|---------|-------|------------|----------------|

### Minimal Tests
| Service | Stack | Test Files | What's missing |
|---------|-------|------------|----------------|

### No Tests (priority targets)
| Service | Stack | Endpoints | Complexity | Priority |
|---------|-------|-----------|------------|----------|

### Recommendations
1. High-priority services to add tests (most endpoints, most critical)
2. Services where @test-writer could be run immediately
```

## Rules

- Do NOT create or modify any files. This is a read-only report.
- Check EVERY service, not just a sample.
- For services without tests, estimate priority based on: number of endpoints, whether it handles user data, whether it's public-facing.
- End with: **"Would you like me to generate tests for any of these services using @test-writer?"**
