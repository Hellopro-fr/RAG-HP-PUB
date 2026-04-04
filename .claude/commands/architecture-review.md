# /architecture-review — Architecture-Level Review

Review the architecture of a service, feature, or the entire platform for structural quality, scalability, and maintainability.

## Input

The user provides:
- **Scope**: a service name, a feature area, or "full platform"
- **Focus** (optional): specific concerns (coupling, performance, scalability, security)

## Process

### Step 1 — Understand the architecture

For the target scope:
1. Read CLAUDE.md files for context.
2. Map the service boundaries, communication patterns, and data flows.
3. Identify the tech stack per `.claude/rules/stack-detection.md`.

### Step 2 — Evaluate architecture dimensions

| # | Dimension | What to Check |
|---|-----------|---------------|
| 1 | **Coupling** | Are services tightly coupled? Direct DB access across boundaries? Shared state? |
| 2 | **Cohesion** | Does each service have a single clear responsibility? Mixed concerns? |
| 3 | **Communication patterns** | Sync (HTTP/gRPC) vs async (RabbitMQ) — appropriate for each interaction? |
| 4 | **Data ownership** | Does each service own its data? Cross-service data access patterns? |
| 5 | **Failure handling** | Circuit breakers? DLQ for failed messages? Retry with backoff? Timeout configuration? |
| 6 | **Scalability** | Horizontal scaling possible? Stateless services? Bottleneck identification? |
| 7 | **Observability** | Prometheus metrics? Structured logging? Health checks? Tracing? |
| 8 | **Security** | Per `.claude/rules/security.md` + `.claude/rules/docker-security.md` |

### Step 3 — Identify architectural smells

Common patterns to flag:
- **Distributed monolith**: Services that must be deployed together.
- **Chatty communication**: Many sync calls between services for a single operation.
- **Shared database**: Multiple services accessing the same database directly.
- **Missing async**: Sync calls where async messaging would be more resilient.
- **God service**: One service that does too much (check line count, endpoint count).
- **Circular dependencies**: Service A depends on B depends on A.

### Step 4 — Report

```
## Architecture Review: "<scope>"

### Architecture Score
| Dimension | Score (1-5) | Key Finding |
|-----------|-------------|-------------|
| Coupling | X | ... |
| Cohesion | X | ... |
| Communication | X | ... |
| Data Ownership | X | ... |
| Failure Handling | X | ... |
| Scalability | X | ... |
| Observability | X | ... |
| Security | X | ... |

### Architectural Smells
- 🔴 [Critical smells]
- 🟡 [Warning smells]
- 🔵 [Suggestions]

### Strengths
- [What the architecture does well]

### Recommendations
1. [Prioritized improvement suggestions]

### Trade-offs
- Current approach gains: ...
- Current approach costs: ...
- If changed: gains vs costs
```

## Rules

- Do NOT modify any files. This is a read-only review.
- Read actual code, not just CLAUDE.md descriptions.
- Apply `.claude/rules/impact-awareness.md` for trade-off analysis.
- For full platform reviews, use sub-agents to parallelize service analysis.
- End with: **"Would you like me to elaborate on any finding or create a plan to address specific issues?"**
