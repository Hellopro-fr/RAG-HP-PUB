# Impact Awareness Rules

> Apply BEFORE every code modification.

## 1. Trade-Off Analysis

Before modifying code, briefly state the **Gain** and **Cost**. If the cost is non-trivial, mention it before proceeding.

## 2. Bigger Picture

- Understand the service's role (check its CLAUDE.md).
- Grep for the same pattern in other services. If found: "This same issue exists in [services]. Fix here only, or fix all?"

## 3. Blast Radius — Shared Components

| Path | Impact |
|------|--------|
| `libs/common-utils/` | 75+ Python services — grep all importers |
| `libs/grpc-stubs/` | All gRPC consumers — verify proto compatibility |
| `protos/grpc_stubs/` | All gRPC services — regeneration required |
| `libs/rust-common-utils/` | Rust service — `cargo check` |
| `docker-compose.yml` | All services — flag env/port changes |

When modifying shared components: list downstream consumers, assess backward compatibility, propose migration if breaking.

- A refusal or guard whose message redirects to another path ("use X instead") → run that path on the same population before merging: two guards on sibling paths can leave no way out.
- A call added towards a service (API, detector, crawl) → check its worst-case latency and cost (retries, forced refresh) against the caller's budget (timeout, cron window, quota).

## 4. When to Skip

Typo fixes, comment-only changes, documentation updates, single-service changes with no shared imports.
