# Zoho Auto-Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject `X-Zoho-Allowed-User` on outbound MCP calls to Zoho backends — server's `created_by` for imported Zoho servers, admin-configured per-token / per-OAuth2-client allow-list otherwise.

**Architecture:** Mirror the existing Leexi/Ringover filter pipeline. Two new DB columns on each of `scope_tokens` + `oauth2_clients`. New context key + struct. New `injectZohoHeader` method + switch case in `scoped_gateway.go`. New `ZohoFilterPanel.vue` mirroring `LeexiFilterPanel.vue`. No Zoho admin API, no email→ID resolution — header carries email strings.

**Tech Stack:** Go 1.24 (net/http, GORM auto-migrate, no third-party router), Vue 3 + TypeScript + Vite + PrimeVue.

**Spec:** `docs/superpowers/specs/2026-05-12-zoho-auto-filter-design.md`.

---

## File Structure

### Files to modify

| File | Responsibility | Change |
|---|---|---|
| `apps-microservices/mcp-gateway-service/internal/db/models.go` | GORM models | Add `ZohoFilterMode` + `ZohoAllowedEmails` on `ScopeToken` and `OAuth2Client` |
| `apps-microservices/mcp-gateway-service/internal/gateway/registry.go` | In-memory backend registry | Add `TemplateSlug` + `CreatedBy` on `BackendServer`, populate at load |
| `apps-microservices/mcp-gateway-service/internal/scopetoken/middleware.go` | Scope context plumbing | Add `ZohoFilterContextKey`, `ZohoFilterContext`, `ZohoFilterFromContext` |
| `apps-microservices/mcp-gateway-service/internal/scopetoken/cache.go` | Scope-token cache | Add `ZohoFilterMode` + `ZohoAllowedEmails` fields on `CachedToken` |
| `apps-microservices/mcp-gateway-service/internal/oauth2/cache.go` | OAuth2-client cache | Add same fields on `CachedClient` |
| `apps-microservices/mcp-gateway-service/internal/scopetoken/middleware.go` (resolution block) | Token-path cache-miss | Decode persisted Zoho filter into `CachedToken` + stash on ctx |
| `apps-microservices/mcp-gateway-service/internal/oauth2/middleware.go` (resolution block) | OAuth2-path cache-miss | Decode persisted Zoho filter into `CachedClient` + stash on ctx |
| `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go` | Header injector | Add `zohoToolPrefix`, header const, deny sentinel, `injectZohoHeader`, switch case |
| `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_test.go` | Unit tests | 10 new cases covering Step 1 / Step 2 / bypass |
| `apps-microservices/mcp-gateway-service/internal/api/token_dto.go` | Token DTOs | Add `ZohoFilterDTO`, mode constants, wire into Create/Update/Response |
| `apps-microservices/mcp-gateway-service/internal/api/oauth2_dto.go` | OAuth2-client DTOs | Same |
| `apps-microservices/mcp-gateway-service/internal/api/token_handlers.go` | Token CRUD | Validate `zoho_filter`, pipe into DB struct |
| `apps-microservices/mcp-gateway-service/internal/api/oauth2_handlers.go` | OAuth2-client CRUD | Same |
| `apps-microservices/mcp-gateway-frontend/src/types/server.ts` (or tokens.ts) | TS types | Add `ZohoFilter` shape + plug into existing `ScopeToken` and `OAuth2Client` types |
| `apps-microservices/mcp-gateway-frontend/src/components/tokens/ZohoFilterPanel.vue` | New component | Mirror `LeexiFilterPanel.vue` |
| `apps-microservices/mcp-gateway-frontend/src/views/TokenFormView.vue` | Token form | Mount the panel under `RingoverFilterPanel` |
| `apps-microservices/mcp-gateway-frontend/src/views/ClientFormView.vue` | OAuth2-client form | Same |
| `apps-microservices/mcp-gateway-service/CLAUDE.md` | Service docs | Update server-auth paragraph; add Zoho filter convention bullet |

### Files unchanged

- No Zoho admin API. No `mcp-zoho-service` repo touched.
- No proto changes.
- No router changes (uses existing token / oauth2_clients endpoints).

---

## Conventions

- **Backend Go**: `go test ./internal/...` and `go build ./...` from `apps-microservices/mcp-gateway-service`. The persistent gateway-go container at `/work` is the user's preferred test runner; if unavailable, run `go` directly.
- **Frontend**: `npm run type-check` and `npm run build` from `apps-microservices/mcp-gateway-frontend`.
- **Commits**: Conventional Commits, bilingual (EN + FR per `.claude/rules/commit-messages.md`), subject < 72 chars.

---

## Task 1: DB schema — add Zoho filter columns to ScopeToken + OAuth2Client

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/db/models.go`

GORM auto-migrate handles the ALTER on first boot. No data migration needed (defaults are safe).

- [ ] **Step 1: Edit `ScopeToken`**

In `apps-microservices/mcp-gateway-service/internal/db/models.go`, locate the `ScopeToken` struct. After the `RingoverAllowedTeamIDs` field (around line 235), insert:

```go
	// Zoho ownership scope — see ZohoFilterMode constants in api/token_dto.go.
	// "users":   ZohoAllowedEmails is authoritative (JSON array of email strings).
	// "creator": resolved single email from the token's CreatedBy at write time.
	// "none":    no filter (default).
	ZohoFilterMode    string          `gorm:"type:varchar(16);not null;default:'none'" json:"zoho_filter_mode"`
	ZohoAllowedEmails json.RawMessage `gorm:"type:json" json:"zoho_allowed_emails,omitempty"`
```

- [ ] **Step 2: Edit `OAuth2Client`**

In the same file, locate the `OAuth2Client` struct. After the `RingoverAllowedTeamIDs` field (around line 293), insert:

```go
	// Zoho ownership scope — same semantics as ScopeToken.ZohoFilterMode.
	ZohoFilterMode    string          `gorm:"type:varchar(16);not null;default:'none'" json:"zoho_filter_mode"`
	ZohoAllowedEmails json.RawMessage `gorm:"type:json" json:"zoho_allowed_emails,omitempty"`
```

- [ ] **Step 3: Build**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go build ./...
```

Expected: success (no output).

- [ ] **Step 4: Run all tests**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/... -count=1
```

Expected: PASS (the schema add is purely additive; nothing should break).

- [ ] **Step 5: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/internal/db/models.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): add Zoho filter columns to scope tokens + oauth2 clients

ZohoFilterMode (varchar(16) default 'none') and ZohoAllowedEmails
(json) on both scope_tokens and oauth2_clients. Schema-only; runtime
injection lands in a follow-up commit.

EN: Ajoute les colonnes du filtre Zoho sur les tokens de scope et
clients OAuth2.
EOF
)"
```

