# Stack Detection Rules

> Single source of truth for detecting a service's technology stack. All stack-dependent rules MUST reference this file.

## Detection Table

Match in order (first match wins):

| Indicator | Stack | Tests | Formatter | Linter |
|-----------|-------|-------|-----------|--------|
| `Cargo.toml` | Rust | `cargo test` | `cargo fmt` | `cargo clippy` |
| `package.json` + `next.config.*` | Next.js | Jest / `next test` | Prettier | ESLint |
| `package.json` + `vite.config.*` | Vite | Vitest | Prettier | ESLint |
| `package.json` | Node.js | Jest/Vitest | Prettier | ESLint |
| `go.mod` | Go | `go test ./...` | `go fmt` | `go vet` |
| `pom.xml` | Java (Maven) | JUnit | google-java-format | Checkstyle |
| `build.gradle*` | Java/Kotlin | JUnit | google-java-format / ktlint | detekt |
| `requirements.txt` / `pyproject.toml` | Python | pytest | ruff/black | ruff/flake8 |
| `Gemfile` | Ruby | RSpec/minitest | rubocop | rubocop |
| `composer.json` | PHP | PHPUnit | php-cs-fixer | phpstan |

## Detection Process

1. List files in service root → match table above.
2. Check for existing tool configs (`.eslintrc`, `ruff.toml`, `pytest.ini`) — these override defaults.
3. No match → Unknown Stack (see below).

## Unknown / New Stack

1. Show detected files and your stack guess to the user.
2. Ask: "What conventions should I follow?"
3. Apply defaults: match existing style, look for Makefile/tests/Dockerfile.
4. Flag: "New stack detected. Consider updating `stack-detection.md`."
