# Impact Awareness Rules

> Apply these rules BEFORE every code modification — whether from the main agent, debugger, or any other agent.

## 1. Trade-Off Analysis

Before modifying code, briefly state:
- **Gain:** What the change achieves (bug fix, performance, readability, new feature).
- **Cost:** What it introduces (complexity, new dependency, breaking change, migration needed).
- If the cost is non-trivial, mention it to the user before proceeding.

## 2. Bigger Picture

Do not solve problems in isolation. Before changing code:
- Understand the **service's role** in the pipeline (check its CLAUDE.md).
- Check if the pattern you are fixing or changing exists in **other services** (grep for similar code).
- If the same bug/pattern exists elsewhere, flag it: "This same issue exists in [services]. Fix here only, or fix all?"

## 3. Blast Radius — Shared Components

Changes to these paths affect multiple services. Extra caution required:

| Path | Impact | Action |
|------|--------|--------|
| `libs/common-utils/` | 75+ Python services | Grep for all importers of the changed module. List affected services. |
| `libs/grpc-stubs/` | All gRPC consumers | Verify proto compatibility. Check Python + Rust consumers. |
| `protos/grpc_stubs/` | All gRPC services | Regeneration required. Flag breaking changes (removed/renamed fields). |
| `libs/rust-common-utils/` | Rust service | Verify `cargo check` passes. |
| `docker-compose.yml` | All services | Flag environment variable or port changes that affect other services. |
| `.claude/rules/`, `.claude/agents/` | All contributors | Changes affect every team member's AI-assisted workflow. |

When modifying a shared component:
1. List all downstream consumers (use `grep` on import statements).
2. Assess if the change is **backward-compatible** (additive) or **breaking** (removal/rename).
3. If breaking: propose a migration path or flag for team discussion.

## 4. When to Skip

- Typo fixes, comment-only changes, and documentation updates do not need trade-off analysis.
- Changes scoped to a single service with no shared imports can use a lighter-weight assessment.