---

## Task 2: Registry — expose TemplateSlug + CreatedBy on BackendServer

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/registry.go`

The header injector reads `backend.TemplateSlug` and `backend.CreatedBy` (Step 1 condition). The current `BackendServer` shape does not expose them, so we must add them to the registry struct and populate them from the DB model at load.

- [ ] **Step 1: Inspect the current `BackendServer` shape**

Open `apps-microservices/mcp-gateway-service/internal/gateway/registry.go`. Locate the `BackendServer` struct (around line 10). Note the existing fields and the function that populates a registry entry from `db.MCPServer` (search for `MCPServer` references in the same file).

- [ ] **Step 2: Add the two fields**

In the `BackendServer` struct, after the existing `ToolPrefix` field, insert:

```go
	// TemplateSlug echoes mcp_servers.template_slug. Non-empty means this
	// backend was created via the /templates catalog (stdio instance or
	// http_batch sheet import). Read by the Zoho header injector to decide
	// whether to fire the auto-filter Step 1 path.
	TemplateSlug string

	// CreatedBy echoes mcp_servers.created_by. Used by the Zoho header
	// injector to populate X-Zoho-Allowed-User on imported Zoho backends.
	CreatedBy string
```

- [ ] **Step 3: Populate at load**

In the same file, locate every site that builds a `BackendServer` value from a `db.MCPServer` (search for `Name:` / `URL:` / `ToolPrefix:` together). For each such site, add:

```go
		TemplateSlug: row.TemplateSlug,
		CreatedBy:    row.CreatedBy,
```

(Field name `row` here is illustrative — match the local variable name at each call site.)

- [ ] **Step 4: Build**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go build ./...
```

Expected: success.

- [ ] **Step 5: Run all tests**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/... -count=1
```

Expected: PASS. Registry tests should be unaffected; the new fields default to `""`.

- [ ] **Step 6: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/internal/gateway/registry.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): expose TemplateSlug + CreatedBy on BackendServer

The runtime registry now mirrors mcp_servers.template_slug and
mcp_servers.created_by so the header injector can read them at
request time. Required by the upcoming Zoho auto-filter.

EN: Expose template_slug et created_by sur BackendServer pour
l'injection runtime du filtre Zoho.
EOF
)"
```

---

## Task 3: Context plumbing — ZohoFilterContext + ctx helpers

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/scopetoken/middleware.go`

Mirror the existing `LeexiFilterContext` block exactly.

- [ ] **Step 1: Add the context key**

In `apps-microservices/mcp-gateway-service/internal/scopetoken/middleware.go`, locate the existing `RingoverFilterContextKey` declaration (around line 51). Immediately after it, insert:

```go
// ZohoFilterContextKey carries a *ZohoFilterContext describing the active
// per-token / per-OAuth2-client Zoho ownership scope. Absence of the key
// means no admin filter is configured (Step 2 of requestHeadersFor sees
// nothing and emits no header). When the imported-server Step 1 path
// fires, this context is ignored.
const ZohoFilterContextKey = "scope_zoho_filter"
```

- [ ] **Step 2: Add the struct + accessor**

In the same file, after the existing `RingoverFilterFromContext` function (around line 125), insert:

```go
// ZohoFilterContext is the runtime view of the persisted Zoho scope.
type ZohoFilterContext struct {
	Mode          string   // "none" | "users" | "creator"
	AllowedEmails []string // for mode "users"
	// CreatorEmail is the owning user's email captured at scope-token /
	// OAuth2-client write time. Used only for mode "creator".
	CreatorEmail string
}

// ZohoFilterFromContext returns the typed Zoho filter info if any was set.
func ZohoFilterFromContext(ctx context.Context) (*ZohoFilterContext, bool) {
	v, ok := ctx.Value(ZohoFilterContextKey).(*ZohoFilterContext)
	return v, ok
}
```

- [ ] **Step 3: Build**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go build ./...
```

Expected: success.

- [ ] **Step 4: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/internal/scopetoken/middleware.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): add ZohoFilterContext to scope plumbing

ZohoFilterContextKey carries the active per-token / per-client Zoho
scope. Mirrors the existing Leexi/Ringover context shape; populated
by the two middlewares in a follow-up commit.

EN: Ajoute le contexte typé pour le filtre Zoho dans le plumbing
de scope.
EOF
)"
```

---

## Task 4: Caches — add Zoho fields + populate during cache-miss

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/scopetoken/cache.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/oauth2/cache.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/scopetoken/middleware.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/oauth2/middleware.go`

- [ ] **Step 1: Extend `CachedToken`**

In `apps-microservices/mcp-gateway-service/internal/scopetoken/cache.go`, locate `CachedToken`. After the `BDDAllowedTableIDs` field (around line 46), insert:

```go
	// Zoho ownership scope (echoed from the DB row). See db.ScopeToken.ZohoFilterMode.
	ZohoFilterMode    string   // "none" | "users" | "creator"
	ZohoAllowedEmails []string // for mode "users"
	ZohoCreatorEmail  string   // for mode "creator" — snapshot of CreatedBy at write time
```

- [ ] **Step 2: Extend `CachedClient`**

In `apps-microservices/mcp-gateway-service/internal/oauth2/cache.go`, locate `CachedClient`. After the `BDDAllowedTableIDs` field (around line 42), insert:

```go
	// Zoho ownership scope — mirrors scopetoken.CachedToken.
	ZohoFilterMode    string
	ZohoAllowedEmails []string
	ZohoCreatorEmail  string
```

- [ ] **Step 3: Populate `CachedToken` from DB row**

In `apps-microservices/mcp-gateway-service/internal/scopetoken/middleware.go`, locate the block where the cache-miss decodes the persisted Leexi/Ringover filters into the `CachedToken` (search for `LeexiFilterMode = ` near line 230 — exact line will vary; look for the per-token resolution path). Right after the Ringover decode block, insert:

```go
				// Decode persisted Zoho filter for runtime header injection.
				ct.ZohoFilterMode = dbToken.ZohoFilterMode
				if len(dbToken.ZohoAllowedEmails) > 0 {
					_ = json.Unmarshal(dbToken.ZohoAllowedEmails, &ct.ZohoAllowedEmails)
				}
				if ct.ZohoFilterMode == "creator" {
					ct.ZohoCreatorEmail = dbToken.CreatedBy
				}
```

(Match the local variable names already in use: replace `ct` / `dbToken` with whatever the surrounding block uses.)

