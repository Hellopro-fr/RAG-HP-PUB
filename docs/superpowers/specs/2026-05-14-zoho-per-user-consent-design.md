# Per-User Zoho Tools on OAuth2 Consent Screen

**Date:** 2026-05-14
**Service:** `mcp-gateway-service` + `mcp-gateway-frontend`
**Status:** Design

## Problem

The OAuth2 `/authorize` consent screen currently shows Zoho tools using a
fall-back chain: per-user `zoho_imports` row → admin `zoho_imports` row →
cached registry tools. Effect: a non-admin user who has no per-user Zoho row
still sees the admin's Zoho tools as if they were their own. This is wrong
both for usability (the user cannot call those tools against the admin's
upstream) and for privacy (admin catalog leaks into every connected user's
consent screen).

## Goal

Render Zoho tools on the consent screen strictly per viewer identity:

| Viewer | Zoho row | Consent rendering for Zoho-tagged server |
|---|---|---|
| Admin (`gateway_users.role = "admin"`) | admin row present | "Configurés" section — admin tools |
| Admin | admin row missing | "Non configurés" section — docs link |
| Non-admin | user row present | "Configurés" section — user tools |
| Non-admin | user row missing | "Non configurés" section — docs link |
| Anonymous / client_credentials | n/a | unchanged — consent screen not reached |

Non-admin viewers MUST NOT see the admin Zoho catalog anymore. When a viewer
has no configured row, the Zoho server is moved into a new visual section
"Serveurs non configurés" containing a CTA link to
`{GATEWAY_PUBLIC_URL}/docs/zohocrm` (existing Vue documentation route in
`mcp-gateway-frontend`), opened with `target="_blank"`.

## Non-Goals

- The `/docs/zohocrm` Vue page itself — already exists in
  `mcp-gateway-frontend`. No frontend doc-page work.
- Runtime MCP tools-list path (`handleToolsList`). Only the consent UI is
  changed by this spec. The runtime live-fetch keeps its current semantics.
- Backwards compatibility for `ZohoUserCatalog.ToolsForEmail` callers — only
  one production caller exists and is replaced atomically.

## Architecture

```
GET /authorize
  ↓
renderConsent(email)
  ↓
gateway.FetchZohoStateForUser(ctx, email)        ← replaces FetchZohoToolsForUser
  ↓
ZohoUserCatalog.StateForEmail(ctx, email)        ← replaces ToolsForEmail
  ↓
zohoCatalogAdapter (app layer)
  ↓ users.GetByEmail(email) → role
  ↓ role == "admin"  → imports.GetAdmin()
  ↓ role != "admin"  → imports.FindUserImportByEmail(email)
  ↓ row != nil       → imports.ListTools(row.ID)
  ← ZohoCatalogState{Tools, Configured}
  ↓
renderConsent partitions backends:
  - Zoho server with Configured == false → unconfigured slice
  - everything else (including Configured == true Zoho)  → configured slice
template renders two sections; unconfigured shows the docs link.
```

### Types

```go
// internal/gateway/types_zoho.go  (or extend gateway.go)
type ZohoServerState struct {
    Tools      []mcp.Tool
    Configured bool   // row exists AND has at least one tool
}

type ZohoCatalogState struct {
    Tools      []mcp.Tool
    Configured bool
}
```

### Interface change (`internal/gateway/gateway.go`)

```go
type ZohoUserCatalog interface {
    // Replaces ToolsForEmail. Caller (FetchZohoStateForUser) uses the
    // Configured flag to decide whether to keep the server in the main
    // section or move it to "Non configurés".
    StateForEmail(ctx context.Context, email string) ZohoCatalogState
}

func (g *Gateway) FetchZohoStateForUser(
    ctx context.Context, email string,
) map[string]ZohoServerState {
    // ... same backend iteration as today,
    //     populates Tools + Configured per Zoho-tagged server.
}
```

### Adapter (`internal/app/zoho_catalog_adapter.go`)

```go
type zohoCatalogAdapter struct {
    imports *repository.ZohoImportRepo
    users   *repository.UserRepo
}

func (a *zohoCatalogAdapter) StateForEmail(
    ctx context.Context, email string,
) ZohoCatalogState {
    if a == nil || a.imports == nil || email == "" {
        return ZohoCatalogState{}
    }
    user, _ := a.users.GetByEmail(email)
    isAdmin := user != nil && user.Role == "admin"

    var row *db.ZohoImport
    if isAdmin {
        row, _ = a.imports.GetAdmin()
    } else {
        row, _ = a.imports.FindUserImportByEmail(email)
    }
    if row == nil {
        return ZohoCatalogState{Configured: false}
    }
    tools, err := a.imports.ListTools(row.ID)
    if err != nil || len(tools) == 0 {
        return ZohoCatalogState{Configured: false}
    }
    return ZohoCatalogState{Tools: convert(tools), Configured: true}
}
```

Key semantic change: **no admin fallback for non-admin viewers**.

### Consent rendering (`internal/authserver/authorize.go`)

`renderConsent` partitions backends into two slices:

```go
type consentTemplateData struct {
    ClientName            string
    // … existing fields …
    Servers               []serverEntry   // configured
    UnconfiguredServers   []serverEntry   // Zoho when state.Configured == false
    DocsURL               string          // = GATEWAY_PUBLIC_URL + "/docs/zohocrm"
    PreConfigured         bool
}
```

Partition rule applied inside the existing loop:

