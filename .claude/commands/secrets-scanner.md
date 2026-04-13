# /secrets-scanner — Full Codebase Secrets Audit

Scan the entire codebase for hardcoded secrets, API keys, passwords, and connection strings.

## Process

### Step 1 — Define scan scope

Scan ALL files across:
- `apps-microservices/` — all 90+ service directories
- `libs/` — shared libraries
- `tools/` — utility scripts
- `docker-compose.yml` — environment variables
- `.github/workflows/` — CI/CD secrets

### Step 2 — Scan for patterns

Search for these categories using Grep across the codebase:

| Category | Patterns |
|----------|----------|
| **API Keys** | `sk-ant-`, `sk-`, `AKIA`, `AIza`, `ghp_`, `glpat-`, `hf_`, `gsk_` |
| **Connection strings** | `mongodb://`, `postgres://`, `mysql://`, `redis://`, `amqp://`, `neo4j://` |
| **Hardcoded URLs** | `localhost:`, `127.0.0.1:`, `http://` followed by IP addresses |
| **Passwords** | `password=`, `passwd=`, `pwd=` with string values |
| **Tokens** | `token=`, `secret=`, `api_key=` with string values |
| **Private keys** | `-----BEGIN.*PRIVATE KEY-----` |
| **JWT** | `eyJ` (base64 JWT prefix) |

### Step 3 — Classify findings

For each finding, classify:

| Severity | Criteria |
|----------|----------|
| 🔴 **Critical** | Real secret with high entropy (API key, private key, connection string with credentials) |
| 🟡 **Warning** | Hardcoded URL (localhost, IP address), default password, low-entropy token |
| 🔵 **Info** | Placeholder values (`changeme`, `TODO`), example patterns in docs |

### Step 4 — Cross-reference with security.md

Check each finding against `.claude/rules/security.md`:
- Is it in the "Known violations to fix" list? Mark as **KNOWN**.
- Is it new? Mark as **NEW**.

### Step 5 — Report

```
## Secrets Scan Report

**Scanned:** X files across Y services
**Date:** YYYY-MM-DD

### 🔴 Critical (N findings)
| # | File:Line | Type | Status |
|---|-----------|------|--------|
| 1 | path/to/file.py:42 | AWS Access Key | NEW |

### 🟡 Warning (N findings)
| # | File:Line | Type | Status |
|---|-----------|------|--------|

### 🔵 Info (N findings)
| # | File:Line | Type | Status |
|---|-----------|------|--------|

### Known Violations (from security.md)
- [status: fixed/still present] path/to/file.py — description
```

## Rules

- Do NOT modify any files. This is a read-only scan.
- Be exhaustive — scan every service, not just a sample.
- Exclude: `.env.example`, `*.lock`, `node_modules/`, `.venv/`, `.git/`, test fixtures with fake data.
- End with: **"Would you like me to fix any of these findings?"**