- [ ] **Step 4: Stash `ZohoFilterContext` on request ctx (scope-token path)**

In the same file, locate the existing block that stashes `LeexiFilterContext` / `RingoverFilterContext` on the request ctx (around line 289). Right after the Ringover ctx assignment, insert:

```go
				if ct.ZohoFilterMode != "" && ct.ZohoFilterMode != "none" {
					ctx = context.WithValue(ctx, ZohoFilterContextKey, &ZohoFilterContext{
						Mode:          ct.ZohoFilterMode,
						AllowedEmails: ct.ZohoAllowedEmails,
						CreatorEmail:  ct.ZohoCreatorEmail,
					})
				}
```

- [ ] **Step 5: Populate `CachedClient` from DB row (OAuth2 path)**

In `apps-microservices/mcp-gateway-service/internal/oauth2/middleware.go`, locate the Ringover decode block (around line 138). Right after it, insert:

```go
					// Decode persisted Zoho filter (email strings).
					cc.ZohoFilterMode = client.ZohoFilterMode
					if len(client.ZohoAllowedEmails) > 0 {
						_ = json.Unmarshal(client.ZohoAllowedEmails, &cc.ZohoAllowedEmails)
					}
					if cc.ZohoFilterMode == "creator" {
						cc.ZohoCreatorEmail = client.CreatedBy
					}
```

- [ ] **Step 6: Stash `ZohoFilterContext` on request ctx (OAuth2 path)**

In the same file, locate the existing block around line 190 that stashes the Ringover filter on ctx. Right after that block (still inside the same `if cc.IsActive` branch), insert:

```go
				if cc.ZohoFilterMode != "" && cc.ZohoFilterMode != "none" {
					ctx = context.WithValue(ctx, scopetoken.ZohoFilterContextKey, &scopetoken.ZohoFilterContext{
						Mode:          cc.ZohoFilterMode,
						AllowedEmails: cc.ZohoAllowedEmails,
						CreatorEmail:  cc.ZohoCreatorEmail,
					})
				}
```

- [ ] **Step 7: Build**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go build ./...
```

Expected: success.

- [ ] **Step 8: Run all tests**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/... -count=1
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add \
  apps-microservices/mcp-gateway-service/internal/scopetoken/cache.go \
  apps-microservices/mcp-gateway-service/internal/oauth2/cache.go \
  apps-microservices/mcp-gateway-service/internal/scopetoken/middleware.go \
  apps-microservices/mcp-gateway-service/internal/oauth2/middleware.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): cache + stash Zoho filter on request context

Both the scope-token and OAuth2 middlewares decode the persisted Zoho
filter on cache-miss and stash a ZohoFilterContext on the request ctx
when the mode is anything but "none". Runtime header injection lands
in the next commit.

EN: Décode le filtre Zoho dans les caches et le pose sur le contexte
de requête côté scope-token et OAuth2.
EOF
)"
```

---

## Task 5: Gateway — injectZohoHeader + switch case (TDD)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_test.go`

Tests first. The contract: given a Zoho backend and a context, `requestHeadersFor` returns the expected `X-Zoho-Allowed-User` header (or no header).

- [ ] **Step 1: Open the existing test file to learn the local helpers**

Open `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_test.go` and the sibling `scoped_gateway_server_auth_test.go`. Note the helpers used to build a `*ScopedGateway`, a `*BackendServer`, and to push a filter onto ctx. Reuse the same helper names in the new tests.

- [ ] **Step 2: Write the failing tests**

Append a new test function to `scoped_gateway_test.go`:

```go
// TestRequestHeadersFor_Zoho verifies the per-server auto-filter (Step 1)
// and the admin-configured filter (Step 2) for Zoho backends.
func TestRequestHeadersFor_Zoho(t *testing.T) {
	const header = "X-Zoho-Allowed-User"
	const denySentinel = "deny-all@hellopro.fr.deny"

	t.Run("imported zoho server with created_by → step 1 wins", func(t *testing.T) {
		sg := newTestScopedGateway(t)
		backend := &BackendServer{
			ID:           "srv-1",
			ToolPrefix:   "zoho",
			TemplateSlug: "ga",
			CreatedBy:    "alice@hellopro.fr",
		}
		headers := sg.requestHeadersFor(context.Background(), backend)
		if got := headers[header]; got != "alice@hellopro.fr" {
			t.Fatalf("got %q, want %q", got, "alice@hellopro.fr")
		}
	})

	t.Run("imported zoho server with empty created_by → falls back to admin", func(t *testing.T) {
		sg := newTestScopedGateway(t)
		backend := &BackendServer{
			ID:           "srv-2",
			ToolPrefix:   "zoho",
			TemplateSlug: "ga",
			CreatedBy:    "",
		}
		ctx := context.WithValue(context.Background(), scopetoken.ZohoFilterContextKey, &scopetoken.ZohoFilterContext{
			Mode:          "users",
			AllowedEmails: []string{"bob@hp.fr", "carol@hp.fr"},
		})
		headers := sg.requestHeadersFor(ctx, backend)
		if got := headers[header]; got != "bob@hp.fr,carol@hp.fr" {
			t.Fatalf("got %q, want %q", got, "bob@hp.fr,carol@hp.fr")
		}
	})

	t.Run("manual zoho server + users mode → step 2 csv", func(t *testing.T) {
		sg := newTestScopedGateway(t)
		backend := &BackendServer{
			ID:         "srv-3",
			ToolPrefix: "zoho",
			// no TemplateSlug, no CreatedBy
		}
		ctx := context.WithValue(context.Background(), scopetoken.ZohoFilterContextKey, &scopetoken.ZohoFilterContext{
			Mode:          "users",
			AllowedEmails: []string{"bob@hp.fr"},
		})
		headers := sg.requestHeadersFor(ctx, backend)
		if got := headers[header]; got != "bob@hp.fr" {
			t.Fatalf("got %q, want %q", got, "bob@hp.fr")
		}
	})

	t.Run("manual zoho server + mode none → no header", func(t *testing.T) {
		sg := newTestScopedGateway(t)
		backend := &BackendServer{ID: "srv-4", ToolPrefix: "zoho"}
		ctx := context.WithValue(context.Background(), scopetoken.ZohoFilterContextKey, &scopetoken.ZohoFilterContext{Mode: "none"})
		headers := sg.requestHeadersFor(ctx, backend)
		if _, ok := headers[header]; ok {
			t.Fatalf("expected no %s header, got %q", header, headers[header])
		}
	})

	t.Run("users mode + empty list → deny sentinel", func(t *testing.T) {
		sg := newTestScopedGateway(t)
		backend := &BackendServer{ID: "srv-5", ToolPrefix: "zoho"}
		ctx := context.WithValue(context.Background(), scopetoken.ZohoFilterContextKey, &scopetoken.ZohoFilterContext{
			Mode:          "users",
			AllowedEmails: nil,
		})
		headers := sg.requestHeadersFor(ctx, backend)
		if got := headers[header]; got != denySentinel {
			t.Fatalf("got %q, want %q", got, denySentinel)
		}
	})

	t.Run("creator mode → single email", func(t *testing.T) {
		sg := newTestScopedGateway(t)
		backend := &BackendServer{ID: "srv-6", ToolPrefix: "zoho"}
		ctx := context.WithValue(context.Background(), scopetoken.ZohoFilterContextKey, &scopetoken.ZohoFilterContext{
			Mode:         "creator",
			CreatorEmail: "dave@hp.fr",
		})
		headers := sg.requestHeadersFor(ctx, backend)
		if got := headers[header]; got != "dave@hp.fr" {
			t.Fatalf("got %q, want %q", got, "dave@hp.fr")
		}
	})

	t.Run("creator mode + empty creator → deny sentinel", func(t *testing.T) {
		sg := newTestScopedGateway(t)
		backend := &BackendServer{ID: "srv-7", ToolPrefix: "zoho"}
		ctx := context.WithValue(context.Background(), scopetoken.ZohoFilterContextKey, &scopetoken.ZohoFilterContext{
			Mode:         "creator",
			CreatorEmail: "",
		})
		headers := sg.requestHeadersFor(ctx, backend)
		if got := headers[header]; got != denySentinel {
			t.Fatalf("got %q, want %q", got, denySentinel)
		}
	})

	t.Run("non-zoho backend ignores zoho filter", func(t *testing.T) {
		sg := newTestScopedGateway(t)
		backend := &BackendServer{ID: "srv-8", ToolPrefix: "leexi"}
		ctx := context.WithValue(context.Background(), scopetoken.ZohoFilterContextKey, &scopetoken.ZohoFilterContext{
			Mode:          "users",
			AllowedEmails: []string{"bob@hp.fr"},
		})
		headers := sg.requestHeadersFor(ctx, backend)
		if _, ok := headers[header]; ok {
			t.Fatalf("expected no %s header for non-zoho backend, got %q", header, headers[header])
		}
	})
}
```

