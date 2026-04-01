# Stack Detection Rules

> Single source of truth for detecting a service's technology stack and mapping it to conventions. All stack-dependent rules, agents, and commands MUST reference this file instead of hardcoding their own detection logic.

## Detection Table

Read the service directory and match against these indicators (check in order, first match wins):

| Indicator File | Stack | Package Manager | Test Framework | Formatter | Linter |
|---------------|-------|-----------------|----------------|-----------|--------|
| `Cargo.toml` | Rust | cargo | `cargo test` | `cargo fmt` | `cargo clippy` |
| `package.json` + `next.config.*` | Node.js (Next.js) | npm/yarn/pnpm | Jest or `next test` | Prettier | ESLint (`next lint`) |
| `package.json` + `vite.config.*` | Node.js (Vite) | npm/yarn/pnpm | Vitest | Prettier | ESLint |
| `package.json` | Node.js (generic) | npm/yarn/pnpm | Jest or Vitest (check config) | Prettier | ESLint |
| `go.mod` | Go | go modules | `go test ./...` | `go fmt` | `go vet` / `golangci-lint` |
| `pom.xml` | Java (Maven) | Maven | JUnit (`mvn test`) | google-java-format | Checkstyle / SpotBugs |
| `build.gradle` / `build.gradle.kts` | Java/Kotlin (Gradle) | Gradle | JUnit (`gradle test`) | google-java-format / ktlint | Checkstyle / detekt |
| `requirements.txt` or `pyproject.toml` | Python | pip | pytest | ruff / black | ruff / flake8 |
| `Gemfile` | Ruby | bundler | RSpec / minitest | rubocop | rubocop |
| `composer.json` | PHP | composer | PHPUnit | php-cs-fixer | phpstan / psalm |

## Detection Process

1. **List files** in the service root directory.
2. **Match against the table above** (first match wins).
3. **Check for existing tool configs** in the service (e.g., `.eslintrc`, `ruff.toml`, `pytest.ini`) — these override defaults.
4. **If no match**: treat as **Unknown Stack** (see below).

## Unknown / New Stack Protocol

When a stack is not in the detection table:

1. **List what you found** — show the user the files detected and what stack you think it might be.
2. **Ask the user**: "I detected [files] but this stack is not in my detection table. What conventions should I follow?"
3. **Apply language-agnostic defaults**:
   - Match the file's existing indentation and style.
   - Look for a `Makefile`, `justfile`, or `taskfile` for available commands.
   - Look for a `test/` or `tests/` directory to infer test framework.
   - Look for a `Dockerfile` to infer build process.
4. **Flag for rule update**: "New stack detected: [stack]. Consider updating `.claude/rules/stack-detection.md` to add conventions for this stack."

## How Other Rules Reference This

Rules, agents, and commands that depend on the stack should NOT hardcode stack-specific logic. Instead:

```
Detect the service's stack per `.claude/rules/stack-detection.md`, then apply
the corresponding conventions below.
```

This ensures that when a new stack is added to the detection table, all dependent rules automatically pick it up.

## Updating This Table

When a new stack is introduced to the project:
1. Add a row to the detection table above.
2. Update `formatting.md` with the new stack's style conventions.
3. Update `pre-push.md` with the new stack's check commands.
4. Update `docker-security.md` if the new stack has specific Dockerfile patterns.
5. The `test-writer` agent already handles unknown stacks by asking the user.
