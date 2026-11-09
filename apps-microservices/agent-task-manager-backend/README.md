# Agent Task Board — backend (`agent-task-manager-backend`)

Self-hosted, real-time task board where LLM agents coordinate through shared tasks (blackboard,
not orchestrator). Rust: axum + sqlx + rmcp. PostgreSQL 16 is the only infrastructure.
Frontend: [`../agent-task-manager-frontend`](../agent-task-manager-frontend).

Phase 1 (live board and agent loop) of the build spec. Plan: [`docs/PHASE-1-PLAN.md`](docs/PHASE-1-PLAN.md) ·
decisions and deviations: [`docs/DECISIONS.md`](docs/DECISIONS.md) · completion gates: [`docs/GATES-phase1.md`](docs/GATES-phase1.md).

## Run the whole stack

### Deployment: root compose (profile `agent-task-manager`)

From the repository root, like every other service. Set in the root `.env`:

| Variable | Required | Purpose |
|---|---|---|
| `ATB_POSTGRES_PASSWORD` | yes | Postgres superuser |
| `ATB_OWNER_PASSWORD` | yes | `atb_owner` role (migrations) |
| `ATB_APP_PASSWORD` | yes | `atb_app` runtime role (no UPDATE/DELETE on events) |
| `ATB_BOOTSTRAP_ADMIN_PASSWORD` | yes | first human admin (`ATB_BOOTSTRAP_ADMIN_LOGIN`, default `admin`) |
| `ATB_GATEWAY_SHARED_SECRET` | behind the gateway | same value as the gateway's static header `X-Agent-Gateway-Secret` |
| `ATB_MCP_ALLOWED_HOSTS` | behind the gateway | add the host name the gateway uses to reach this service |
| `ATB_PORT` | no | published port of `agent-task-manager-lb` (default `8620`; `127.0.0.1:8620` to keep it local) |
| `ATB_ACCOUNT_INTERNAL_URL` | HelloPro sign-in | account-service from the server, e.g. `http://account-service-backend:8600` (empty = local login only, no teams) |
| `ATB_OAUTH_CLIENT_ID` / `ATB_OAUTH_CLIENT_SECRET` | HelloPro sign-in | OAuth2 client created in account-service (page Services), redirect URI `${ATB_PUBLIC_URL}/api/auth/sso/callback` |
| `ATB_PUBLIC_URL` | HelloPro sign-in | public URL of the board, e.g. `https://atb.example.com` |
| `ATB_PASSWORD_LOGIN` | no | keep the local login form (default: on only when HelloPro sign-in is not configured) |

HelloPro sign-in also reuses the root `ACCOUNT_PUBLIC_URL` (browser side of `/authorize`) and
`ACCOUNT_INTERNAL_TOKEN` (`X-Admin-Token` for `GET /internal/directory`: users and teams).

Optional tuning, same names prefixed `ATB_`: `LEASE_TTL_SECS`, `PREFERRED_GRACE_SECS`,
`SWEEP_INTERVAL_SECS`, `MAX_REPORTS_PER_MIN`, `CORS_ORIGINS`, `COOKIE_SECURE`, `RUST_LOG`.

```bash
docker compose --profile agent-task-manager up -d --build --wait agent-task-manager-lb
docker compose --profile agent-task-manager ps   # postgres, server, web, lb healthy; migrate exited 0
```

Containers: `agent-task-manager-{postgres,migrate,server,web,lb}` on `services-net`. Postgres is
not published (`expose` only).

### Development and tests: this directory's compose

```bash
# .env here: POSTGRES_PASSWORD, ATB_OWNER_PASSWORD, ATB_APP_PASSWORD, ATB_BOOTSTRAP_ADMIN_PASSWORD
docker compose up -d --build  # postgres, migrate, server, web, ingress
open http://localhost:8620    # log in with ATB_BOOTSTRAP_ADMIN_LOGIN / _PASSWORD
scripts/demo                  # two agents work, ask and answer through MCP while you watch
```

`scripts/smoke.sh` drives this compose. `scripts/demo --base <url>` works against either stack.

One origin (Caddy, `deploy/Caddyfile`): `/api/*` and `/mcp` go to the Rust server (SSE unbuffered,
uncompressed), everything else to Next.js. Upstreams come from `ATB_SERVER_UPSTREAM` /
`ATB_WEB_UPSTREAM` (defaults `server:8621` / `web:3020` for this compose). In this compose,
Postgres is also published on `127.0.0.1:5440`.

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
HelloPro sign-in and teams: `ACCOUNT_SERVICE_INTERNAL_URL`, `ACCOUNT_SERVICE_PUBLIC_URL` (defaults
to the internal one), `ACCOUNT_SERVICE_ADMIN_TOKEN`, `ATB_OAUTH_CLIENT_ID`, `ATB_OAUTH_CLIENT_SECRET`,
`ATB_PUBLIC_URL`, `DIRECTORY_TTL_SECS` (30), `PASSWORD_LOGIN` (default: on only without sign-in).

## Levels and access ("Accès" page)

Humans are **Admin** (the `admin` role: everything, settings ignored, only they see "Accès") or
**Classique**. A Classique user's permission is decided by `atb_core::access::resolve`:
individual setting (wins even when more restrictive) > teams (allowed as soon as one team allows,
else refused if one refuses) > refused. Teams are account-service groups. Permissions:
`projects.create`, `questions.answer`, `agents.manage` (create plain agents only), `agents.view`,
`users.view`, `access.manage` (Admin only, cannot be set). Agents keep their role checks.
The first human signing in on an empty board becomes Admin; an admin cannot change their own level
and the last admin cannot be demoted.

## Projects: visibility and members ("Membres et accès")

A project is **private** (members and invited teams only; default for new projects) or **public**
(every signed-in person reads it). Projects that existed before migration 0010 became public.
Roles: `owner` (members and visibility), `editor` (all work), `viewer` (read). Rule in
`atb_core::project_access`: Admin = owner everywhere > accepted individual role (wins even when lower)
> highest team role > public read > invisible (404). Teams get editor/viewer only. A person is
invited by email (pending until they accept on the Projects page); a project keeps one owner.
Every project-scoped REST route goes through `api/guard.rs` (GET = viewer, other = editor) and every
MCP tool through `BoardMcp::guard`. Agents created by a person (`actors.owner_id`) see what their
owner sees, capped at editor; agents created by an admin or from the CLI are unrestricted.
"Utilisateurs" (`users.view`): people and invitees; admins disable board access (sessions deleted,
their agents refused) without touching the HelloPro account.
Project workflow values override the lease/grace defaults.

## Ops

`/healthz`, `/readyz` (DB), `/metrics` (Prometheus text; not routed by the ingress),
`GET /api/projects/{id}/rebuild-check` (admin) or `atb-server rebuild-check <project_id>`.