**Important:** the helper `newTestScopedGateway(t)` already exists in the sibling test files; if its current signature does not match what this test needs, prefer the equivalent helper used by `TestRequestHeadersFor_Leexi` in the same package and mirror it. Do **not** invent new helpers.

- [ ] **Step 3: Run the tests, verify compile failure**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run TestRequestHeadersFor_Zoho -v
```

Expected: compile error — `BackendServer` has no `TemplateSlug` / `CreatedBy` fields was already added in Task 2, so the actual error will be one of: `ZohoFilterContextKey` undefined (if Task 3 not done), `ZohoFilterContext` undefined, or the test references behaviour not yet wired (no `X-Zoho-Allowed-User` header produced). All are expected. Confirm at least one error message mentions the missing Zoho path or the absence of the header.

- [ ] **Step 4: Add the constants + injector**

In `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go`, locate the existing `LeexiAllowedParticipantsHeader` declaration (around line 53). After the `BDDAllowedTablesHeader` line (around line 63), insert:

```go
// ZohoAllowedUserHeader carries one or more comma-separated emails when the
// active backend is Zoho-tagged and a filter (auto or admin) applies.
const ZohoAllowedUserHeader = "X-Zoho-Allowed-User"

// zohoDenySentinel is the email value injected when the admin-configured
// Zoho filter resolves to an empty allow-list. The Zoho MCP backend treats
// any unknown email as no-access; this value is intentionally never a real
// account.
const zohoDenySentinel = "deny-all@hellopro.fr.deny"

// zohoToolPrefix is the ToolPrefix value identifying Zoho backends in the
// in-memory registry. Mirrors leexiToolPrefix / ringoverToolPrefix.
const zohoToolPrefix = "zoho"
```

(Match the existing capitalisation style: `leexiToolPrefix` is lowercase, so `zohoToolPrefix` should be lowercase too.)

- [ ] **Step 5: Add the injector method**

In the same file, at the end of the file (or directly after `injectRingoverHeader`), insert:

```go
// injectZohoHeader resolves the Zoho filter for this request.
//
// Step 1 — when the backend is an imported Zoho server (non-empty
// TemplateSlug + non-empty CreatedBy), inject the server's created_by as
// the allowed user. Per-server, deterministic; end-user identity is not
// consulted.
//
// Step 2 — otherwise, resolve the admin-configured per-token /
// per-OAuth2-client filter:
//   - mode "none" or no filter on ctx → no header (unrestricted backend)
//   - mode "users" with non-empty list → comma-joined emails
//   - mode "users" with empty list → deny sentinel
//   - mode "creator" with non-empty CreatorEmail → single email
//   - mode "creator" with empty CreatorEmail → deny sentinel
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
		if filter.CreatorEmail == "" {
			headers[ZohoAllowedUserHeader] = zohoDenySentinel
			return
		}
		headers[ZohoAllowedUserHeader] = filter.CreatorEmail
	}
}
```

- [ ] **Step 6: Wire the switch case in `requestHeadersFor`**

In the same file, locate the existing `switch backend.ToolPrefix` block in `requestHeadersFor` (around line 213). Add the Zoho case BEFORE the BDD case:

```go
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
```

- [ ] **Step 7: Run the Zoho tests, verify PASS**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run TestRequestHeadersFor_Zoho -v
```

Expected: 8 sub-tests PASS.

- [ ] **Step 8: Run the full backend test suite**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go test ./internal/... -count=1
```

Expected: PASS. Existing Leexi/Ringover/BDD tests should be untouched.

- [ ] **Step 9: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add \
  apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go \
  apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_test.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): inject X-Zoho-Allowed-User on Zoho backends

Per-server auto-filter on imported Zoho servers (template_slug !=
'' AND created_by != '' → header value = backend.CreatedBy) with
fall-through to the admin per-token / per-OAuth2-client filter
(modes: none, users, creator) and a deny sentinel on empty allow-lists.

EN: Injecte X-Zoho-Allowed-User sur les backends Zoho avec auto-filtre
côté serveur importé et repli sur la configuration admin.
EOF
)"
```

---

