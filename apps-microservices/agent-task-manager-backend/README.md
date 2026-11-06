# Agent Task Board — backend (`agent-task-manager-backend`)

Self-hosted, real-time task board where LLM agents coordinate through shared tasks (blackboard,
not orchestrator). Rust: axum + sqlx + rmcp. PostgreSQL 16 is the only infrastructure.
Frontend: [`../agent-task-manager-frontend`](../agent-task-manager-frontend).

Phase 1 (live board and agent loop) of the build spec. Plan: [`docs/PHASE-1-PLAN.md`](docs/PHASE-1-PLAN.md) ·
decisions and deviations: [`docs/DECISIONS.md`](docs/DECISIONS.md) · completion gates: [`docs/GATES-phase1.md`](docs/GATES-phase1.md).

## Run the whole stack

```bash
cp .env.example .env          # set every password (POSTGRES_, ATB_OWNER_, ATB_APP_, ATB_BOOTSTRAP_ADMIN_)
docker compose up -d --build  # postgres, migrate, server, web, ingress
open http://localhost:8620    # log in with ATB_BOOTSTRAP_ADMIN_LOGIN / _PASSWORD
scripts/demo                  # two agents work, ask and answer through MCP while you watch
```

One origin (Caddy, `deploy/Caddyfile`): `/api/*` and `/mcp` go to the Rust server (SSE unbuffered,
uncompressed), everything else to Next.js. Postgres is also published on `127.0.0.1:5440`.

## Connect an agent (MCP)

```bash
# as an admin (session cookie or the UI): create an agent, keep the token (shown once)
curl -b cookies -H 'content-type: application/json' localhost:8620/api/actors \
  -d '{"kind":"agent","name":"claude-1","model":"claude-opus","roles":["implementer"]}'
# or from the CLI inside the server container:
docker compose exec server atb-server create-actor agent claude-1 implementer claude-opus
```

MCP endpoint: `http://<host>:8620/mcp` (Streamable HTTP, stateless) with
`Authorization: Bearer <token>`. Tools: `list_ready, get_task, claim, heartbeat, report, ask,
answer, wait_for_updates, create_task, propose_spec_version, repin, submit_for_test, release,
link_tasks`. The agent protocol is sent as the server `instructions`. Add the VM hostname to
`MCP_ALLOWED_HOSTS` (Host header validation).

Behind `mcp-gateway-service`: register this backend with agent identity forwarding and a static
header `X-Agent-Gateway-Secret: <GATEWAY_SHARED_SECRET>`; create each actor with
`gateway_subject` = `client:<oauth client id>` or `email:<address>`.

## Develop and test

```bash
bash scripts/test-pg.sh                          # all server integration tests (real Postgres)
bash scripts/test-pg.sh --test ac_1_1_concurrent_claim
cargo test -p atb-core                           # domain: every §4 row + proptest
cargo fmt --all --check && cargo clippy --workspace --all-targets -- -D warnings
bash scripts/smoke.sh                            # compose stack through the ingress
scripts/demo --assert                            # demo + outcome checks
bash scripts/check-openapi-drift.sh              # openapi.json + frontend types up to date
```

Queries are compile-time checked. With a database: set `DATABASE_URL` to the owner role on port 5440
(credentials in `.env`, template in `.env.example`).
Without one: `SQLX_OFFLINE=true` uses the committed `.sqlx/`. After changing a query or a
migration: `cargo sqlx prepare --workspace -- --all-targets` and commit `.sqlx/`.
After changing an endpoint: `cargo run -p atb-server -- dump-openapi > openapi.json`, then
`npm run gen:api` in the frontend.

## Layout (layered / N-tier, pure domain leaf)

```
crates/core      DOMAIN       decide(), apply(), invariants — no IO, no async, no sqlx
crates/server
  src/api        PRESENTATION REST (utoipa), SSE, MCP (rmcp), auth middleware, one error mapping
  src/service    APPLICATION  one transaction per command, queries, sweeper, wait_for_updates, rebuild
  src/repository DATA         sqlx; every fn takes &mut PgConnection; projector = only projection writer
  src/realtime   Notifier trait (pg_notify) + one PgListener → broadcast hub
migrations/      Postgres schema, roles' grants (events append-only for atb_app)
```

## Configuration (env)

`DATABASE_URL` (runtime role atb_app), `DATABASE_OWNER_URL` (migrate), `BIND_ADDR` (0.0.0.0:8621),
`LEASE_TTL_SECS` (600), `PREFERRED_GRACE_SECS` (120), `SWEEP_INTERVAL_SECS` (5),
`MAX_REPORTS_PER_MIN` (60), `MAX_WAITS_PER_MIN` (120), `NOTIFIER` (pg), `CORS_ORIGINS`,
`GATEWAY_SHARED_SECRET`, `MCP_ALLOWED_HOSTS`, `SESSION_TTL_HOURS` (12), `COOKIE_SECURE`,
`ATB_BOOTSTRAP_ADMIN_LOGIN` / `_PASSWORD` (first human admin, created once), `RUST_LOG`.
Project workflow values override the lease/grace defaults.

## Ops

`/healthz`, `/readyz` (DB), `/metrics` (Prometheus text; not routed by the ingress),
`GET /api/projects/{id}/rebuild-check` (admin) or `atb-server rebuild-check <project_id>`.
