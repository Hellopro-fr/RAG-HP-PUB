# Agent Task Board — Phase 1 plan (live board and agent loop)

Status: **awaiting approval** — no code is written until this plan is OK'd.
Source spec: build spec "real-time task board for LLM agents (Rust + Next.js)", §11 Phase 1.
Decisions and deviations: `docs/DECISIONS.md`. Completion contract: `docs/GATES-phase1.md`.

## 0. Pinned toolchain (measured 2026-11-05)

| Item | Version | Note |
|---|---|---|
| rustc / cargo | 1.96.1 | Docker builder `rust:1.96-slim`, runtime `debian:bookworm-slim` |
| axum | 0.8.9 | |
| sqlx | **0.9.0** | new major — `PgListener`, `sqlx::test`, offline `.sqlx` re-checked via Context7 before use |
| rmcp | **3.8.0** | new major — Streamable HTTP + `NeverSessionManager` (stateless) re-checked before use |
| utoipa / tower-http / tokio | 6.0.0 / 0.7.1 / 1.54.1 | |
| schemars / uuid | 1.2.3 / 1.29.0 (`v7`) | |
| Node | 24.19 | |
| next | 16.4.5 (App Router, React 19, TS strict) | |
| @tanstack/react-query | 5.106.1 | |
| openapi-typescript / openapi-fetch | 7.13.0 / 0.17.0 | |
| tailwindcss + shadcn/ui | 4.3.4 | |
| @playwright/test | 1.64.1 | |
| PostgreSQL | 16 (`postgres:16-alpine`) | |

## 1. Layout — two services

### 1.1 `apps-microservices/agent-task-manager-backend/` (Layered / N-Tier, pure domain leaf)