## Task 6: API DTOs + handler validation

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/token_dto.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/api/oauth2_dto.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/api/token_handlers.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/api/oauth2_handlers.go`

- [ ] **Step 1: Add DTO + mode constants in `token_dto.go`**

In `apps-microservices/mcp-gateway-service/internal/api/token_dto.go`, after the `BDDFilterDTO` block (around line 60), insert:

```go
// ZohoFilterMode constants — accepted values for ZohoFilterDTO.Mode.
const (
	ZohoFilterModeNone    = "none"
	ZohoFilterModeUsers   = "users"
	ZohoFilterModeCreator = "creator"
)

// ZohoFilterDTO carries the per-token / per-client Zoho ownership scope.
// AllowedEmails is meaningful only when Mode = "users". CreatorEmail is
// response-only — set to the resolved CreatedBy when Mode = "creator".
type ZohoFilterDTO struct {
	Mode          string   `json:"mode"`                     // none | users | creator
	AllowedEmails []string `json:"allowed_emails,omitempty"` // Mode = users
	CreatorEmail  string   `json:"creator_email,omitempty"`  // response-only when Mode = creator
}
```

- [ ] **Step 2: Add `ZohoFilter` to every relevant request / response struct in `token_dto.go`**

Locate every struct in `token_dto.go` that currently has a `LeexiFilter *LeexiFilterDTO` field (`CreateTokenRequest`, `CreateTokenResponse`, `UpdateTokenRequest`, `GetTokenResponse`, `ListTokensResponseEntry` — the exact names will match the surrounding pattern). For each, add a sibling line right after the `BDDFilter` field:

```go
	ZohoFilter     *ZohoFilterDTO        `json:"zoho_filter,omitempty"`
```

- [ ] **Step 3: Add the same field on the OAuth2 DTOs**

In `apps-microservices/mcp-gateway-service/internal/api/oauth2_dto.go`, locate every struct with a `LeexiFilter` field and add a sibling `ZohoFilter` field with the same JSON tag (`zoho_filter,omitempty`).

- [ ] **Step 4: Helper conversion functions**

In `apps-microservices/mcp-gateway-service/internal/api/token_handlers.go`, locate the existing `scopeTokenLeexiFilterToDTO` helper. Right after it, add:

```go
// scopeTokenZohoFilterToDTO converts the persisted Zoho columns on a
// ScopeToken row into the wire DTO. Returns nil when no filter is set
// so the JSON serialisation omits the key (zoho_filter,omitempty).
func scopeTokenZohoFilterToDTO(t *db.ScopeToken) *ZohoFilterDTO {
	if t == nil || t.ZohoFilterMode == "" || t.ZohoFilterMode == ZohoFilterModeNone {
		return nil
	}
	dto := &ZohoFilterDTO{Mode: t.ZohoFilterMode}
	if t.ZohoFilterMode == ZohoFilterModeUsers && len(t.ZohoAllowedEmails) > 0 {
		_ = json.Unmarshal(t.ZohoAllowedEmails, &dto.AllowedEmails)
	}
	if t.ZohoFilterMode == ZohoFilterModeCreator {
		dto.CreatorEmail = t.CreatedBy
	}
	return dto
}
```

In `apps-microservices/mcp-gateway-service/internal/api/oauth2_handlers.go`, locate `oauth2ClientLeexiFilterToDTO`. Right after it, add the equivalent for the OAuth2 client:

```go
func oauth2ClientZohoFilterToDTO(c *db.OAuth2Client) *ZohoFilterDTO {
	if c == nil || c.ZohoFilterMode == "" || c.ZohoFilterMode == ZohoFilterModeNone {
		return nil
	}
	dto := &ZohoFilterDTO{Mode: c.ZohoFilterMode}
	if c.ZohoFilterMode == ZohoFilterModeUsers && len(c.ZohoAllowedEmails) > 0 {
		_ = json.Unmarshal(c.ZohoAllowedEmails, &dto.AllowedEmails)
	}
	if c.ZohoFilterMode == ZohoFilterModeCreator {
		dto.CreatorEmail = c.CreatedBy
	}
	return dto
}
```

- [ ] **Step 5: Validation helper**

In `apps-microservices/mcp-gateway-service/internal/api/token_handlers.go`, near the top of the file (after the imports / before the handler function), add a shared validator used by both create and update paths:

```go
// applyZohoFilterToDBRow validates a *ZohoFilterDTO and writes it into the
// generic target's ZohoFilterMode + ZohoAllowedEmails fields. The interface
// is satisfied by both *db.ScopeToken and *db.OAuth2Client via reflection-
// free helpers below. Returns a user-facing error on invalid input.
func applyZohoFilterToDBRow(dto *ZohoFilterDTO, setMode func(string), setEmails func(json.RawMessage)) error {
	if dto == nil || dto.Mode == "" || dto.Mode == ZohoFilterModeNone {
		setMode(ZohoFilterModeNone)
		setEmails(nil)
		return nil
	}
	switch dto.Mode {
	case ZohoFilterModeUsers:
		emails := uniqueTrimmedEmails(dto.AllowedEmails)
		if len(emails) == 0 {
			return fmt.Errorf("zoho_filter.allowed_emails: must contain at least one non-empty email when mode is %q", ZohoFilterModeUsers)
		}
		raw, err := json.Marshal(emails)
		if err != nil {
			return fmt.Errorf("zoho_filter.allowed_emails: failed to encode: %w", err)
		}
		setMode(ZohoFilterModeUsers)
		setEmails(raw)
		return nil
	case ZohoFilterModeCreator:
		setMode(ZohoFilterModeCreator)
		setEmails(nil)
		return nil
	default:
		return fmt.Errorf("zoho_filter.mode: unknown value %q (expected: none | users | creator)", dto.Mode)
	}
}

// uniqueTrimmedEmails strips whitespace, drops empty entries, and removes
// duplicates while preserving first-seen order.
func uniqueTrimmedEmails(in []string) []string {
	seen := make(map[string]struct{}, len(in))
	out := make([]string, 0, len(in))
	for _, e := range in {
		e = strings.TrimSpace(e)
		if e == "" {
			continue
		}
		if _, dup := seen[e]; dup {
			continue
		}
		seen[e] = struct{}{}
		out = append(out, e)
	}
	return out
}
```

(Imports: ensure `encoding/json`, `errors`/`fmt`, `strings` are present — most are already in scope.)

- [ ] **Step 6: Wire into token create**

In `apps-microservices/mcp-gateway-service/internal/api/token_handlers.go`, locate the place where `req.LeexiFilter` is consumed during token creation (around line 124 — the call to a Leexi resolver). Right after the Leexi/Ringover/BDD wiring, insert:

```go
	if err := applyZohoFilterToDBRow(
		req.ZohoFilter,
		func(m string) { token.ZohoFilterMode = m },
		func(b json.RawMessage) { token.ZohoAllowedEmails = b },
	); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
		return
	}
