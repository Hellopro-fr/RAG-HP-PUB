# Zoho Auto-Filter on Imported Servers + Admin Fallback

**Date:** 2026-05-12
**Scope:** `apps-microservices/mcp-gateway-service/`, `apps-microservices/mcp-gateway-frontend/`
**Status:** Draft

## Problem

The gateway already enforces ownership filters for Leexi (`X-Leexi-Allowed-Participants`), Ringover (`X-Ringover-Allowed-User-IDs`), and BDD (`X-BDD-Allowed-Tables`). Zoho is flagged as a "future" backend in `CLAUDE.md` § Server-level full-access grants, but no filter currently fires when calls hit a `ToolPrefix=='zoho'` backend.

Operationally, sheet-imported Zoho servers are one-per-user instances — each row stamped with the owner's email in `mcp_servers.created_by` (just shipped). When any OAuth2 client (or scope token) calls one of these per-user instances, the gateway must scope the outbound call to the named owner. Manual Zoho servers (added outside the templates flow) need a separate admin-configurable filter.

## Goal

Add a Zoho filter step to `requestHeadersFor` with this precedence:

1. **Step 0 — server-authorization grant**: unchanged. Bypass on match.
2. **Step 1 — auto-filter (new)**: when `backend.ToolPrefix=='zoho'` AND `backend.TemplateSlug != ''` AND `backend.CreatedBy != ''`, inject `X-Zoho-Allowed-User: <backend.CreatedBy>`. End-user identity is not consulted.
3. **Step 2 — admin filter (new)**: any other Zoho backend resolves the active scope-token / OAuth2-client's `ZohoFilterMode` and injects the corresponding header (or nothing if mode is `none`).

## Non-goals

- No Zoho admin API integration. No email → Zoho-user-ID resolution. The header value is always a plain email string (or CSV of emails).
- No `mcp-zoho-service` changes in this spec. The gateway emits `X-Zoho-Allowed-User`; the Zoho MCP backend must consume it. Until the backend lands the matching filter, the header is informational.
- No retroactive backfill on existing rows.
- No new permission gates. Existing token / OAuth2-client server allow-lists already control which clients can call which servers.
- No UI change to the `/templates` import wizard (the just-shipped `created_by` picker is sufficient).
- No deprecation of any existing Leexi/Ringover/BDD pathway.

## Affected Surfaces

| Layer | Touched |
|---|---|
| DB schema | 4 new columns total across `scope_tokens` and `oauth2_clients` (GORM auto-migrate handles ALTER) |
| Gateway runtime | `scoped_gateway.go` — new `injectZohoHeader` method + case in switch |
| Repos | implicit (GORM serialises new columns automatically) |
| API DTOs | new `ZohoFilterDTO` shape on token + OAuth2-client request/response |
| Frontend | new `ZohoFilterPanel.vue`, pluggable into `TokenFormView` + `ClientFormView` |
| Tests | extend `scoped_gateway_test.go` and the form-level Vue specs |
| Docs | `apps-microservices/mcp-gateway-service/CLAUDE.md` — update Server-level full-access paragraph + add a Zoho filter conventions bullet |

## Design

### Schema

Mirror the Leexi schema on both tables (column names and types):

```go
// On ScopeToken and OAuth2Client:
ZohoFilterMode    string          `gorm:"type:varchar(16);not null;default:'none'" json:"zoho_filter_mode"`
ZohoAllowedEmails json.RawMessage `gorm:"type:json"                                  json:"zoho_allowed_emails,omitempty"`
```

Modes (validated server-side at create/update time):

- `none` (default) — no header injected; backend treats the call as unrestricted.
- `users` — `ZohoAllowedEmails` holds a non-empty JSON array of email strings.
- `creator` — single email resolved from `token.CreatedBy` or `oauth2_client.CreatedBy`. Snapshot at row write time; not re-resolved on every request.

`ZohoAllowedEmails` is null/empty for `none` and `creator` modes.

### Header injection contract

| Step 1 fires when | Header value |
|---|---|
| `backend.ToolPrefix=='zoho'` AND `backend.TemplateSlug != ''` AND `backend.CreatedBy != ''` | `backend.CreatedBy` (one email) |

| Step 2 fires when | Header value |
|---|---|
| Step 1 conditions not met AND `backend.ToolPrefix=='zoho'` | depends on mode (see below) |

```
mode=='none'                                    → no header (caller backend = unrestricted)
mode=='users' AND emails non-empty              → strings.Join(emails, ",")
mode=='users' AND emails empty                  → "deny-all@hellopro.fr.deny" (sentinel)
mode=='creator' AND token.CreatedBy non-empty   → token.CreatedBy
mode=='creator' AND token.CreatedBy empty       → "deny-all@hellopro.fr.deny"
```

The deny sentinel mirrors the Leexi `"00000000-0000-0000-0000-000000000000"` pattern — a never-matching value the backend can detect and treat as "deny all".