```go
for _, srv := range servers {
    if zohoIDs[srv.ID] {
        st := zohoState[srv.ID]  // ZohoServerState
        if !st.Configured {
            unconfigured = append(unconfigured, serverEntry{
                ID:        srv.ID,
                Name:      srv.Name,
                ToolCount: 0,
            })
            continue
        }
        source := toServerTools(st.Tools)
        // … existing tool-build path …
    }
    configured = append(configured, entry)
}
```

`hasPreConfiguredScope` branch follows the same partition (only adds Zoho
admin-assigned scope if state.Configured; otherwise treat as unconfigured).

### Template (`internal/authserver/templates/consent.html`)

After the existing `{{range .Servers}}` block, add:

```html
{{if .UnconfiguredServers}}
<p class="text-xs text-gray-500 mt-4 mb-2">Serveurs non configurés :</p>
<div class="border border-amber-200 rounded-lg bg-amber-50">
  {{range .UnconfiguredServers}}
  <div class="flex items-center justify-between px-3 py-2 border-b border-amber-100 last:border-b-0">
    <div class="flex items-center gap-2">
      <svg class="w-4 h-4 text-amber-500 shrink-0" …></svg>
      <span class="text-sm font-medium text-gray-800">{{.Name}}</span>
      <span class="text-xs text-amber-700 px-1.5 py-0.5 rounded bg-amber-100">Non configuré</span>
    </div>
    <a href="{{$.DocsURL}}" target="_blank" rel="noopener noreferrer"
       class="text-xs font-medium text-brand-600 hover:underline">
      Voir documentation →
    </a>
  </div>
  {{end}}
</div>
{{end}}
```

### JSON API (`internal/authserver/authorize_api.go`)

Extend `authorizeServerDTO`:

```go
type authorizeServerDTO struct {
    ID         string             `json:"id"`
    Name       string             `json:"name"`
    Tools      []authorizeToolDTO `json:"tools"`
    Configured bool               `json:"configured"`
    DocsURL    string             `json:"docs_url,omitempty"`  // populated when Configured == false
    // … existing fields …
}
```

Response splitting is done client-side by `AuthorizeView.vue`
(filter `configured === false` into a separate section). One round-trip,
same endpoint.

### Frontend (`AuthorizeView.vue`)

Two sections:

1. "Serveurs disponibles" — `servers.filter(s => s.configured !== false)`,
   existing checkbox + tool picker.
2. "Serveurs non configurés" — `servers.filter(s => s.configured === false)`,
   read-only row with name + "Non configuré" badge + link button
   (`<a :href="server.docs_url" target="_blank" rel="noopener noreferrer">`).

The second section is hidden when its filter result is empty.

### Config

| Variable | Source | Use |
|---|---|---|
| `GATEWAY_PUBLIC_URL` | existing env (already used for OAuth2 issuer) | base for `DocsURL = $GATEWAY_PUBLIC_URL + "/docs/zohocrm"` |

The docs URL is materialized at request time in `renderConsent` /
`buildServerList` from `s.config.PublicURL` (or equivalent) to avoid stale
embeds.

## Tests

| File | Cases |
|---|---|
| `internal/app/zoho_catalog_adapter_test.go` | (1) admin role + admin row + tools → Configured=true, tools returned. (2) admin role + admin row missing → Configured=false. (3) non-admin + user row + tools → Configured=true, user tools. (4) non-admin + no user row → Configured=false **and admin row not consulted**. (5) empty email → empty state. (6) row exists but ListTools err → Configured=false. (7) row exists but tools empty → Configured=false. |
| `internal/authserver/consent_test.go` | (1) non-admin without user row → Zoho server appears in UnconfiguredServers only. (2) non-admin with user row → Zoho server appears in Servers only with user tools. (3) admin with admin row → Zoho in Servers. (4) admin without admin row → Zoho in UnconfiguredServers. (5) Non-Zoho servers always go to Servers regardless of email. |
| `internal/authserver/authorize_api_test.go` | JSON response: each server has `configured` bool; unconfigured server has non-empty `docs_url`; configured server has empty `docs_url`. |
| `internal/gateway/gateway_test.go` | `FetchZohoStateForUser` returns one entry per Zoho-tagged backend with Configured flag matching adapter state; non-Zoho backends absent from map. |

Failure modes covered:
- `users.GetByEmail` returning ErrNotFound → treat as non-admin (existing default).
- `users.GetByEmail` returning a transient DB error → log + treat as non-admin (fail safe: never grant admin tools on lookup error).

## Impact / Blast Radius

| Path | Change | Downstream |
|---|---|---|
| `internal/gateway/gateway.go` | replace interface + method | `internal/app/app.go` wiring; `internal/authserver/{authorize.go, authorize_api.go}` callers |
| `internal/app/zoho_catalog_adapter.go` | add UserRepo dep, change return type | unit tests only |
| `internal/app/app.go` | wire UserRepo into adapter | n/a |
| `internal/authserver/templates/consent.html` | new section + DocsURL | HTML render only |
| `mcp-gateway-frontend/src/views/AuthorizeView.vue` | second list rendering | none (DTO additive) |

No proto changes. No DB schema changes. No new env vars (reuses
`GATEWAY_PUBLIC_URL`). One MCP gateway service restart required.

## Rollout

1. Land backend change (adapter + gateway + authserver + template + JSON DTO).
2. Land frontend change (AuthorizeView.vue) — additive consumer of the new
   DTO field. Backend ships first.
3. Manual smoke on staging:
   - Non-admin user without `zoho_imports` row → consent shows Zoho under
     "Non configurés" with the docs link.
   - Same user adds a row via `/api/v1/zoho-imports` → consent shows their
     Zoho tools.
   - Admin sees admin tools.
   - Admin without admin row → Zoho appears under "Non configurés".

## Open Questions

None — all clarifications resolved in the brainstorming pass.