```

- [ ] **Step 7: Wire into token update**

In the same file, locate the existing block that consumes `req.LeexiFilter` during update (around line 313). Right after the Leexi/Ringover/BDD update wiring, insert:

```go
	if req.ZohoFilter != nil {
		if err := applyZohoFilterToDBRow(
			req.ZohoFilter,
			func(m string) { existing.ZohoFilterMode = m },
			func(b json.RawMessage) { existing.ZohoAllowedEmails = b },
		); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
			return
		}
	}
```

- [ ] **Step 8: Wire into token response shape**

Still in `token_handlers.go`, locate every site that builds a response DTO from a `db.ScopeToken` (search for `LeexiFilter: scopeTokenLeexiFilterToDTO(...)`). After the Leexi line at each site, add:

```go
		ZohoFilter:     scopeTokenZohoFilterToDTO(&token),
```

(Match the local variable name — `&token`, `&t`, `&row`, etc.)

- [ ] **Step 9: Wire into OAuth2-client handlers**

In `apps-microservices/mcp-gateway-service/internal/api/oauth2_handlers.go`, repeat steps 6–8 against the OAuth2-client create / update / response paths. The same `applyZohoFilterToDBRow` helper is reused (live in `token_handlers.go`); just supply setters for `client.ZohoFilterMode` and `client.ZohoAllowedEmails`.

- [ ] **Step 10: Build + tests**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go build ./... && go test ./internal/... -count=1
```

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add \
  apps-microservices/mcp-gateway-service/internal/api/token_dto.go \
  apps-microservices/mcp-gateway-service/internal/api/oauth2_dto.go \
  apps-microservices/mcp-gateway-service/internal/api/token_handlers.go \
  apps-microservices/mcp-gateway-service/internal/api/oauth2_handlers.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): zoho_filter DTO + CRUD handlers for tokens and clients

Adds ZohoFilterDTO (modes: none, users, creator) on the create / update
/ response payloads of /api/v1/tokens and /api/v1/oauth2/clients.
Server-side validation strips whitespace, deduplicates emails, and
rejects unknown modes with 400.

EN: Ajoute le DTO zoho_filter et le câblage CRUD côté tokens et
clients OAuth2.
EOF
)"
```

---

## Task 7: Frontend types + API client pass-through

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/types/server.ts` (or whichever TS file currently declares `LeexiFilter` — confirm by grep before editing)

- [ ] **Step 1: Locate the existing Leexi types**

Run:
```bash
grep -n "LeexiFilter\b\|leexi_filter" apps-microservices/mcp-gateway-frontend/src/types/*.ts
```

Open every file the grep returns. Identify (a) the `LeexiFilter` interface definition and (b) every place a `leexi_filter?: LeexiFilter` field appears on a request/response type. These are the files you will mirror.

- [ ] **Step 2: Add the `ZohoFilter` interface**

Right after the `LeexiFilter` interface declaration, insert:

```ts
// ZohoFilter mirrors the backend ZohoFilterDTO. allowed_emails is
// meaningful only when mode === 'users'. creator_email is response-only
// and reflects the row's created_by snapshot when mode === 'creator'.
export interface ZohoFilter {
  mode: 'none' | 'users' | 'creator'
  allowed_emails?: string[]
  creator_email?: string
}
```

- [ ] **Step 3: Add `zoho_filter` to every request / response type that carries `leexi_filter`**

For each location identified in Step 1, add a sibling `zoho_filter?: ZohoFilter` line right under the existing `leexi_filter?: LeexiFilter` field.

- [ ] **Step 4: Typecheck + build**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-frontend && npm run type-check && npm run build
```

Expected: both succeed (the field is optional everywhere — no existing payload breaks).

- [ ] **Step 5: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-frontend/src/types/
git commit -m "$(cat <<'EOF'
feat(mcp-gateway-frontend): add ZohoFilter TS types

Mirrors the backend zoho_filter DTO on token and OAuth2-client request
and response shapes.

EN: Ajoute les types TypeScript du filtre Zoho côté frontend.
EOF
)"
```

---

## Task 8: Frontend `ZohoFilterPanel.vue` + plug into forms

**Files:**
- Create: `apps-microservices/mcp-gateway-frontend/src/components/tokens/ZohoFilterPanel.vue`
- Modify: `apps-microservices/mcp-gateway-frontend/src/views/TokenFormView.vue`
- Modify: `apps-microservices/mcp-gateway-frontend/src/views/ClientFormView.vue`

- [ ] **Step 1: Read the existing `LeexiFilterPanel.vue`**

Open `apps-microservices/mcp-gateway-frontend/src/components/tokens/LeexiFilterPanel.vue`. Skim it end-to-end. Note: its props, emits, the way it gates render on selected backends, and the way it serialises emit payloads.

- [ ] **Step 2: Create `ZohoFilterPanel.vue`**

Create `apps-microservices/mcp-gateway-frontend/src/components/tokens/ZohoFilterPanel.vue` with the following content. Keep the structural blocks (props, emits, conditional render) identical to `LeexiFilterPanel.vue`; only the emit payload shape, the labels, and the user editor differ.

