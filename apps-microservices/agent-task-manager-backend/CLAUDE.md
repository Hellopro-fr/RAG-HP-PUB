# agent-task-manager-backend

Agent Task Board backend: real-time task board for LLM agents (blackboard, not orchestrator).
REST + SSE for the UI, MCP (`/mcp`, rmcp Streamable HTTP, stateless) for agents.
Frontend: `apps-microservices/agent-task-manager-frontend`.

## Tech Stack
- Rust 1.96, edition 2024, Cargo workspace: `crates/core` (atb-core), `crates/server` (atb-server)
- axum 0.8, tokio, tower-http 0.7, sqlx 0.9 (Postgres, compile-time checked, offline `.sqlx/`),
  utoipa 6, rmcp 3.8, argon2, PostgreSQL 16 (only infrastructure)
- Ports: server 8621 (internal), ingress 8620 (Caddy), Postgres 127.0.0.1:5440 (dev)

## Architecture rules (do not break)
- Layered with a pure domain leaf: `api → service → {core, repository, realtime}`; `core` has no IO.
- One transaction per command (`service::tx::run`): idempotency advisory lock → spec row
  (`FOR NO KEY UPDATE`) → task rows in id order (`FOR UPDATE` / `FOR KEY SHARE` for FK-only
  references) → project row (seq reservation in `tx::persist`). Never lock a task after the project row.
- `repository::projector` is the ONLY writer of projection tables and uses only `meta.at`
  (the event's `created_at`) — never `now()` — so `rebuild-check` (AC-1.8) stays exact.
- Volatile fields (`leases.expires_at`, `leases.last_heartbeat_at`, `actors.last_seen_at`) are the
  only things written outside events (heartbeats, presence).
- Lease tokens are stored and evented as SHA-256 only; fencing checks (actor, token hash).
- `DomainError → HTTP / MCP` mapping lives only in `src/error.rs`.

## Run / test
```bash
docker compose up -d --build          # dev stack from this directory (smoke.sh, demo)
# deployment: repo root, `docker compose --profile agent-task-manager up -d --build`, ATB_* in root .env
bash scripts/test-pg.sh               # integration tests (needs Docker), AC-1.x per file
cargo test -p atb-core                # domain table + proptest
cargo fmt --all --check && cargo clippy --workspace --all-targets -- -D warnings
```
After any query/migration change: `cargo sqlx prepare --workspace -- --all-targets` (commit `.sqlx/`).
After any endpoint change: `cargo run -p atb-server -- dump-openapi > openapi.json` then
`npm run gen:api` in the frontend; `scripts/check-openapi-drift.sh` fails CI otherwise.

## Phase status
Phase 1 implemented. `TODO(phase-2)`: verifier, test_runs/reviews tables, submit_review endpoint,
spec editor. `TODO(phase-3)`: Redis notifier, reservations, DAG view, time travel, k8s.
Deviations from the build spec: `docs/DECISIONS.md`.
