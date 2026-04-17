# Google Templates — Dynamic Secrets + Independent Instance Hosting

**Date:** 2026-04-17
**Status:** Draft
**Services:** `mcp-gateway-service` (Go, control plane), `mcp-google-templates-runner` (Python, new sidecar), `mcp-gateway-frontend` (Vue 3, UI)

## Problem

Adding a new Google-backed MCP server (Analytics, Search Console, …) today means:

1. Declare a dedicated service in `docker-compose.yml` (one container per template).
2. Download a GCP service-account JSON, drop it on the host at `./secrets/gcp-*.json`.
3. Rebuild / restart the compose stack.
4. Register the URL with the gateway via a `curl` command.

This is slow, infrastructure-heavy, and — critically — each template container can host exactly **one** credential. Running multiple GA properties, or one key per team, means declaring multiple near-identical services.

We want admins to:

- Browse a catalog of Google templates (GA, GSC — extensible later) in the gateway UI.
- Upload a service-account JSON to create a new instance.
- Have each uploaded JSON run as an **independent, supervised subprocess**. If instance D crashes, only D restarts — A, B, C keep serving.

## Goals

- One-click creation of a new Google template instance from the gateway UI.
- N-uploads-per-template, each with an isolated lifecycle (start, crash-restart, delete).
- Credentials encrypted at rest, never logged, never re-displayed.
- Zero infra change when adding an Nth instance of an existing template (no compose edit, no rebuild).
- Reuse the existing GA/GSC pattern (`mcp-proxy` + upstream stdio package) — do not re-implement protocol handling.
- Adding a *new* template later (e.g. Gmail) = seed row + one pip dep, no architectural work.

## Non-Goals