```vue
<template>
  <section
    v-if="visible"
    class="rounded-lg border border-gray-200 dark:border-gray-800 p-4 space-y-3"
  >
    <header>
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
        Filtre Zoho
      </h3>
      <p class="text-xs text-gray-500 dark:text-gray-400">
        Restreint les appels Zoho aux emails autorisés.
        Pour les serveurs Zoho importés depuis un Google Sheet, le `created_by`
        du serveur prend précédence (filtre automatique par ligne).
      </p>
    </header>

    <div class="flex items-center gap-3">
      <label class="text-sm text-gray-700 dark:text-gray-300">Mode</label>
      <select
        v-model="modeLocal"
        class="text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-1.5 bg-white dark:bg-gray-800 dark:text-gray-200"
        @change="emitChange"
      >
        <option value="none">Aucun (illimité)</option>
        <option value="users">Liste d'emails</option>
        <option value="creator">Créateur</option>
      </select>
    </div>

    <div v-if="modeLocal === 'users'" class="space-y-2">
      <label class="block text-sm text-gray-700 dark:text-gray-300">
        Emails autorisés
      </label>
      <div class="flex gap-2">
        <input
          v-model="newEmail"
          type="email"
          placeholder="alice@hellopro.fr"
          class="h-9 flex-1 text-sm rounded-md border border-gray-300 dark:border-gray-600 px-3 bg-white dark:bg-gray-800 dark:text-gray-200"
          @keyup.enter.prevent="addEmail"
        />
        <button
          type="button"
          class="px-3 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="addEmail"
        >
          Ajouter
        </button>
      </div>
      <ul class="flex flex-wrap gap-2">
        <li
          v-for="email in emailsLocal"
          :key="email"
          class="inline-flex items-center gap-1 text-xs bg-gray-100 dark:bg-white/5 text-gray-700 dark:text-gray-300 rounded-full px-2 py-0.5"
        >
          {{ email }}
          <button
            type="button"
            class="text-gray-400 hover:text-error-500"
            @click="removeEmail(email)"
            aria-label="Retirer"
          >×</button>
        </li>
      </ul>
      <p v-if="!emailsLocal.length" class="text-xs text-error-500">
        Mode "users" requiert au moins un email.
      </p>
    </div>

    <p v-else-if="modeLocal === 'creator'" class="text-xs text-gray-500 dark:text-gray-400">
      Le filtre sera lié au créateur de cet enregistrement :
      <code class="font-mono">{{ creatorEmail || '(à la création)' }}</code>
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ZohoFilter } from '@/types/server'

const props = defineProps<{
  modelValue: ZohoFilter | null | undefined
  selectedToolPrefixes: string[]
  creatorEmail?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ZohoFilter | null]
}>()

const visible = computed(() => props.selectedToolPrefixes.includes('zoho'))

const modeLocal = ref<ZohoFilter['mode']>(props.modelValue?.mode ?? 'none')
const emailsLocal = ref<string[]>(props.modelValue?.allowed_emails ?? [])
const newEmail = ref('')

watch(
  () => props.modelValue,
  (next) => {
    modeLocal.value = next?.mode ?? 'none'
    emailsLocal.value = next?.allowed_emails ?? []
  },
)

function addEmail() {
  const v = newEmail.value.trim()
  if (!v) return
  if (emailsLocal.value.includes(v)) {
    newEmail.value = ''
    return
  }
  emailsLocal.value = [...emailsLocal.value, v]
  newEmail.value = ''
  emitChange()
}

function removeEmail(email: string) {
  emailsLocal.value = emailsLocal.value.filter(e => e !== email)
  emitChange()
}

function emitChange() {
  if (modeLocal.value === 'none') {
    emit('update:modelValue', null)
    return
  }
  emit('update:modelValue', {
    mode: modeLocal.value,
    allowed_emails: modeLocal.value === 'users' ? emailsLocal.value : undefined,
  })
}
</script>
```

- [ ] **Step 3: Mount the panel in `TokenFormView.vue`**

Open `apps-microservices/mcp-gateway-frontend/src/views/TokenFormView.vue`. Locate the `<RingoverFilterPanel>` mount site. Directly after that closing tag, insert:

```vue
        <ZohoFilterPanel
          v-model="form.zoho_filter"
          :selected-tool-prefixes="selectedToolPrefixes"
          :creator-email="form.created_by"
        />
```

Add the import in the `<script setup>` block (alongside `RingoverFilterPanel`):

```ts
import ZohoFilterPanel from '@/components/tokens/ZohoFilterPanel.vue'
```

Initialise the form field. Locate where `leexi_filter` / `ringover_filter` are declared on the form object (or `reactive`/`ref`) and add a sibling:

```ts
  zoho_filter: null as ZohoFilter | null,
```

Add the import for the type:

```ts
import type { ZohoFilter } from '@/types/server'
```

- [ ] **Step 4: Mount the panel in `ClientFormView.vue`**

Repeat Step 3 against `apps-microservices/mcp-gateway-frontend/src/views/ClientFormView.vue`. The panel mount and form initialisation are identical.

- [ ] **Step 5: Typecheck + build**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-frontend && npm run type-check && npm run build
```

Expected: success.

- [ ] **Step 6: Smoke test (optional but recommended)**

Start the stack:
```bash
docker compose up -d mcp-gateway-service mcp-gateway-frontend
```

In a browser, open `/tokens/new` and confirm:
1. With no Zoho server in the picked set, the panel is hidden.
2. With a Zoho server picked, the panel appears with Mode select.
3. Mode "users" reveals the email editor; emails persist on submit.
4. Mode "creator" shows the creator hint with the connected user's email.
5. Submitting creates the token with `zoho_filter: {mode, allowed_emails}` visible in the GET response.

Repeat for `/oauth2/clients/new`.

- [ ] **Step 7: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add \
  apps-microservices/mcp-gateway-frontend/src/components/tokens/ZohoFilterPanel.vue \
  apps-microservices/mcp-gateway-frontend/src/views/TokenFormView.vue \
  apps-microservices/mcp-gateway-frontend/src/views/ClientFormView.vue
git commit -m "$(cat <<'EOF'
feat(mcp-gateway-frontend): ZohoFilterPanel + plug into token / client forms

Adds the per-token and per-OAuth2-client Zoho filter editor. Mirrors
the LeexiFilterPanel UX: hidden when no Zoho backend is selected,
mode select (none / users / creator), email chip editor for users
mode, creator-email hint for creator mode.

EN: Composant ZohoFilterPanel et intégration dans les formulaires
token / client OAuth2.
EOF
)"
```

---

## Task 9: CLAUDE.md refresh

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`

- [ ] **Step 1: Update the server-level grants paragraph**

Open `apps-microservices/mcp-gateway-service/CLAUDE.md`. Locate the bullet starting `**Server-level full-access grants (admin)**` (around line 281). The current text mentions `(Leexi, Ringover, BDD, future Zoho)`. Replace `future Zoho` with `Zoho`:

```
…the gateway skips ALL filter-header injection (Leexi, Ringover, BDD, Zoho)…
```

- [ ] **Step 2: Add a Zoho filter convention bullet**

In the same `Conventions` section, locate the Leexi convention bullet (search for `Leexi ownership filter` — around line 281). After the BDD convention bullet that follows it, insert:

```markdown
- **Zoho ownership filter**: scope tokens and OAuth2 clients carry an optional Zoho filter (`ZohoFilterMode` + `ZohoAllowedEmails`). Resolution at `requestHeadersFor`: Step 0 server-authorization grant → **Step 1 imported-server auto-filter** (when `backend.ToolPrefix == "zoho"` AND `backend.TemplateSlug != ""` AND `backend.CreatedBy != ""`, inject `X-Zoho-Allowed-User: <created_by>`) → Step 2 admin-configured filter (modes: `none` no header, `users` comma-joined emails, `creator` single email = token/client `created_by`). Deny sentinel `deny-all@hellopro.fr.deny` is injected when an admin filter resolves to an empty allow-list. The Zoho MCP backend enforces the header server-side.
```

- [ ] **Step 3: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB && git add apps-microservices/mcp-gateway-service/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(mcp-gateway): document Zoho filter in CLAUDE.md

Refreshes the Server-level full-access paragraph to drop the "future
Zoho" hedge and adds a Zoho convention bullet describing the two-step
resolution (imported-server auto-filter, admin per-client fallback).

EN: Documente le filtre Zoho dans le CLAUDE.md du service.
EOF
)"
```