```
Cargo.toml                 workspace (edition 2024), members = crates/*
Cargo.lock                 committed (repo rule: unpinned deps broke a build on 06/10)
crates/
  core/                    package atb-core — DOMAIN tier, no IO / async / sqlx
    src/lib.rs
    src/state.rs           TaskState, terminal(), a2a mapping stub TODO(phase-3)
    src/command.rs         Command enum (claim, heartbeat, report, ask, answer, release,
                           submit_for_test, expire_lease, cancel, repin, approve_spec_version, …)
    src/event.rs           DomainEvent enum (§3 event types), self-contained payloads
    src/ctx.rs             Ctx { now, caller, workflow, blockers, lease, attempt }
    src/workflow.rs        WorkflowConfig + validate()
    src/decide.rs          decide(&TaskSnapshot, &Command, &Ctx) -> Result<Vec<DomainEvent>, DomainError>
    src/apply.rs           apply(TaskSnapshot, &DomainEvent) -> TaskSnapshot
    src/error.rs           DomainError (thiserror): StaleLease, GuardFailed{guard, hint}, Forbidden, NotFound…
    src/graph.rs           would_create_cycle(edges, from, to) — pure DFS
    tests/transitions.rs   one test per §4 table row (all rows, incl. phase-2 rows)
    tests/proptest_invariants.rs  random command sequences never reach an illegal state
  server/                  package atb-server
    src/main.rs            `atb-server serve | migrate | dump-openapi | rebuild-check`
    src/config.rs          env: DATABASE_URL, DATABASE_OWNER_URL, LEASE_TTL_SECS, PREFERRED_GRACE_SECS,
                           SWEEP_INTERVAL_SECS, MAX_REPORTS_PER_MIN, NOTIFIER, CORS_ORIGINS,
                           GATEWAY_SHARED_SECRET, BIND_ADDR
    src/app.rs             router assembly, tower-http (trace, CORS, 256 KB body limit, request-id)
    src/api/               PRESENTATION tier
      error.rs             the ONE DomainError/AppError → HTTP status + {code,message,details} + MCP error mapping
      auth.rs              middleware: session cookie | bearer token | gateway identity header → Actor extension
      rest/{projects,tasks,specs,questions,actors,auth,ops}.rs   (utoipa-annotated)
      sse.rs               project stream + global stream
      mcp/{mod,tools,instructions}.rs   rmcp StreamableHttpService mounted at /mcp
      openapi.rs
    src/service/           APPLICATION tier
      command.rs           execute(cmd): idempotency lookup → BEGIN → lock tasks FOR UPDATE (id order)
                           → load snapshot+ctx → core::decide → next seq from projects row → insert events
                           → apply projections → store idempotency response → pg_notify → COMMIT
      queries.rs           board, task context (get_task), timeline, questions, presence
      claim.rs             claim-best (reference SKIP LOCKED query) / claim-by-id
      sweeper.rs           every SWEEP_INTERVAL_SECS: expire leases (one tx each), purge idempotency > 24 h
      rebuild.rs           replay events into a scratch schema and diff against live projections (AC-1.8)
      ratelimit.rs         per-actor token buckets for report / wait_for_updates (in-process)
    src/repository/        DATA tier — every fn takes `&mut PgConnection`, never the pool
      {projects,actors,specs,tasks,links,leases,attempts,questions,events,idempotency,sessions}.rs
      projector.rs         DomainEvent → projection SQL (shared by live path and rebuild)
    src/realtime/
      notifier.rs          trait Notifier (PgNotifier now; Redis TODO(phase-3))
      hub.rs               one PgListener → load events after last broadcast seq → tokio broadcast;
                           lagged subscriber → refill from events table
    tests/                 integration tests against real Postgres (sqlx::test), one file per AC
      ac_1_1_concurrent_claim.rs   ac_1_2_lease_expiry.rs   ac_1_3_stale_lease.rs
      ac_1_4_blocking_question.rs  ac_1_5_cycle.rs          ac_1_6_idempotency.rs
      ac_1_7_sse_replay.rs         ac_1_8_rebuild.rs        ac_1_9_mcp_loop.rs
      db_role_events_append_only.rs
migrations/                (see §2)
.sqlx/                     committed offline query data
openapi.json               committed, written by `atb-server dump-openapi` (frontend type source)
deploy/
  Caddyfile                single-origin ingress: /api/*, /mcp → server (flush_interval -1, no encode on SSE),
                           everything else → web
  postgres-init/01-roles.sql   creates atb_owner / atb_app roles
docker-compose.yml         postgres, server, web (build ../agent-task-manager-frontend), ingress (caddy)
Dockerfile                 multi-stage, non-root user
scripts/
  demo                     creates a project and simulates two agents working, asking, answering (via MCP)
  test-pg.sh               starts the compose postgres if needed and exports DATABASE_URL for cargo test
  smoke.sh                 docker compose up --wait, curls /healthz and the web root
  check-openapi-drift.sh   regenerates openapi.json + frontend schema and diffs
docs/DECISIONS.md  docs/PHASE-1-PLAN.md  docs/GATES-phase1.md
README.md  CLAUDE.md
```

**Dependency rule:** `api → service → {core, repository, realtime}`; `repository → core` (types only);
`core → nothing`. REST handlers and MCP tools both call the same `service::command::execute`.

### 1.2 `apps-microservices/agent-task-manager-frontend/` (feature-sliced, server-authoritative cache)

```
package.json  next.config.ts  tsconfig.json (strict)  components.json (shadcn)  playwright.config.ts
src/
  app/                               thin routes; page.tsx = Server Component → prefetch → <HydrationBoundary>
    (auth)/login/page.tsx
    projects/page.tsx
    projects/[id]/page.tsx           board
    tasks/[id]/page.tsx              task detail
    questions/page.tsx               cross-project inbox (global stream)
    agents/page.tsx                  presence
    layout.tsx  providers.tsx
  features/
    board/        api.ts (query keys + fetchers)  components/ (Column, TaskCard, LeaseCountdown, Badges)  hooks/
    task-detail/  api.ts  components/ (SpecPanel, Timeline, Attempts, AnswerForm)
    questions/    api.ts  components/
    agents/       api.ts  components/
    projects/     api.ts  components/
  realtime/
    ProjectStreamProvider.tsx        one EventSource per project, Last-Event-ID resume
    GlobalStreamProvider.tsx         /api/stream?topics=questions,reviews
    reducers.ts                      PURE (queryCache, event) → patches, one case per event type
    seq.ts                           gap / parse-error detection → invalidate board
    reducers.test.ts  seq.test.ts    vitest
  lib/api/
    schema.d.ts                      GENERATED from ../agent-task-manager-backend/openapi.json (committed)
    client.ts                        openapi-fetch; browser = same-origin /api, RSC = BACKEND_INTERNAL_URL + forwarded cookie
  lib/i18n/fr.ts                     all UI copy (French); code/logs/API stay English
  components/ui/                     shadcn/ui
  middleware.ts                      redirect to /login without session cookie
e2e/
  board-live.spec.ts                 AC-1.7 (two browser contexts, change visible < 1 s)
  pages.spec.ts                      board, task detail, questions inbox, agents render real data
Dockerfile  CLAUDE.md  README.md
```