- Adding Gmail/Drive/Calendar templates now — GA and GSC only for this spec.
- Per-user instance ownership (all instances are admin-managed, gateway-wide; per-user Google OAuth2 for Sheets import is a separate existing feature).
- Runtime mutation of the template catalog (seed via migration, not UI).
- Credential export (write-only).
- P12 credential format (JSON only — existing GA service's P12→JSON converter remains available as a pre-upload utility).
- Secrets manager integration (Vault/AWS SM) — current `ENCRYPTION_KEY` + MySQL model is sufficient for project scale.
- Multi-runner horizontal scaling.
- Deprecating the existing `mcp-google-analytics-service` and `mcp-google-search-console-service` — they coexist during rollout and are removed in a later PR outside this spec.

## Architecture

Control plane (gateway) is separated from runtime (subprocess host) so the Go gateway stays lean and the Python runtime owns the `mcp-proxy` dependency chain.

```
┌─────────────────────────────────────────┐
│  mcp-gateway-service  (Go, existing)    │ control plane
│  - templates catalog (DB)               │
│  - template_instances CRUD (DB)         │
│  - AES-256-GCM credential encryption    │
│  - admin UI (via mcp-gateway-frontend)  │
│  - calls runner admin API               │
│  - auto-populates mcp_servers per       │
│    live instance (routing reuse)        │
└───────────────┬─────────────────────────┘
                │ HTTP (shared-secret auth, Leexi pattern)
                ▼
┌─────────────────────────────────────────┐
│  mcp-google-templates-runner  (Python,  │ runtime
│  new)                                   │
│  - image: python + mcp-proxy +          │
│    analytics-mcp + mcp-gsc              │
│  - supervisor per uploaded JSON         │
│  - allocates port 9001–9099 per inst    │
│  - writes JSON to tmpfs, shreds on del  │
│  - admin API (register/unregister/      │
│    reconcile/status)                    │
└───────────────┬─────────────────────────┘
                │ asyncio.subprocess
                ▼
  mcp-proxy :9001 → analytics-mcp (key A)
  mcp-proxy :9002 → analytics-mcp (key B)
  mcp-proxy :9003 → mcp-gsc       (key C)
  mcp-proxy :9004 → mcp-gsc       (key D)
```

### Why split (vs. running `mcp-proxy` inside the gateway)

Running `mcp-proxy` + `analytics-mcp` + `mcp-gsc` from the gateway image means shipping a Python runtime plus three pip packages inside a Go service. Ugly coupling, larger image, mixed runtimes in one container. The split keeps the gateway pure Go and confines all Google-specific subprocess logic to a single purpose-built image.

### Why a supervisor (vs. Docker-per-instance)

Option considered and rejected: one Docker container per uploaded JSON, gateway drives via Docker socket. Rejected because:

- Requires giving the gateway Docker-socket privileges (large security surface).
- Cold-start per instance ~5–10s (container boot) vs. ~1s (process fork).
- Scattered logs across N containers.
- The isolation gain (kernel boundary) is not justified for trusted stdio MCP servers that cannot DoS each other.

Process-level isolation via per-child asyncio supervision gives the user's stated requirement ("restart only D if D crashes") at a fraction of the complexity.

## Data Model

Two new tables in the gateway DB (MySQL, via GORM auto-migration).

### `templates` (seed data, managed via migration)

| Column | Type | Notes |
|---|---|---|
| `slug` | VARCHAR(32) PK | `ga`, `gsc` |
| `name` | VARCHAR(128) | Display name, e.g. "Google Analytics 4" |
| `description` | TEXT | UI blurb |
| `icon` | VARCHAR(512) | URL or emoji |
| `stdio_command` | VARCHAR(256) | e.g. `analytics-mcp` |
| `stdio_args` | JSON | JSON array, e.g. `[]` |
| `default_env` | JSON | Static env merged into each instance, e.g. `{"GOOGLE_APPLICATION_CREDENTIALS": "/tmp/secrets/{instance_id}.json"}` (the runner substitutes `{instance_id}` at spawn time) |
| `required_extra_env` | JSON | Schema for admin-filled env vars, e.g. `[{"key":"GOOGLE_PROJECT_ID","label":"Project ID","required":true}]` |
| `tool_prefix` | VARCHAR(64) | Populated on the auto-created `mcp_servers` row |
| `tags` | JSON | JSON array, e.g. `["analytics","google"]` |
| `is_active` | BOOL | Soft-disable |
| `created_at`, `updated_at` | DATETIME(3) | Standard |

Adding a new template = adding a seed row in a migration + adding its pip dependency to the runner image.

### `template_instances`

| Column | Type | Notes |
|---|---|---|
| `id` | CHAR(36) PK | UUID — also used as the `mcp_servers.id` |
| `template_slug` | VARCHAR(32) | FK → `templates.slug`, `ON DELETE RESTRICT` |
| `name` | VARCHAR(255) | Admin-chosen, e.g. "HelloPro prod" |
| `encrypted_credentials` | BLOB | AES-256-GCM over raw SA JSON |
| `credentials_hash` | CHAR(64) | SHA-256 of plaintext — enables diff-without-decrypt during reconcile |
| `extra_env` | JSON | Values for the template's `required_extra_env` |
| `runner_port` | INT | Assigned by runner, `NULL` until running |
| `runner_status` | ENUM(`pending`,`running`,`failed`,`stopped`) | Last state reported by runner |
| `runner_last_error` | TEXT | Populated when `failed` |
| `mcp_server_id` | CHAR(36) | FK → `mcp_servers.id`, no DB-level cascade (delete order enforced in application) |
| `created_by` | VARCHAR(255) | Admin email |
| `created_at`, `updated_at` | DATETIME(3) | Standard |

Delete flow (all steps in a single GORM transaction):

1. Gateway calls `DELETE /admin/instances/{id}` on runner (subprocess kill + tmpfs wipe). If runner is unreachable, transaction aborts — admin retries.
2. Gateway deletes the `template_instances` row.
3. Gateway deletes the `mcp_servers` row by id; the existing cascade on `mcp_servers` (scope token servers, OAuth2 client servers, tools, resources, prompts, tags) runs as usual.

DB-level cascade is deliberately not used for the `template_instances` ↔ `mcp_servers` link, so the runner-kill step cannot be silently skipped by a raw `DELETE` against `mcp_servers`.

### Runner in-memory state (no DB)

```python
class RunningInstance:
    instance_id: str
    template_slug: str
    port: int
    pid: int
    credentials_path: str           # /tmp/secrets/{instance_id}.json
    credentials_hash: str           # sha256 of the plaintext
    stdio_command: str
    stdio_args: list[str]
    env: dict[str, str]
    desired_state: str              # "running" | "stopped"
    process: asyncio.subprocess.Process
    supervisor_task: asyncio.Task
    stderr_ring: collections.deque  # last 200 lines for debug surface
    exit_count: int
    last_exit_at: float | None
    last_error: str
```

## API Surface

### Gateway (admin, behind existing JWT + `admin` role) under `/api/v1/`

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/templates` | List available templates (`is_active=true`) |
| `GET` | `/templates/{slug}` | Template detail, including `required_extra_env` schema |
| `GET` | `/template-instances` | List all instances (admin-scoped view) |
| `POST` | `/template-instances` | Create — multipart: `template_slug`, `name`, `credentials` (JSON file), `extra_env` (JSON) |
| `GET` | `/template-instances/{id}` | Detail, including `runner_status`, `runner_last_error`, and `stderr_tail` (last ~200 lines, fetched live from runner) |
| `POST` | `/template-instances/{id}/restart` | Ask runner to kill + respawn |
| `POST` | `/template-instances/{id}/rotate-credentials` | Upload new JSON, re-encrypt, re-spawn in place (same port, same `mcp_server_id`, no re-discover) |
| `DELETE` | `/template-instances/{id}` | Cascade: runner kill → delete `template_instances` row → `mcp_servers` + joins drop via FK |

Gateway → runner callbacks (admin-token only, no JWT):

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/internal/runner/sync` | Runner calls on boot — returns authoritative desired state |

`POST /template-instances` response (201):

```json
{
  "id": "7f2a...-uuid",
  "name": "HelloPro prod",
  "template_slug": "ga",
  "runner_status": "pending",
  "runner_port": null,
  "mcp_server_id": "7f2a...-uuid",
  "url": "http://mcp-google-templates-runner:9001",
  "created_at": "2026-04-17T10:00:00Z"
}
```

### Runner admin API (shared-secret, `X-Admin-Token`)

Mirrors the existing `mcp-leexi-service` `/admin/*` pattern.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/health` | Liveness |
| `GET` | `/admin/instances` | List running: `[{id, port, pid, status, uptime_s, last_error, stderr_tail}]` |
| `POST` | `/admin/instances` | Body: `{instance_id, template_slug, stdio_command, stdio_args, env, credentials_json}` → writes creds to tmpfs, allocates port, spawns. Returns `{port, pid}` |
| `DELETE` | `/admin/instances/{id}` | SIGTERM → wait 5s → SIGKILL, shred tmpfs file, release port |
| `POST` | `/admin/instances/{id}/restart` | Kill + respawn same config |
| `POST` | `/admin/reconcile` | Body: authoritative list from gateway — runner spawns missing, kills extras, restarts credential-hash mismatches |

### Configuration (env vars)

Gateway:

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_TEMPLATES_RUNNER_URL` | — | In-cluster URL of runner, e.g. `http://mcp-google-templates-runner:8590` |
| `GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN` | — | Shared secret for runner admin API |

Runner:

| Variable | Default | Description |
|---|---|---|
| `MCP_GATEWAY_URL` | — | Gateway base URL for startup sync callback |
| `MCP_GATEWAY_ADMIN_TOKEN` | — | Same shared secret |
| `RUNNER_ADMIN_TOKEN` | — | Incoming admin token on `/admin/*` (can be the same value as `MCP_GATEWAY_ADMIN_TOKEN`, but split for rotation) |
| `RUNNER_PORT` | `8590` | Admin API port |
| `RUNNER_INSTANCE_PORT_START` | `9001` | First port in the dynamic pool |
| `RUNNER_INSTANCE_PORT_END` | `9099` | Last port in the dynamic pool |

## Supervision Model

### Per-instance asyncio supervisor

```python
async def supervise(inst: RunningInstance):
    backoff = 1.0
    while inst.desired_state == "running":
        inst.process = await asyncio.create_subprocess_exec(
            "mcp-proxy",
            "--port", str(inst.port),
            "--host", "0.0.0.0",
            "--pass-environment",
            "--stateless",
            "--", inst.stdio_command, *inst.stdio_args,
            env={**os.environ, **inst.env},
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
        )
        inst.pid = inst.process.pid
        start_ts = time.monotonic()
        # stderr drain task streams lines into inst.stderr_ring
        drain_task = asyncio.create_task(drain_stderr(inst))

        exit_code = await inst.process.wait()
        drain_task.cancel()

        if inst.desired_state != "running":
            break

        inst.exit_count += 1
        inst.last_exit_at = time.monotonic()
        inst.last_error = f"exit {exit_code}; stderr tail: {tail(inst.stderr_ring)}"

        # Flapping detection: 5 exits within 10s each → give up
        if time.monotonic() - start_ts < 10.0 and inst.exit_count >= 5:
            inst.desired_state = "stopped"
            inst.runner_status = "failed"
            break

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60.0)
        if time.monotonic() - start_ts > 60.0:
            backoff = 1.0  # healthy long-run resets backoff
            inst.exit_count = 0
```

### Authoritative state split

- **Gateway is authoritative on `desired_state`** (created, deleted, rotated — the user's intent).
- **Runner is authoritative on `live_state`** (running, failed, pending — what the OS actually shows).
- Gateway polls runner every 30s and writes `runner_status` + `runner_last_error` into `template_instances`; the existing gateway health loop pings each instance URL for protocol-level health.

### Reconciliation (runner boot)

```
gw_state = GET /api/v1/internal/runner/sync       # authoritative desired
local_state = self.instances                        # empty on cold start

for inst in gw_state:
    if inst.id not in local_state:
        spawn(inst)                                 # bounded concurrency = 5
for id in local_state:
    if id not in {g.id for g in gw_state}:
        kill(id)
for id in gw_state & local_state:
    if gw_state[id].credentials_hash != local_state[id].credentials_hash:
        restart_with_new_credentials(gw_state[id])
```

### Failure modes

| Failure | Behavior |
|---|---|
| One child crashes | Runner respawns. Gateway sees brief `unhealthy → healthy`. Siblings untouched. |
| Child flapping (5 exits within 10s of start) | Runner marks instance `failed`, stops respawning, surfaces stderr tail + exit code. Admin must hit `/restart` to retry. |
| Runner dies / restarts | All children die. Runner startup sync re-fetches desired state, spawns all instances with bounded concurrency 5. Gateway shows `pending` during the gap. |
| Gateway dies / restarts | Runner children keep running. Gateway on restart reads `template_instances`, polls runner, reconciles. |
| Runner unreachable (network partition) | Gateway marks instances `unknown` via existing `mcp_servers.health_status`. No auto-kill (avoid flapping on transient blips). |
| Invalid JSON uploaded | Rejected at gateway upload time — never reaches runner. |
| Credentials revoked by Google | Subprocess alive but returns auth errors at tool-call time. No restart loop (process is fine). Admin sees tool errors → rotates credentials. |
| `extra_env` missing required key | Rejected at gateway upload time. |

### Graceful shutdown

- Runner on SIGTERM: mark all instances `stopped`, SIGTERM children, wait up to 10s, SIGKILL stragglers, shred tmpfs, exit.
- Gateway on SIGTERM: existing 10s drain covers in-flight HTTP; no new behaviour.

## Security

### At rest

- SA JSON encrypted with existing `internal/crypto` AES-256-GCM (reuses `ENCRYPTION_KEY`, same path as `auth_headers`, OAuth2 refresh tokens).
- `credentials_hash` (SHA-256 of plaintext) stored alongside — enables diff-without-decrypt.
- Never logged. `credentials` added to existing audit-log sensitive-key redaction list.

### In transit

- Gateway → runner: JSON in POST body. HTTPS if `GOOGLE_TEMPLATES_RUNNER_URL` is `https://`, else plain HTTP on the internal Docker network. `X-Admin-Token` shared secret.
- Rotate-credentials: new JSON passed as POST body; gateway updates DB transactionally after runner ack.

### In runner memory

- Written to `/tmp/secrets/{instance_id}.json` on a `tmpfs` mount: `noexec`, `nosuid`, `size=16m`. Never persisted, never swapped.
- File mode `0600`, owned by runner's non-root user.
- On instance delete: `shred -u` the file before port release.
- On runner SIGTERM: wipe `/tmp/secrets/*`.

### Upload validation (gateway, before encrypt)

Reject if any of:

- Content-Type is not `application/json` or a valid multipart file part.
- File does not parse as JSON.
- Missing or empty: `type == "service_account"`, `client_email`, `private_key`, `project_id`.
- `private_key` does not start with `-----BEGIN PRIVATE KEY-----` (catches P12 or pasted-fingerprint mistakes).
- File size > 16 KB (SA JSONs are ~2 KB; larger is suspicious).
- `client_email` ends in `@developer.gserviceaccount.com` without a `.iam.` segment (legacy format).

### Authn/authz

| Endpoint | Auth |
|---|---|
| Gateway `GET /api/v1/templates/*` | JWT, any authenticated role |
| Gateway `/api/v1/template-instances/*` (CRUD) | JWT + `admin` role |
| Gateway `/api/v1/internal/runner/sync` | `X-Admin-Token` only |
| Runner `/admin/*` | `X-Admin-Token` only |

### Command injection / SSRF surface

- Template `stdio_command` / `stdio_args` are set exclusively by migration seed rows. **No admin UI edits**. Adding a new template = code change + migration, not runtime mutation.
- `extra_env` passed as env vars via `subprocess.create_subprocess_exec(env=...)` (no shell interpolation). `shell=False`, fixed argv.

### Audit log (existing `audit_logs` infra)

| Action | Redactions |
|---|---|
| `template_instance.create` | `credentials` redacted in request body |
| `template_instance.delete` | — |
| `template_instance.rotate_credentials` | new `credentials` redacted |
| `template_instance.restart` | — |

## UI

Lives in existing `mcp-gateway-frontend` (Vue 3). New top-level tab **Templates** alongside Servers / Tokens / OAuth2 / Users.

### Screens

1. **Catalog** `/admin/templates` — lists templates (GA, GSC, future placeholders) with live instance counts. Click → template detail.
2. **Template detail** `/admin/templates/{slug}` — per-template view: header with stdio command, list of instances (cards with status badge `running` / `failed` / `pending`, uptime, SA email, port), actions per instance: **Rotate JSON**, **Restart**, **Delete**, **View logs** (for failed). Top-right: **+ Add instance**.
3. **Add instance modal** — fields: name (text), credentials (drag-drop JSON, client-side SA-shape validation), required env (rendered from `templates.required_extra_env` schema). Submit calls `POST /api/v1/template-instances`.

### UX conventions

- Instances also surface in the existing **Servers** tab with a "from template: ga" badge — they are MCP servers, so they live in both views.
- Credentials are write-only: no re-display, no download. Rotate flow uploads a fresh JSON and discards the old encrypted blob transactionally.
- **View logs** shows the runner's stderr tail for the instance (last ~200 lines from the ring buffer).
- Failed instances surface the last error prominently; no auto-retry — explicit **Restart** needed.

## Testing

### Gateway (Go, `testing` + stdlib)

Matches the existing pattern in `internal/repository/*_test.go`, `internal/authserver/*_test.go`, `internal/db/mysql_test.go`:

- `repository/template_repo_test.go` — CRUD on `templates` and `template_instances`, cascade-delete to `mcp_servers`.
- `api/template_handlers_test.go` — upload validation (valid SA JSON, bad `type`, missing `private_key`, oversized, wrong MIME), 403 for non-admin, encrypted-blob round-trip.
- `api/runner_client_test.go` — gateway's runner client against `httptest.Server` mock: spawn, kill, reconcile, timeout, admin-token mismatch.
- DB auto-migration of new tables verified on real MySQL via testcontainer if available.

### Runner (Python, `pytest` + `pytest-asyncio`)

- `tests/test_supervisor.py` — spawn/kill lifecycle using a dummy `sleep 3600` subprocess; crash-respawn using `sh -c 'exit 1'`; flapping detection after 5 fast exits; backoff timing.
- `tests/test_reconcile.py` — cold-start reconcile spawning N instances against mocked gateway; extra-local cleanup; credentials-hash diff triggering restart.
- `tests/test_admin_api.py` — 401 on missing/wrong `X-Admin-Token`, port allocation from pool, instance CRUD, stderr-tail endpoint.
- `tests/test_credentials.py` — tmpfs write/wipe, file mode 0600, `shred` on delete.
- CI smoke: start runner container, spawn one instance with a fake `stdio_command=cat`, verify `GET /admin/instances` reports it running, kill, verify cleanup.

### Frontend (Vue, existing Vitest)

Component tests for `TemplatesView`, `TemplateInstanceCard`, `AddInstanceModal` — JSON client-side validation, drag-drop, required-env rendering from template schema.

## Risks / Open Items

- **`mcp-proxy` cold start ~2s per instance.** Acceptable for single uploads. Painful if the runner restarts with 20+ instances. Mitigation: `asyncio` reconcile with bounded concurrency = 5.
- **Port range sizing.** 9001–9099 = 99 instances per runner. If HelloPro outgrows this, widen the range (config already supports it) or migrate to unix sockets (breaking contract change between runner and gateway).
- **Upstream package breakage.** `analytics-mcp` and `mcp-gsc` are third-party. Pin versions in runner's `requirements.txt`. Upgrade only via explicit PR with a smoke-test in staging.
- **`mcp-gsc` local patch.** The existing GSC service ships a patched `mcp_gsc/__init__.py` fixing two bugs. The new runner must carry the same patch until fixed upstream — copy the patch into the runner image.
- **Runner is a single point of failure.** Restart ≈ 2–10 seconds of instance downtime (spawn pool cold start). Multi-runner scheduling is out of scope; a single replica is sufficient for current scale.