---

## Task 10: Final verification + PR

- [ ] **Step 1: Backend full build + tests**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-service && go build ./... && go test ./... -count=1
```

Expected: success across all packages.

- [ ] **Step 2: Frontend typecheck + build + tests**

Run:
```bash
cd /home/sandratra/RAG-HP-PUB/apps-microservices/mcp-gateway-frontend && npm run type-check && npm run build && npm run test --silent
```

Expected: success.

- [ ] **Step 3: End-to-end smoke (live stack)**

Bring up the stack and walk through both end-user paths.

```bash
cd /home/sandratra/RAG-HP-PUB && docker compose up -d mcp-gateway-service mcp-gateway-frontend
```

A. Imported Zoho server path (Step 1):
1. Use the just-shipped sheet-import feature to import a Zoho instance with `created_by = alice@hp.fr`.
2. Tail the gateway logs:
   ```bash
   docker compose logs -f mcp-gateway-service
   ```
3. Issue a tool call against that backend through a scope token or OAuth2 client that has the server in its allow-list.
4. Confirm the gateway log line for the outbound MCP call includes `X-Zoho-Allowed-User: alice@hp.fr`.

B. Admin-configured filter path (Step 2):
1. Create a manual Zoho server (no `template_slug`).
2. Create / update a token with `zoho_filter: {mode: "users", allowed_emails: ["bob@hp.fr"]}` via the `/tokens` admin UI or via curl.
3. Issue a tool call. Confirm log line `X-Zoho-Allowed-User: bob@hp.fr`.
4. Update the same token to `mode: "users", allowed_emails: []` and issue another call — confirm log line `X-Zoho-Allowed-User: deny-all@hellopro.fr.deny`.
5. Set `mode: "creator"` and confirm the token creator's email is injected.

C. Bypass via server-authorization grant:
1. Add a `server_authorizations` row for the calling end-user on the Zoho server (via the admin UI).
2. Issue the same tool call — confirm no `X-Zoho-Allowed-User` header is injected (existing Step 0 behavior).

Document any unexpected behavior in the PR description.

- [ ] **Step 4: Confirm spec coverage**

Re-read `docs/superpowers/specs/2026-05-12-zoho-auto-filter-design.md`. Walk through every row of the "Validation rules" table, every item in "Tests", and every line of "Affected Surfaces" — confirm each maps to behavior verified above. Note any gap in the PR body.

- [ ] **Step 5: Push and open PR (REQUIRES USER CONFIRMATION)**

Do **not** push without the user's explicit OK. When approved, run:

```bash
cd /home/sandratra/RAG-HP-PUB && git push -u origin features/poc
gh pr create --title "feat(mcp-gateway): Zoho auto-filter on imported servers + admin fallback" --body "$(cat <<'EOF'
## Summary
- Backend: per-server `X-Zoho-Allowed-User` injection when `backend.ToolPrefix == 'zoho'` AND `backend.TemplateSlug != ''` AND `backend.CreatedBy != ''` (Step 1 auto-filter).
- Backend: admin-configured per-token / per-OAuth2-client Zoho filter (`ZohoFilterMode` + `ZohoAllowedEmails`) covering modes `none`, `users`, `creator` (Step 2 fallback).
- Backend: new `injectZohoHeader` + switch case in `scoped_gateway.go`. Existing server-authorization grant continues to bypass everything (Step 0).
- Frontend: new `ZohoFilterPanel.vue`, mounted under `RingoverFilterPanel` on token and OAuth2-client forms.
- Docs: CLAUDE.md refreshed.

Spec: `docs/superpowers/specs/2026-05-12-zoho-auto-filter-design.md`
Plan: `docs/superpowers/plans/2026-05-12-zoho-auto-filter.md`

## Test plan
- [x] `go test ./internal/...` in `mcp-gateway-service` — new `TestRequestHeadersFor_Zoho` (8 sub-cases)
- [x] `npm run type-check && npm run build` in `mcp-gateway-frontend`
- [x] Manual: imported Zoho server → `X-Zoho-Allowed-User: <created_by>`
- [x] Manual: manual Zoho server + admin users mode → CSV emails
- [x] Manual: empty allow-list → deny sentinel
- [x] Manual: mode creator → token/client.created_by
- [x] Manual: server-authorization grant → bypass, no Zoho header
EOF
)"
```

---

## Self-review (run before declaring complete)

1. **Spec coverage**
   - Two-step resolution (auto + admin) → Task 5.
   - Schema additions on both `scope_tokens` and `oauth2_clients` → Task 1.
   - `BackendServer.TemplateSlug` + `BackendServer.CreatedBy` exposed → Task 2.
   - `ZohoFilterContext` + cache plumbing on both middleware paths → Tasks 3 + 4.
   - DTO + handler validation (mode + emails) → Task 6.
   - Frontend types → Task 7.
   - `ZohoFilterPanel.vue` + form integration → Task 8.
   - Docs refresh → Task 9.
   - Manual + automated verification → Task 10.
   - Tests cover all eight cases listed in the spec → Task 5 Step 2.

2. **Placeholder scan**
   - No "TODO", "TBD", "fill in details", "similar to Task N" with elided code, "add appropriate error handling". ✔
   - Every code step shows the exact code to write.

3. **Type consistency**
   - Backend: `ZohoFilterMode` / `ZohoAllowedEmails` on DB models, cache, DTO. ✔
   - Backend: `ZohoFilterContext{Mode, AllowedEmails, CreatorEmail}` consistent across Tasks 3, 4, 5. ✔
   - Backend: `injectZohoHeader(ctx, headers, backend)` signature consistent across Tasks 5 (definition) and 5 (switch wiring). ✔
   - Frontend: `ZohoFilter{mode, allowed_emails?, creator_email?}` interface consistent across Tasks 7 and 8. ✔
   - Constants: `ZohoAllowedUserHeader = "X-Zoho-Allowed-User"`, `zohoDenySentinel = "deny-all@hellopro.fr.deny"`, `zohoToolPrefix = "zoho"` referenced consistently in Task 5 (defines them) and the test cases in Task 5 Step 2 (uses them).

No gaps found.