Rules: no optimistic workflow transitions (drag shows pending until the event arrives; 409 / guard
failure snaps back with the server's reason); only `realtime/reducers.ts` writes event-driven cache
patches; never hand-write API types.

### 1.3 `apps-microservices/mcp-gateway-service/` (separate PR, your choice "extend gateway")

Per-backend opt-in flag `forward_agent_identity`. When set, the gateway injects on that backend's
calls: `X-Agent-Client-Id: <oauth client_id>` (client-credentials) or `X-Agent-User-Email` (human
token) plus `X-Agent-Gateway-Secret: <shared secret>`. The task board accepts these headers **only**
when the secret matches `GATEWAY_SHARED_SECRET`, and maps them to `actors.gateway_subject`. Direct
bearer auth keeps working (tests, demo). Exact injection point (`requestHeadersFor`) to be confirmed
by reading the gateway code before editing; gateway CLAUDE.md updated in the same commit.

## 2. Migrations (phase 1)

| # | File | Content |
|---|---|---|
| 0001 | `enums.sql` | `actor_kind`, `task_state`, `lease_kind`, `link_kind`, `question_status`, `attempt_outcome` enums |
| 0002 | `projects_actors.sql` | `projects` (workflow jsonb CHECK keys, `event_seq bigint default 0`), `actors` (+ `password_hash`, `gateway_subject` — see DECISIONS), `sessions` |
| 0003 | `specs.sql` | `specs`, `spec_versions` (PK spec_id, version) |
| 0004 | `tasks.sql` | `tasks` (+ index `(project_id, state, priority desc, created_at)`), `task_links` |
| 0005 | `leases_attempts.sql` | `leases` (task_id PK, `token_hash bytea`), `attempts` |
| 0006 | `questions.sql` | `questions` |
| 0007 | `events.sql` | `events` PK (project_id, seq), index (task_id) |
| 0008 | `idempotency.sql` | `idempotency_keys` PK (actor_id, key) |
| 0009 | `grants.sql` | `atb_app`: SELECT/INSERT on `events`, **no UPDATE/DELETE**; full DML elsewhere |

`test_runs`, `reviews` → phase 2 migrations; `reservations` → phase 3. UUIDv7 generated in Rust
(`Uuid::now_v7()`), not in SQL (Postgres 16 has no native v7).

## 3. REST + SSE endpoints (phase 1)

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/api/auth/login` · `/api/auth/logout` · GET `/api/auth/me` | human | argon2id, httpOnly SameSite=Lax cookie |
| GET/POST | `/api/projects` | any / admin | create validates workflow |
| GET | `/api/projects/{id}/board` | any | tasks + derived `blocked`, lease, attempt, open-question flag |
| GET | `/api/projects/{id}/stream` | any | SSE, `id:`=seq, Last-Event-ID replay, 15 s keep-alive |
| GET | `/api/projects/{id}/events?after=&limit=` | any | catch-up / history |
| GET | `/api/stream?topics=questions,reviews` | any | global SSE; no resume — client refetches on reconnect |
| POST | `/api/projects/{id}/specs` · `/api/specs/{id}/versions` | any | propose |
| POST | `/api/specs/{id}/versions/{v}/approve` | human | minimal in P1 (no editor UI) |
| GET | `/api/specs/{id}` | any | versions |
| POST | `/api/projects/{id}/tasks` | any | `blocked_by`, `discovered_from`, `parent_id` |
| GET / PATCH | `/api/tasks/{id}` | any / human | PATCH needs `expected_version` → 409 `version_conflict` |
| POST | `/api/tasks/{id}/links` | any | cycle check (AC-1.5) |
| POST | `/api/tasks/{id}/{claim,heartbeat,report,ask,release,submit-for-test,repin,cancel}` | per guard | humans run the same commands as agents |
| GET | `/api/tasks/{id}/timeline` | any | events for the task |
| GET | `/api/questions?project_id=&status=` · POST `/api/questions/{id}/answer` | any | open & blocking first |
| GET / POST | `/api/actors` | any / admin | presence; create agent returns token once |
| GET | `/healthz` `/readyz` `/metrics` `/api/openapi.json` | public | metrics: claims, expiries, SSE clients |

Phase 2 (`TODO(phase-2)`): reviews queue, `submit_review`, verifier endpoints, spec diff.
In phase 1 `submit_for_test` is accepted only when the project's `test_gate = none`
(it then skips straight to the review gate; with `review_gate = none` the task goes to `done`).

## 4. MCP tools (phase 1, rmcp stateless Streamable HTTP at `/mcp`)

`list_ready`, `get_task`, `claim`, `heartbeat`, `report`, `ask`, `answer`, `wait_for_updates`,
`create_task`, `propose_spec_version`, `repin`, `submit_for_test` (gates-off only), `release`.
`submit_review` → phase 2. Server `instructions` = the §7 agent protocol verbatim. Every tool:
one-line summary + compact JSON, ids included, long fields truncated; mutating tools take
`idempotency_key`. Errors: `stale_lease`, `guard_failed` (guard + fix hint), `not_found`,
`forbidden`, `rate_limited`. Actor resolved by the axum auth middleware and read in tools via
`RequestContext.extensions → http::request::Parts → Actor`.

## 5. Tests → acceptance criteria

| AC | Test | How |
|---|---|---|
| §4 rows | `core/tests/transitions.rs` | one test per table row + proptest |
| 1.1 | `ac_1_1_concurrent_claim` | 20 tokio tasks claim against 5 ready tasks; assert exactly 5 leases, 5 distinct tasks, 15 `guard_failed` |
| 1.2 | `ac_1_2_lease_expiry` | TTL 1 s, sweeper 1 s; assert `ready` + `lease.expired` with handoff note within 10 s |
| 1.3 | `ac_1_3_stale_lease` | expired token, foreign token, same actor wrong token → `stale_lease` |
| 1.4 | `ac_1_4_blocking_question` | ask blocking → `input_required`, no lease; answer → `ready`, preferred_actor = asker, other claimer refused in grace |
| 1.5 | `ac_1_5_cycle` | A→B→C, C→A rejected; self-link rejected |
| 1.6 | `ac_1_6_idempotency` | same key twice → identical body, one event set; concurrent duplicate → one applied |
| 1.7 | `ac_1_7_sse_replay` + `e2e/board-live.spec.ts` | replay after Last-Event-ID ordered, no dupes; browser board updates < 1 s |
| 1.8 | `ac_1_8_rebuild` | run a scripted workload, rebuild from events, diff projections (volatile fields excluded) |
| 1.9 | `ac_1_9_mcp_loop` | rmcp client: list_ready → claim → report → ask → answer → claim → release |
| role | `db_role_events_append_only` | as `atb_app`, UPDATE/DELETE on `events` fails (positive control: INSERT succeeds) |

## 6. Order of work

1. Context7 checks: sqlx 0.9 (PgListener, sqlx::test, offline), rmcp 3.8 (stateless server, tool macros, client for tests), axum 0.8 SSE, utoipa 6, Next 16 (RSC fetch + cookies, middleware).
2. `crates/core` + its tests (no DB needed).
3. Migrations + repository + `service::command` + AC-1.1…1.6, 1.8.
4. Realtime hub + SSE + AC-1.7 (Rust half).
5. MCP + AC-1.9 + `scripts/demo`.
6. Frontend + vitest reducers + Playwright.
7. Compose + Caddy + smoke + README + CLAUDE.md for both services.
8. Gateway PR (separate branch/commit).
9. Re-run every gate, report deviations.

## 7. Not in phase 1

Verifier, review flow, spec editor/diff UI, DAG view, time travel, reservations, Redis notifier,
Kubernetes manifests, CI workflows (`ci_services_agent_task_manager_*.yml` proposed after phase 1 is green).
