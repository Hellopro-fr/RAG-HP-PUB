# /audit-feature — End-to-End Feature Audit

Audit a complete feature across the microservice pipeline — from API entry point to database and back.

## Input

The user provides:
- **Feature name** (e.g., "product search", "document ingestion", "price extraction")
- Optionally: specific services to focus on

## Process

### Step 1 — Map the feature flow

Trace the feature across services. Identify:
- **Entry point**: Which API service receives the request?
- **Message flow**: Which RabbitMQ exchanges/queues are involved?
- **Processors**: Which processor services handle the data?
- **Storage**: Which databases (Qdrant, Milvus, Neo4j, Redis) are written to/read from?
- **Response path**: How does the result get back to the caller?

Present the flow as a numbered chain:
```
1. api-ingestion (POST /ingest) → publishes to data_exchange
2. product-processor-service (consumes from product_processing_queue) → transforms
3. product-database-qdrant-service (upserts to Qdrant) → indexes
4. api-recherche (GET /search) → queries Qdrant → returns results
```

### Step 2 — Audit each service in the chain

For each service involved, check:

| Dimension | What to Check |
|-----------|---------------|
| **Code quality** | SOLID/DRY/KISS violations, error handling |
| **Security** | Per `.claude/rules/security.md` — hardcoded URLs, input validation, CORS |
| **Docker** | Per `.claude/rules/docker-security.md` — base image, health check, secrets |
| **Test coverage** | Does `tests/` exist? How many test files? Any critical paths untested? |
| **CLAUDE.md accuracy** | Does the service CLAUDE.md reflect current state? Stale info? |
| **Impact awareness** | Per `.claude/rules/impact-awareness.md` — shared components used? |

### Step 3 — Produce the audit report

```
## Feature Audit: "<feature name>"

### Flow
[numbered chain from Step 1]

### Per-Service Findings

#### <service-1>
- 🔴 [Critical findings]
- 🟡 [Warnings]
- 🔵 [Suggestions]
- Test coverage: X test files / Y endpoints covered

#### <service-2>
...

### Cross-Service Findings
- [Issues that span multiple services: inconsistent schemas, missing error propagation, etc.]

### Summary
- Total services audited: N
- Critical findings: N
- Warnings: N
- Test coverage gaps: [list services with no tests]
```

## Rules

- Do NOT modify any code. This is a read-only audit.
- Read the actual source code of every service in the chain — do not rely on CLAUDE.md alone.
- Use sub-agents for parallel service audits when auditing 3+ services.
- If the feature flow is unclear, ask the user before proceeding.
- End with: **"Would you like me to fix any of these findings?"**