### Context plumbing

In `internal/scopetoken/cache.go` (alongside `LeexiFilterFromContext`):

```go
type ZohoFilter struct {
    Mode          string
    AllowedEmails []string
    // CreatedBy is the owning user's email captured at scope-token / OAuth2-client
    // create time. Used only for Mode=="creator".
    CreatedBy string
}

func ZohoFilterFromContext(ctx context.Context) (*ZohoFilter, bool)
func ContextWithZohoFilter(ctx context.Context, f *ZohoFilter) context.Context
```

Build the `ZohoFilter` during scope-cache resolution alongside the Leexi/Ringover/BDD filters. JSON-unmarshal `ZohoAllowedEmails` once into `[]string`, cache for the 60-second TTL.

### Gateway change

In `internal/gateway/scoped_gateway.go`:

```go
const (
    zohoToolPrefix         = "zoho"
    ZohoAllowedUserHeader  = "X-Zoho-Allowed-User"
    zohoDenySentinel       = "deny-all@hellopro.fr.deny"
)

// requestHeadersFor: add the new case in the existing switch.
switch backend.ToolPrefix {
case leexiToolPrefix:
    sg.injectLeexiHeader(ctx, headers)
case ringoverToolPrefix:
    sg.injectRingoverHeader(ctx, headers)
case zohoToolPrefix:
    sg.injectZohoHeader(ctx, headers, backend)
case bddToolPrefix:
    sg.injectBDDHeader(ctx, headers)
}

func (sg *ScopedGateway) injectZohoHeader(ctx context.Context, headers map[string]string, backend *BackendServer) {
    // Step 1 — auto-filter on imported Zoho servers.
    if backend.TemplateSlug != "" && backend.CreatedBy != "" {
        headers[ZohoAllowedUserHeader] = backend.CreatedBy
        return
    }

    // Step 2 — admin-configured filter.
    filter, ok := scopetoken.ZohoFilterFromContext(ctx)
    if !ok || filter == nil || filter.Mode == "none" {
        return
    }
    switch filter.Mode {
    case "users":
        if len(filter.AllowedEmails) == 0 {
            headers[ZohoAllowedUserHeader] = zohoDenySentinel
            return
        }
        headers[ZohoAllowedUserHeader] = strings.Join(filter.AllowedEmails, ",")
    case "creator":
        if filter.CreatedBy == "" {
            headers[ZohoAllowedUserHeader] = zohoDenySentinel
            return
        }
        headers[ZohoAllowedUserHeader] = filter.CreatedBy
    }
}
```

`BackendServer` (the in-memory registry shape) must expose `TemplateSlug` and `CreatedBy`. Add the two fields to the registry struct if absent and populate from `mcp_servers` at `LoadFromDB` time.

### API DTOs

`internal/api/token_dto.go` and `oauth2_dto.go`: add an optional `ZohoFilter` field on both create and update request DTOs, plus on the response DTO.

```go
type ZohoFilterDTO struct {
    Mode          string   `json:"mode"`                      // "none" | "users" | "creator"
    AllowedEmails []string `json:"allowed_emails,omitempty"`  // required when mode=="users"
}
```

Validation:

- `mode` must be one of `none|users|creator`; default `none`.
- `users` mode requires `AllowedEmails` non-empty; emails trimmed; duplicates removed.
- `creator` mode requires the parent row's `created_by` to be non-empty (otherwise the create/update fails with 400 — same constraint as Leexi).

### Frontend

Component `src/components/tokens/ZohoFilterPanel.vue` modelled on `LeexiFilterPanel.vue`:

- Mounted only when at least one of the selected backends has `tool_prefix == 'zoho'`.
- Radio for mode (`none` / `users` / `creator`).
- When `users`: editable email list (chip input + add/remove).
- When `creator`: helper text "Le filtre sera lié au créateur du token: `{{ createdBy }}`".
- Emits `update:modelValue` with `{ mode, allowed_emails }`.
- Hidden / disabled when no Zoho backend in scope (same UX as `LeexiFilterPanel`).

Plug it into `TokenFormView` and `ClientFormView` directly under the existing `RingoverFilterPanel`.

### Validation rules

| Condition | Behavior |
|---|---|
| Backend not Zoho | Unchanged. Existing Leexi/Ringover/BDD/auto paths fire normally. |
| Server-auth grant matches | Step 0 bypass — no Zoho header injected. |
| Imported Zoho server (`template_slug != '' && created_by != ''`) | Step 1 — inject created_by as the single email. |
| Imported Zoho server, `created_by == ''` | Step 2 (admin filter). |
| Manual Zoho server (`template_slug == ''`) | Step 2. |
| Step 2, mode `none` | No header. |
| Step 2, mode `users`, non-empty list | CSV emails. |
| Step 2, mode `users`, empty list | Deny sentinel. |
| Step 2, mode `creator`, token/client.created_by non-empty | Single email. |
| Step 2, mode `creator`, token/client.created_by empty | Deny sentinel. |
| `client_credentials` grant (no end-user in ctx) | Server-auth Step 0 cannot match; Step 1/2 unchanged. |

### Tests

Backend unit (`internal/gateway/scoped_gateway_test.go`):

1. `ToolPrefix=='zoho'` + `template_slug='ga'` + `created_by='alice@hp.fr'` → `X-Zoho-Allowed-User: alice@hp.fr` (Step 1).
2. `ToolPrefix=='zoho'` + `template_slug=''` + `ZohoFilter{Mode:"users", Emails:["bob@hp.fr","carol@hp.fr"]}` → `X-Zoho-Allowed-User: bob@hp.fr,carol@hp.fr` (Step 2).
3. `ToolPrefix=='zoho'` + `template_slug=''` + `Mode=="none"` → no `X-Zoho-Allowed-User` header.
4. `ToolPrefix=='zoho'` + `Mode=="users"` + empty list → header == deny sentinel.
5. `ToolPrefix=='zoho'` + `Mode=="creator"` + `CreatedBy='dave@hp.fr'` → `X-Zoho-Allowed-User: dave@hp.fr`.
6. `ToolPrefix=='zoho'` + `Mode=="creator"` + empty CreatedBy → deny sentinel.
7. Server-auth grant on Zoho server → bypass; no `X-Zoho-Allowed-User` header.
8. Imported Zoho server + `created_by=''` → falls back to admin Step 2.
9. `ToolPrefix=='leexi'` + Zoho filter set on token → Leexi header injected, no Zoho header.
10. `ToolPrefix=='zoho'` + Leexi filter set on token → Zoho header per Step 1/2; no Leexi header.

Repo/handler tests: create token + OAuth2 client carrying a `zoho_filter` payload; read back; verify `none`/`users`/`creator` validation 400s.

Frontend specs: `ZohoFilterPanel.vue` mount/unmount based on selected backends; payload shape on submit.

## Rollout

- Single PR, branch `features/zoho-auto-filter` (or piggyback on `features/poc`).
- GORM auto-migrate handles the ALTER on `scope_tokens` + `oauth2_clients`. No data migration.
- Backward-compatible: existing tokens/clients default `ZohoFilterMode='none'` → no header → identical to today's behaviour.
- Manual smoke: import a Zoho template instance via `/templates`, observe `X-Zoho-Allowed-User: <email>` on the outbound MCP call (gateway debug log).

## Impact

| File | Change |
|---|---|
| `internal/db/models.go` | 4 new fields on 2 structs |
| `internal/gateway/scoped_gateway.go` | 1 new method, 1 new switch case, 3 new consts |
| `internal/gateway/registry.go` | add `TemplateSlug` + `CreatedBy` to `BackendServer`, populate at load |
| `internal/scopetoken/cache.go` | new `ZohoFilter` struct + ctx helpers, populate in scope resolution |
| `internal/api/token_dto.go` | new `ZohoFilterDTO`, wire in token request/response |
| `internal/api/oauth2_dto.go` | same |
| `internal/api/token_handlers.go` | validate mode + emails, pipe to DB struct |
| `internal/api/oauth2_handlers.go` | same |
| `internal/api/scope_resolver_*.go` (or wherever filters are resolved into ctx) | pull `ZohoFilter` from token/client and stash on ctx |
| `internal/gateway/scoped_gateway_test.go` | 10 new cases |
| `src/types/tokens.ts` + `src/types/oauth2.ts` | add `zoho_filter` shape |
| `src/api/tokens.ts`, `oauth2.ts` | pass-through |
| `src/components/tokens/ZohoFilterPanel.vue` | new, mirrors `LeexiFilterPanel.vue` |
| `src/views/TokenFormView.vue`, `ClientFormView.vue` | mount the panel under RingoverFilterPanel |
| `apps-microservices/mcp-gateway-service/CLAUDE.md` | refresh the Server-level full-access paragraph; add a Zoho filter convention bullet |

## Risks

- `mcp-zoho-service` does not yet enforce `X-Zoho-Allowed-User`. Header is informational until the backend ships the matching filter. Acceptable — gateway side is deployable first; backend can land its filter independently in a follow-up PR.
- `creator` mode snapshots `created_by` at row write. If a user is removed from the org, the stale email keeps being sent. Same as Leexi/Ringover today — accepted pattern. Mitigation: admin re-edits the token/client when ownership changes.
- Step 1 ignores end-user identity. An OAuth2 client whose allow-list contains alice's imported Zoho server will forward calls as alice, regardless of who connected. This is intentional — per-user-instance servers are owned by `created_by` at the server level. Per-end-user gating remains the responsibility of the existing scope-token / OAuth2-client server allow-list.
