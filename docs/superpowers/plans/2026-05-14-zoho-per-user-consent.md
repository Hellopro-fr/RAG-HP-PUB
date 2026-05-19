# Per-User Zoho Tools on OAuth2 Consent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Partition the `/authorize` consent screen into "Configurés" / "Non configurés" sections so non-admin viewers only see their own Zoho tools (or a docs CTA when their `zoho_imports` row is missing) and admins only see admin tools (or the same CTA when the admin row is missing).

**Architecture:** Replace `ZohoUserCatalog.ToolsForEmail` with `StateForEmail` returning `{Tools, Configured}`. The adapter (`internal/app/zoho_catalog_adapter.go`) gets a `UserRepo` dependency so it can resolve the viewer's role (`gateway_users.role == "admin"`) before deciding whether to consult the admin or user row — no admin-row fallback for non-admin viewers. Consent rendering partitions the server list into a normal "Configurés" slice and an "Unconfigurés" slice that surfaces a CTA link to `{GATEWAY_PUBLIC_URL}/docs/zohocrm` (existing Vue page).

**Tech Stack:** Go 1.24 (`net/http`, GORM, `html/template`), Vue 3 + TypeScript (mcp-gateway-frontend), `go test`.

**Spec:** `docs/superpowers/specs/2026-05-14-zoho-per-user-consent-design.md`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `apps-microservices/mcp-gateway-service/internal/gateway/zoho_state.go` | **Create** | `ZohoServerState` + `ZohoCatalogState` value types (kept separate from `gateway.go` for clarity). |
| `apps-microservices/mcp-gateway-service/internal/gateway/gateway.go` | **Modify** | Replace `ZohoUserCatalog` interface and `FetchZohoToolsForUser` method. |
| `apps-microservices/mcp-gateway-service/internal/gateway/gateway_test.go` | **Modify** | Cover `FetchZohoStateForUser` per-server Configured flag. |
| `apps-microservices/mcp-gateway-service/internal/app/zoho_catalog_adapter.go` | **Modify** | Add `users *repository.UserRepo`, role-based resolution, no admin fallback for non-admins. Drop legacy `ToolsForEmail`. |
| `apps-microservices/mcp-gateway-service/internal/app/zoho_catalog_adapter_test.go` | **Modify** | Add role-based cases; drop admin-fallback case. |
| `apps-microservices/mcp-gateway-service/internal/app/app.go` | **Modify** | Inject `userRepo` into adapter ctor. |
| `apps-microservices/mcp-gateway-service/internal/authserver/handler.go` | **Modify** | Rename field `zohoFetcher`'s type → `ZohoStateForUser`. Add `DocsURL` field to `AuthServer` + `AuthServerConfig`. |
| `apps-microservices/mcp-gateway-service/internal/authserver/authorize_api.go` | **Modify** | New interface `ZohoStateForUser`. Add `Configured` + `DocsURL` to `authorizeServerDTO`. Replace `applyZohoUserTools` with `applyZohoUserState`. |
| `apps-microservices/mcp-gateway-service/internal/authserver/authorize_api_test.go` | **Modify** | Cover `Configured` + `DocsURL` JSON output. |
| `apps-microservices/mcp-gateway-service/internal/authserver/authorize.go` | **Modify** | `renderConsent` partition into `Servers` + `UnconfiguredServers`. Pass `DocsURL` to template. |
| `apps-microservices/mcp-gateway-service/internal/authserver/consent_test.go` | **Modify** | Cover partition behavior. |
| `apps-microservices/mcp-gateway-service/internal/authserver/templates/consent.html` | **Modify** | New "Serveurs non configurés" block. |
| `apps-microservices/mcp-gateway-frontend/src/types/oauth2.ts` | **Modify** | `AuthorizeServer` gains `configured?: boolean` + `docs_url?: string`. |
| `apps-microservices/mcp-gateway-frontend/src/views/AuthorizeView.vue` | **Modify** | Render second section "Serveurs non configurés" with link button. |

---

## Task 1: New gateway value types

**Files:**
- Create: `apps-microservices/mcp-gateway-service/internal/gateway/zoho_state.go`

- [ ] **Step 1.1: Create the types file**

```go
package gateway

import "mcp-gateway/internal/mcp"

// ZohoCatalogState is what a ZohoUserCatalog implementation returns for a
// single viewer email. Configured == true iff the viewer's resolved
// zoho_imports row exists AND has at least one tool. Tools is non-empty
// only when Configured == true.
type ZohoCatalogState struct {
	Tools      []mcp.Tool
	Configured bool
}

// ZohoServerState is the per-Zoho-backend view rendered on the consent
// screen. Mirrors ZohoCatalogState but keyed by mcp_servers.id in the
// gateway's FetchZohoStateForUser response.
type ZohoServerState struct {
	Tools      []mcp.Tool
	Configured bool
}
```

- [ ] **Step 1.2: Run `go build ./...` to confirm the package compiles**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go build ./internal/gateway/...
```
Expected: no output (success).

- [ ] **Step 1.3: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/gateway/zoho_state.go
git commit -m "feat(mcp-gateway-service): zoho per-user catalog state types

Adds ZohoCatalogState and ZohoServerState value types used by the
upcoming StateForEmail interface and FetchZohoStateForUser gateway
method.

feat(mcp-gateway-service): types état catalogue Zoho par utilisateur

Ajoute les types valeur ZohoCatalogState et ZohoServerState
utilisés par la future interface StateForEmail et la méthode
FetchZohoStateForUser de la gateway."
```

---

## Task 2: Replace `ZohoUserCatalog` interface and gateway method (test first)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/gateway.go:25-33,82-88,182-239`
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/gateway_test.go`

- [ ] **Step 2.1: Write the failing test in `gateway_test.go`**

Append (or replace any existing `FetchZohoToolsForUser` block):

```go
// fakeZohoCatalog satisfies the new ZohoUserCatalog interface.
type fakeZohoCatalog struct {
	stateByEmail map[string]ZohoCatalogState
}

func (f *fakeZohoCatalog) StateForEmail(_ context.Context, email string) ZohoCatalogState {
	return f.stateByEmail[email]
}

func TestFetchZohoStateForUser_ConfiguredAdmin(t *testing.T) {
	reg := NewRegistry()
	reg.Register(&BackendServer{ID: "srv-zoho", ToolPrefix: "zoho"})
	reg.Register(&BackendServer{ID: "srv-other"})

	gw := New("test", "0", reg)
	gw.SetZohoUserCatalog(&fakeZohoCatalog{
		stateByEmail: map[string]ZohoCatalogState{
			"admin@hp.fr": {
				Tools:      []mcp.Tool{{Name: "admin_tool"}},
				Configured: true,
			},
		},
	})

	got := gw.FetchZohoStateForUser(context.Background(), "admin@hp.fr")

	if len(got) != 1 {
		t.Fatalf("want 1 zoho backend entry, got %d", len(got))
	}
	state, ok := got["srv-zoho"]
	if !ok {
		t.Fatalf("missing srv-zoho entry: %+v", got)
	}
	if !state.Configured {
		t.Fatalf("want Configured=true")
	}
	if len(state.Tools) != 1 || state.Tools[0].Name != "admin_tool" {
		t.Fatalf("want admin_tool, got %+v", state.Tools)
	}
	if _, leak := got["srv-other"]; leak {
		t.Fatalf("non-zoho backend leaked into result")
	}
}

func TestFetchZohoStateForUser_NotConfigured(t *testing.T) {
	reg := NewRegistry()
	reg.Register(&BackendServer{ID: "srv-zoho", ToolPrefix: "zoho"})

	gw := New("test", "0", reg)
	gw.SetZohoUserCatalog(&fakeZohoCatalog{
		stateByEmail: map[string]ZohoCatalogState{
			"alice@hp.fr": {Configured: false},
		},
	})

	got := gw.FetchZohoStateForUser(context.Background(), "alice@hp.fr")

	state, ok := got["srv-zoho"]
	if !ok {
		t.Fatalf("zoho backend must appear even when unconfigured")
	}
	if state.Configured {
		t.Fatalf("want Configured=false")
	}
	if len(state.Tools) != 0 {
		t.Fatalf("unconfigured state must carry no tools, got %d", len(state.Tools))
	}
}

func TestFetchZohoStateForUser_EmptyEmail(t *testing.T) {
	reg := NewRegistry()
	reg.Register(&BackendServer{ID: "srv-zoho", ToolPrefix: "zoho"})
	gw := New("test", "0", reg)
	gw.SetZohoUserCatalog(&fakeZohoCatalog{})

	if got := gw.FetchZohoStateForUser(context.Background(), ""); got != nil {
		t.Fatalf("empty email must return nil, got %+v", got)
	}
}
```

Make sure the test file's imports include `context` and `mcp-gateway/internal/mcp`.

- [ ] **Step 2.2: Run the new tests, confirm they fail**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run TestFetchZohoStateForUser -v
```
Expected: compile error `FetchZohoStateForUser undefined` (or similar).

- [ ] **Step 2.3: Replace the `ZohoUserCatalog` interface and method**

In `internal/gateway/gateway.go`, replace the existing `ZohoUserCatalog` block (currently lines ~25-33):

```go
// ZohoUserCatalog returns the per-viewer Zoho tool catalog state. The
// implementation MUST resolve the viewer's role first (admin vs non-admin)
// and consult only the appropriate zoho_imports row — there is no admin-row
// fallback for non-admin viewers. Configured == false means the row is
// missing (or has no tools); the consent screen renders this as
// "Non configuré" with a docs CTA.
type ZohoUserCatalog interface {
	StateForEmail(ctx context.Context, email string) ZohoCatalogState
}
```

Replace the `FetchZohoToolsForUser` doc comment + method body (currently lines ~182-239) with:

```go
// FetchZohoStateForUser returns the per-viewer Zoho state keyed by
// mcp_servers.id for every registered Zoho-tagged (or zoho-prefixed)
// backend. Each entry's Configured flag indicates whether the viewer
// has a usable zoho_imports row resolved (admin row for admins, user
// row for non-admins). Returns nil only when email is empty or no
// Zoho backend is registered.
//
// When SetZohoUserCatalog has been wired, state comes from the
// persisted zoho_import_tools table via the adapter. Otherwise the
// gateway returns a map where every Zoho backend is marked
// Configured=false (the live HTTP fallback is intentionally removed
// from the consent path — the persisted catalog is the only source
// of truth).
func (g *Gateway) FetchZohoStateForUser(ctx context.Context, email string) map[string]ZohoServerState {
	if email == "" {
		return nil
	}

	var zohoBackends []*BackendServer
	for _, srv := range g.registry.All() {
		if srv.HasTag("zoho") || srv.ToolPrefix == "zoho" {
			zohoBackends = append(zohoBackends, srv)
		}
	}
	if len(zohoBackends) == 0 {
		return nil
	}

	out := make(map[string]ZohoServerState, len(zohoBackends))
	if g.zohoCatalog == nil {
		for _, srv := range zohoBackends {
			out[srv.ID] = ZohoServerState{Configured: false}
		}
		log.Printf("[gateway] consent zoho catalog unwired email=%s — marking all backends unconfigured", email)
		return out
	}

	st := g.zohoCatalog.StateForEmail(ctx, email)
	for _, srv := range zohoBackends {
		out[srv.ID] = ZohoServerState{
			Tools:      st.Tools,
			Configured: st.Configured,
		}
	}
	if st.Configured {
		log.Printf("[gateway] consent zoho catalog email=%s configured=true tool_count=%d", email, len(st.Tools))
	} else {
		log.Printf("[gateway] consent zoho catalog email=%s configured=false — docs CTA", email)
	}
	return out
}
```

Also update the `SetZohoUserCatalog` doc comment (currently lines ~82-88):

```go
// SetZohoUserCatalog wires the persisted per-viewer Zoho catalog source.
// When set, FetchZohoStateForUser asks the implementation whether the
// viewer's zoho_imports row resolves and what its tools are. Pass nil
// to disable per-viewer resolution (every Zoho backend then renders as
// "Non configuré").
func (g *Gateway) SetZohoUserCatalog(c ZohoUserCatalog) {
	g.zohoCatalog = c
}
```

Remove the now-unused `strings` and `transport` imports if no other code in `gateway.go` uses them. Run `goimports` or check manually; do not delete imports still referenced elsewhere in the file.

- [ ] **Step 2.4: Run the gateway tests, confirm green**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -run TestFetchZohoStateForUser -v
```
Expected: all three PASS.

- [ ] **Step 2.5: Run the full gateway package suite**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/gateway/ -count=1
```
Expected: PASS (no other test depends on `FetchZohoToolsForUser`; if any does, fix it now — they were consent-only).

- [ ] **Step 2.6: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/gateway/gateway.go apps-microservices/mcp-gateway-service/internal/gateway/gateway_test.go
git commit -m "feat(mcp-gateway-service): replace ToolsForEmail with StateForEmail

FetchZohoToolsForUser becomes FetchZohoStateForUser, returning the
per-backend ZohoServerState (Tools + Configured). The interface
ZohoUserCatalog drops ToolsForEmail and gains StateForEmail.
The live-HTTP fallback for the consent path is removed; the
persisted catalog is now the only source of truth for the consent
screen.

feat(mcp-gateway-service): remplace ToolsForEmail par StateForEmail

FetchZohoToolsForUser devient FetchZohoStateForUser et renvoie le
ZohoServerState par backend (Tools + Configured). L'interface
ZohoUserCatalog perd ToolsForEmail au profit de StateForEmail. Le
fallback HTTP live pour le consentement est supprimé : le
catalogue persisté est désormais l'unique source de vérité."
```

---

## Task 3: Adapter `StateForEmail` with role-based resolution (test first)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/app/zoho_catalog_adapter.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/app/zoho_catalog_adapter_test.go`

- [ ] **Step 3.1: Read the existing test file**

Run:
```bash
sed -n '1,140p' apps-microservices/mcp-gateway-service/internal/app/zoho_catalog_adapter_test.go
```

You need to understand the existing fake imports repo + how the test seeds rows. Keep that scaffolding.

- [ ] **Step 3.2: Write new failing tests**

Append (or replace the existing test cases) so the test file covers exactly these cases. Helper `userFinder` is a new minimal fake — define it in the same test file.

```go
// fakeUserFinder satisfies the role-resolution dependency used by the
// adapter. Returns a *db.GatewayUser whose Role is the configured one
// for the given email; nil when the email is unknown.
type fakeUserFinder struct {
	byEmail map[string]string // email -> role
}

func (f *fakeUserFinder) GetByEmail(email string) (*db.GatewayUser, error) {
	if f == nil {
		return nil, nil
	}
	role, ok := f.byEmail[email]
	if !ok {
		return nil, nil
	}
	return &db.GatewayUser{Email: email, Role: role}, nil
}

func TestZohoCatalogAdapter_StateForEmail_AdminWithRow(t *testing.T) {
	imports := newFakeZohoImportRepo(t)
	imports.seedAdmin(t, "admin-id", []db.ZohoImportTool{{Name: "admin_tool"}})

	a := &zohoCatalogAdapter{
		imports: imports,
		users:   &fakeUserFinder{byEmail: map[string]string{"admin@hp.fr": "admin"}},
	}

	st := a.StateForEmail(context.Background(), "admin@hp.fr")

	if !st.Configured {
		t.Fatalf("admin with admin row must be Configured")
	}
	if len(st.Tools) != 1 || st.Tools[0].Name != "admin_tool" {
		t.Fatalf("want admin_tool, got %+v", st.Tools)
	}
}

func TestZohoCatalogAdapter_StateForEmail_AdminWithoutRow(t *testing.T) {
	imports := newFakeZohoImportRepo(t) // no admin row seeded

	a := &zohoCatalogAdapter{
		imports: imports,
		users:   &fakeUserFinder{byEmail: map[string]string{"admin@hp.fr": "admin"}},
	}

	st := a.StateForEmail(context.Background(), "admin@hp.fr")

	if st.Configured {
		t.Fatalf("admin without admin row must be Configured=false")
	}
	if len(st.Tools) != 0 {
		t.Fatalf("unconfigured state must carry no tools")
	}
}

func TestZohoCatalogAdapter_StateForEmail_NonAdminWithRow(t *testing.T) {
	imports := newFakeZohoImportRepo(t)
	imports.seedAdmin(t, "admin-id", []db.ZohoImportTool{{Name: "admin_tool"}})
	imports.seedUser(t, "user-id", "alice@hp.fr", []db.ZohoImportTool{{Name: "alice_tool"}})

	a := &zohoCatalogAdapter{
		imports: imports,
		users:   &fakeUserFinder{byEmail: map[string]string{"alice@hp.fr": "user"}},
	}

	st := a.StateForEmail(context.Background(), "alice@hp.fr")

	if !st.Configured {
		t.Fatalf("non-admin with user row must be Configured=true")
	}
	if len(st.Tools) != 1 || st.Tools[0].Name != "alice_tool" {
		t.Fatalf("want alice_tool, got %+v", st.Tools)
	}
}

func TestZohoCatalogAdapter_StateForEmail_NonAdminWithoutRow_NoAdminFallback(t *testing.T) {
	imports := newFakeZohoImportRepo(t)
	imports.seedAdmin(t, "admin-id", []db.ZohoImportTool{{Name: "admin_tool"}})

	a := &zohoCatalogAdapter{
		imports: imports,
		users:   &fakeUserFinder{byEmail: map[string]string{"bob@hp.fr": "user"}},
	}

	st := a.StateForEmail(context.Background(), "bob@hp.fr")

	if st.Configured {
		t.Fatalf("non-admin without user row must NOT fall back to admin row (got Configured=true)")
	}
	if len(st.Tools) != 0 {
		t.Fatalf("non-admin without user row must NOT see admin tools (got %+v)", st.Tools)
	}
}

func TestZohoCatalogAdapter_StateForEmail_UnknownUserTreatedAsNonAdmin(t *testing.T) {
	imports := newFakeZohoImportRepo(t)
	imports.seedAdmin(t, "admin-id", []db.ZohoImportTool{{Name: "admin_tool"}})

	a := &zohoCatalogAdapter{
		imports: imports,
		users:   &fakeUserFinder{}, // no users mapped
	}

	st := a.StateForEmail(context.Background(), "stranger@hp.fr")

	if st.Configured {
		t.Fatalf("unknown user must default to non-admin and NOT fall back to admin (got Configured=true)")
	}
}

func TestZohoCatalogAdapter_StateForEmail_EmptyEmail(t *testing.T) {
	a := &zohoCatalogAdapter{
		imports: newFakeZohoImportRepo(t),
		users:   &fakeUserFinder{},
	}
	if st := a.StateForEmail(context.Background(), ""); st.Configured || len(st.Tools) > 0 {
		t.Fatalf("empty email must return zero state")
	}
}

func TestZohoCatalogAdapter_StateForEmail_RowExistsButNoTools(t *testing.T) {
	imports := newFakeZohoImportRepo(t)
	imports.seedUser(t, "user-id", "alice@hp.fr", nil) // row but no tools

	a := &zohoCatalogAdapter{
		imports: imports,
		users:   &fakeUserFinder{byEmail: map[string]string{"alice@hp.fr": "user"}},
	}

	st := a.StateForEmail(context.Background(), "alice@hp.fr")

	if st.Configured {
		t.Fatalf("row without tools must be Configured=false")
	}
}
```

If the existing test file already uses a concrete `*repository.ZohoImportRepo` against SQLite, keep that pattern: replace the `newFakeZohoImportRepo`/`seedAdmin`/`seedUser` helpers in the snippet above with the existing seed helpers used by the file (read the file first to find them). The semantic intent of each test is what matters; the seeding mechanism is whatever the file already uses.

Delete any existing test that asserted the old "non-admin → admin row fallback" behavior — that behavior is being removed by design.

- [ ] **Step 3.3: Run the tests, confirm they fail**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/app/ -run TestZohoCatalogAdapter_StateForEmail -v
```
Expected: compile error (`StateForEmail undefined`, `users field undefined`, `fakeUserFinder` defined but `users` not on struct, etc.).

- [ ] **Step 3.4: Rewrite the adapter**

Overwrite `internal/app/zoho_catalog_adapter.go` with:

```go
package app

import (
	"context"
	"log"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/repository"
)

// userFinder is the slice of *repository.UserRepo the adapter needs to
// resolve the viewer's role. Defining it as an interface lets unit tests
// substitute an in-memory fake without spinning up GORM.
type userFinder interface {
	GetByEmail(email string) (*db.GatewayUser, error)
}

// zohoCatalogAdapter wraps ZohoImportRepo + UserRepo to satisfy
// gateway.ZohoUserCatalog.
//
// Resolution order:
//   - role == "admin"  → imports.GetAdmin()
//   - role != "admin"  → imports.FindUserImportByEmail(email)
//
// There is no admin-row fallback for non-admin viewers — that was the
// pre-2026-05-14 behavior that leaked admin tools onto every non-admin
// consent screen and is now intentionally removed.
//
// On any UserRepo error, the viewer is treated as non-admin (fail-safe:
// never auto-promote on transient DB errors).
type zohoCatalogAdapter struct {
	imports *repository.ZohoImportRepo
	users   userFinder
}

func (a *zohoCatalogAdapter) StateForEmail(_ context.Context, email string) gateway.ZohoCatalogState {
	if a == nil || a.imports == nil || email == "" {
		return gateway.ZohoCatalogState{}
	}

	isAdmin := false
	if a.users != nil {
		user, err := a.users.GetByEmail(email)
		if err != nil {
			log.Printf("[zoho-catalog] user lookup email=%s err=%v — treating as non-admin", email, err)
		} else if user != nil && user.Role == "admin" {
			isAdmin = true
		}
	}

	var row *db.ZohoImport
	var err error
	if isAdmin {
		row, err = a.imports.GetAdmin()
		if err != nil {
			log.Printf("[zoho-catalog] admin lookup err=%v email=%s", err, email)
		}
	} else {
		row, err = a.imports.FindUserImportByEmail(email)
		if err != nil {
			log.Printf("[zoho-catalog] user import lookup email=%s err=%v", email, err)
		}
	}
	if row == nil {
		return gateway.ZohoCatalogState{Configured: false}
	}

	tools, err := a.imports.ListTools(row.ID)
	if err != nil {
		log.Printf("[zoho-catalog] list tools import=%s err=%v", row.ID, err)
		return gateway.ZohoCatalogState{Configured: false}
	}
	if len(tools) == 0 {
		return gateway.ZohoCatalogState{Configured: false}
	}

	out := make([]mcp.Tool, 0, len(tools))
	for _, t := range tools {
		out = append(out, mcp.Tool{
			Name:        t.Name,
			Description: t.Description,
			InputSchema: t.InputSchema,
			IsActive:    true,
		})
	}
	return gateway.ZohoCatalogState{Tools: out, Configured: true}
}
```

- [ ] **Step 3.5: Run the tests, confirm green**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/app/ -run TestZohoCatalogAdapter_StateForEmail -v
```
Expected: all PASS.

- [ ] **Step 3.6: Run the whole app package**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/app/ -count=1
```
Expected: PASS.

- [ ] **Step 3.7: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/app/zoho_catalog_adapter.go apps-microservices/mcp-gateway-service/internal/app/zoho_catalog_adapter_test.go
git commit -m "feat(mcp-gateway-service): role-based zoho catalog resolution

The adapter now consults gateway_users.role first: admin viewers
resolve against the admin zoho_imports row, non-admin viewers
resolve against their own row only. The admin-row fallback for
non-admin viewers is removed — non-admin without a row returns
Configured=false so the consent screen surfaces a docs CTA.

feat(mcp-gateway-service): résolution catalogue Zoho par rôle

L'adaptateur consulte d'abord gateway_users.role : un admin
résout sur la ligne admin de zoho_imports, un non-admin résout
sur sa propre ligne uniquement. Le fallback vers la ligne admin
pour les non-admins est supprimé — un non-admin sans ligne
renvoie Configured=false pour afficher un CTA vers la doc."
```

---

## Task 4: Wire `UserRepo` into adapter constructor

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/app/app.go:390`

- [ ] **Step 4.1: Update the adapter construction in `app.go`**

Locate the line:

```go
gw.SetZohoUserCatalog(&zohoCatalogAdapter{imports: zohoImportRepo})
```

Replace with:

```go
gw.SetZohoUserCatalog(&zohoCatalogAdapter{imports: zohoImportRepo, users: dbs.userRepo})
```

- [ ] **Step 4.2: Build the binary to confirm wiring compiles**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go build ./...
```
Expected: no output.

- [ ] **Step 4.3: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/app/app.go
git commit -m "feat(mcp-gateway-service): inject UserRepo into zoho catalog adapter

Lets the adapter resolve the viewer's gateway_users role before
deciding which zoho_imports row to read.

feat(mcp-gateway-service): injection UserRepo dans l'adaptateur Zoho

Permet à l'adaptateur de résoudre le rôle (gateway_users) du
viewer avant de choisir la ligne zoho_imports à lire."
```

---

## Task 5: Update authserver interface + `DocsURL` config field

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/authserver/handler.go:13-72`
- Modify: `apps-microservices/mcp-gateway-service/internal/authserver/authorize_api.go:17-26`

- [ ] **Step 5.1: Replace the `ZohoToolsForUser` interface in `authorize_api.go`**

Replace the existing interface block (lines ~17-26):

```go
// ZohoStateForUser is the optional dependency that buildServerList uses
// to render Zoho-tagged servers on the consent screen. Returns the
// per-backend state keyed by mcp_servers.id. A Configured=false entry
// means the viewer's zoho_imports row is missing — the consent screen
// moves the server into the "Non configurés" section with a docs CTA.
type ZohoStateForUser interface {
	FetchZohoStateForUser(ctx context.Context, email string) map[string]gateway.ZohoServerState
}
```

Add the import:

```go
import (
	// ... existing imports ...
	"mcp-gateway/internal/gateway"
)
```

- [ ] **Step 5.2: Update `AuthServer` struct + config in `handler.go`**

Replace the `zohoFetcher` field type:

```go
// zohoFetcher (optional) — when set, the consent screen partitions
// servers into "Configurés"/"Non configurés" using each backend's
// per-viewer ZohoServerState.Configured flag.
zohoFetcher ZohoStateForUser
```

Add a `docsURL` field beside it:

```go
// docsURL is the absolute URL surfaced in the "Non configurés"
// section so viewers know where to learn how to wire their Zoho
// import. Computed from GATEWAY_PUBLIC_URL + "/docs/zohocrm" at
// boot.
docsURL string
```

Update `AuthServerConfig`:

```go
ZohoFetcher ZohoStateForUser // optional, partitions consent screen per viewer
DocsURL     string           // optional, populated when GATEWAY_PUBLIC_URL is set
```

Update `NewAuthServer` to copy the new field:

```go
return &AuthServer{
	// ... existing assignments ...
	zohoFetcher: cfg.ZohoFetcher,
	docsURL:     cfg.DocsURL,
	// ...
}
```

- [ ] **Step 5.3: Update the gateway construction call site in `app.go`**

Find the `authserver.NewAuthServer(authserver.AuthServerConfig{...})` call (around `app.go:415`). Inside the struct literal, add (or update if already present):

```go
ZohoFetcher: gw,                                                   // *Gateway satisfies ZohoStateForUser
DocsURL:     strings.TrimRight(cfg.GatewayPublicURL, "/") + "/docs/zohocrm",
```

Verify the existing `ZohoFetcher: gw,` assignment is still in the struct (it was passing the legacy interface). If it's already `ZohoFetcher: gw`, the only change is the new `DocsURL` line. Add `"strings"` to imports if not already present.

- [ ] **Step 5.4: Build to confirm everything still compiles**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go build ./...
```
Expected: no output. If any caller of the old `FetchZohoToolsForUser` remains, the compiler will point it out — fix by switching to `FetchZohoStateForUser`.

- [ ] **Step 5.5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/authserver/handler.go apps-microservices/mcp-gateway-service/internal/authserver/authorize_api.go apps-microservices/mcp-gateway-service/internal/app/app.go
git commit -m "feat(mcp-gateway-service): authserver consumes ZohoStateForUser + DocsURL

The consent layer now reads the per-viewer Configured flag and
materializes the docs CTA URL from GATEWAY_PUBLIC_URL.

feat(mcp-gateway-service): authserver consomme ZohoStateForUser + DocsURL

La couche consentement lit le drapeau Configured par viewer et
calcule l'URL de doc CTA à partir de GATEWAY_PUBLIC_URL."
```

---

## Task 6: DTO + JSON API partition (test first)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/authserver/authorize_api.go:38-47,489-547`
- Modify: `apps-microservices/mcp-gateway-service/internal/authserver/authorize_api_test.go`

- [ ] **Step 6.1: Write the failing tests**

In `authorize_api_test.go`, add (or replace the existing applyZohoUserTools tests with):

```go
type fakeZohoState struct {
	stateByEmail map[string]map[string]gateway.ZohoServerState
}

func (f *fakeZohoState) FetchZohoStateForUser(_ context.Context, email string) map[string]gateway.ZohoServerState {
	return f.stateByEmail[email]
}

func TestApplyZohoUserState_ConfiguredServerKeepsTools(t *testing.T) {
	in := []authorizeServerDTO{{
		ID:   "srv-zoho",
		Name: "Zoho",
		Tools: []authorizeToolDTO{{Name: "admin_tool"}},
	}}
	zohoIDs := map[string]bool{"srv-zoho": true}
	fetcher := &fakeZohoState{stateByEmail: map[string]map[string]gateway.ZohoServerState{
		"alice@hp.fr": {"srv-zoho": {
			Tools:      []mcp.Tool{{Name: "alice_tool"}},
			Configured: true,
		}},
	}}

	out := applyZohoUserState(context.Background(), in, zohoIDs, fetcher, "alice@hp.fr", "https://docs/zohocrm")

	if len(out) != 1 {
		t.Fatalf("want 1 entry, got %d", len(out))
	}
	if !out[0].Configured {
		t.Fatalf("Configured must be true on the in-place server")
	}
	if out[0].DocsURL != "" {
		t.Fatalf("DocsURL must be empty when Configured=true, got %q", out[0].DocsURL)
	}
	if len(out[0].Tools) != 1 || out[0].Tools[0].Name != "alice_tool" {
		t.Fatalf("want alice_tool, got %+v", out[0].Tools)
	}
}

func TestApplyZohoUserState_UnconfiguredServerGetsDocsURL(t *testing.T) {
	in := []authorizeServerDTO{{
		ID:    "srv-zoho",
		Name:  "Zoho",
		Tools: []authorizeToolDTO{{Name: "admin_tool"}},
	}}
	zohoIDs := map[string]bool{"srv-zoho": true}
	fetcher := &fakeZohoState{stateByEmail: map[string]map[string]gateway.ZohoServerState{
		"bob@hp.fr": {"srv-zoho": {Configured: false}},
	}}

	out := applyZohoUserState(context.Background(), in, zohoIDs, fetcher, "bob@hp.fr", "https://docs/zohocrm")

	if out[0].Configured {
		t.Fatalf("Configured must be false")
	}
	if out[0].DocsURL != "https://docs/zohocrm" {
		t.Fatalf("DocsURL must be the supplied value, got %q", out[0].DocsURL)
	}
	if len(out[0].Tools) != 0 {
		t.Fatalf("unconfigured server must carry no tools, got %+v", out[0].Tools)
	}
}

func TestApplyZohoUserState_NonZohoUntouched(t *testing.T) {
	in := []authorizeServerDTO{{
		ID:    "srv-other",
		Name:  "Other",
		Tools: []authorizeToolDTO{{Name: "x"}},
	}}
	zohoIDs := map[string]bool{} // none
	fetcher := &fakeZohoState{}

	out := applyZohoUserState(context.Background(), in, zohoIDs, fetcher, "alice@hp.fr", "https://docs/zohocrm")

	if out[0].Configured {
		t.Fatalf("non-Zoho server must not get Configured flag set")
	}
	if out[0].DocsURL != "" {
		t.Fatalf("non-Zoho server must not get DocsURL set")
	}
	if len(out[0].Tools) != 1 {
		t.Fatalf("non-Zoho server tools must be untouched")
	}
}

func TestApplyZohoUserState_NilFetcherLeavesInputAlone(t *testing.T) {
	in := []authorizeServerDTO{{
		ID:    "srv-zoho",
		Name:  "Zoho",
		Tools: []authorizeToolDTO{{Name: "admin_tool"}},
	}}
	zohoIDs := map[string]bool{"srv-zoho": true}

	out := applyZohoUserState(context.Background(), in, zohoIDs, nil, "alice@hp.fr", "https://docs/zohocrm")

	if out[0].Configured || out[0].DocsURL != "" {
		t.Fatalf("nil fetcher must leave Configured/DocsURL unset, got %+v", out[0])
	}
	if len(out[0].Tools) != 1 {
		t.Fatalf("nil fetcher must leave tools intact")
	}
}
```

Ensure the test file imports `"context"`, `"mcp-gateway/internal/gateway"`, `"mcp-gateway/internal/mcp"`.

Remove any old tests for `applyZohoUserTools` that asserted "fail-open keep admin tools" behavior — that is no longer the semantic.

- [ ] **Step 6.2: Run the tests, confirm they fail**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/authserver/ -run TestApplyZohoUserState -v
```
Expected: compile error (`applyZohoUserState undefined`, `Configured undefined on authorizeServerDTO`, etc.).

- [ ] **Step 6.3: Update the DTO**

Replace the `authorizeServerDTO` struct in `authorize_api.go`:

```go
type authorizeServerDTO struct {
	ID         string             `json:"id"`
	Name       string             `json:"name"`
	Tools      []authorizeToolDTO `json:"tools"`
	Configured bool               `json:"configured"`
	DocsURL    string             `json:"docs_url,omitempty"`
}
```

- [ ] **Step 6.4: Replace `applyZohoUserTools` with `applyZohoUserState`**

Replace the existing function (lines ~515-547) with:

```go
// applyZohoUserState rewrites each Zoho-tagged server entry in-place using
// the per-viewer state returned by the fetcher. Configured servers get
// their Tools replaced with the viewer's tools and Configured=true.
// Unconfigured servers are emptied of tools, marked Configured=false, and
// receive the docs CTA URL. Non-Zoho servers and the nil-fetcher / empty
// email / no-Zoho-id cases are passthroughs. Pure function: testable
// without any AuthServer plumbing.
func applyZohoUserState(
	ctx context.Context,
	servers []authorizeServerDTO,
	zohoIDs map[string]bool,
	fetcher ZohoStateForUser,
	userEmail string,
	docsURL string,
) []authorizeServerDTO {
	if fetcher == nil || userEmail == "" || len(zohoIDs) == 0 {
		return servers
	}
	state := fetcher.FetchZohoStateForUser(ctx, userEmail)
	for i, srv := range servers {
		if !zohoIDs[srv.ID] {
			continue
		}
		st, ok := state[srv.ID]
		if !ok {
			// No entry returned: treat as unconfigured (fail-safe — never
			// leak the cached admin tools onto a non-admin consent screen).
			servers[i].Tools = nil
			servers[i].Configured = false
			servers[i].DocsURL = docsURL
			continue
		}
		if !st.Configured {
			servers[i].Tools = nil
			servers[i].Configured = false
			servers[i].DocsURL = docsURL
			continue
		}
		converted := make([]authorizeToolDTO, 0, len(st.Tools))
		for _, t := range st.Tools {
			converted = append(converted, authorizeToolDTO{
				Name:        t.Name,
				Description: t.Description,
			})
		}
		servers[i].Tools = converted
		servers[i].Configured = true
		servers[i].DocsURL = ""
	}
	return servers
}
```

Replace the call site in `buildServerList` (the existing `result = applyZohoUserTools(...)` line):

```go
result = applyZohoUserState(ctx, result, zohoIDs, s.zohoFetcher, userEmail, s.docsURL)
```

- [ ] **Step 6.5: Run the new tests**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/authserver/ -run TestApplyZohoUserState -v
```
Expected: all PASS.

- [ ] **Step 6.6: Run the full authserver package**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/authserver/ -count=1
```
Expected: PASS. If old tests that asserted "fail-open" behavior remain, delete them (they encode the discarded semantic).

- [ ] **Step 6.7: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/authserver/authorize_api.go apps-microservices/mcp-gateway-service/internal/authserver/authorize_api_test.go
git commit -m "feat(mcp-gateway-service): partition zoho servers on consent JSON API

authorizeServerDTO gains Configured + DocsURL. applyZohoUserState
replaces applyZohoUserTools: configured Zoho servers swap their
tools, unconfigured Zoho servers clear their tools and receive the
docs CTA URL. Non-Zoho servers are untouched.

feat(mcp-gateway-service): partition serveurs Zoho côté API consent

authorizeServerDTO gagne Configured + DocsURL.
applyZohoUserState remplace applyZohoUserTools : un serveur Zoho
configuré reçoit les outils du viewer, un serveur non configuré
voit ses outils vidés et reçoit l'URL CTA. Les serveurs non-Zoho
restent intacts."
```

---

## Task 7: Consent HTML rendering — partition into two sections (test first)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/authserver/authorize.go:212-353`
- Modify: `apps-microservices/mcp-gateway-service/internal/authserver/consent_test.go`

- [ ] **Step 7.1: Write the failing test**

Find an existing rendering helper or test entry point in `consent_test.go`. Add:

```go
func TestRenderConsent_PartitionsZohoUnconfigured(t *testing.T) {
	// Arrange: one Zoho server + one non-Zoho server; fake fetcher returns
	// Configured=false for the Zoho one.
	zohoSrv := db.MCPServer{ID: "srv-zoho", Name: "Zoho", ToolPrefix: "zoho"}
	otherSrv := db.MCPServer{ID: "srv-other", Name: "Other"}

	srvRepo := &fakeServerRepo{active: []db.MCPServer{zohoSrv, otherSrv}}
	fetcher := &fakeZohoState{stateByEmail: map[string]map[string]gateway.ZohoServerState{
		"alice@hp.fr": {
			"srv-zoho": {Configured: false},
		},
	}}

	s := &AuthServer{
		serverRepo:  srvRepo,
		consentRepo: &fakeConsentRepo{},
		zohoFetcher: fetcher,
		docsURL:     "https://gw.example/docs/zohocrm",
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/authorize?client_id=cid", nil)

	s.renderConsent(rec, req, &db.OAuth2Client{ID: "cid"}, &authorizeParams{}, "alice@hp.fr")

	body := rec.Body.String()
	if !strings.Contains(body, "Serveurs non configurés") {
		t.Fatalf("rendered body missing 'Serveurs non configurés' section: %s", body)
	}
	if !strings.Contains(body, "https://gw.example/docs/zohocrm") {
		t.Fatalf("rendered body missing docs URL")
	}
	// The Zoho server must appear in the unconfigured section, NOT in the
	// configured list — assert it doesn't show up with a checkbox.
	if strings.Count(body, `name="server_ids" value="srv-zoho"`) > 0 {
		t.Fatalf("unconfigured Zoho server must not render as a selectable checkbox")
	}
}

func TestRenderConsent_ConfiguredZohoStaysInMainList(t *testing.T) {
	zohoSrv := db.MCPServer{ID: "srv-zoho", Name: "Zoho", ToolPrefix: "zoho"}

	srvRepo := &fakeServerRepo{active: []db.MCPServer{zohoSrv}}
	fetcher := &fakeZohoState{stateByEmail: map[string]map[string]gateway.ZohoServerState{
		"admin@hp.fr": {
			"srv-zoho": {
				Tools:      []mcp.Tool{{Name: "admin_tool"}},
				Configured: true,
			},
		},
	}}

	s := &AuthServer{
		serverRepo:  srvRepo,
		consentRepo: &fakeConsentRepo{},
		zohoFetcher: fetcher,
		docsURL:     "https://gw.example/docs/zohocrm",
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/authorize?client_id=cid", nil)

	s.renderConsent(rec, req, &db.OAuth2Client{ID: "cid"}, &authorizeParams{}, "admin@hp.fr")

	body := rec.Body.String()
	if strings.Contains(body, "Serveurs non configurés") {
		t.Fatalf("admin with admin row must NOT see the unconfigured section")
	}
	if !strings.Contains(body, "admin_tool") {
		t.Fatalf("admin tools must appear in the main list")
	}
}
```

You'll need to ensure helpers exist (`fakeServerRepo`, `fakeConsentRepo`) and that `serverRepo` + `consentRepo` are abstracted as interfaces on `AuthServer` for the test to inject fakes — read the existing `consent_test.go` first to find how rendering is already tested. If the existing tests construct `AuthServer` differently, mirror that pattern. The two test functions above are the **behavioral contract**, not the literal template; adapt the test plumbing to whatever the file already uses.

- [ ] **Step 7.2: Run the tests to confirm they fail**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/authserver/ -run TestRenderConsent_Partitions -v
cd apps-microservices/mcp-gateway-service && go test ./internal/authserver/ -run TestRenderConsent_ConfiguredZoho -v
```
Expected: both FAIL — the template still lists Zoho as a checkbox row regardless of Configured.

- [ ] **Step 7.3: Update `renderConsent` to partition entries**

In `authorize.go`, inside `renderConsent`, replace the block that fetches `zohoUserTools` (currently lines ~229-234) with:

```go
// Per-viewer Zoho state — fetched once before iterating servers so we
// can route unconfigured Zoho backends into a dedicated section while
// keeping configured ones in the main list.
var zohoState map[string]gateway.ZohoServerState
if s.zohoFetcher != nil && userEmail != "" && len(zohoIDs) > 0 {
	zohoState = s.zohoFetcher.FetchZohoStateForUser(r.Context(), userEmail)
}
```

Add an `unconfigured` slice next to `entries`:

```go
var entries []serverEntry
var unconfigured []serverEntry
```

Inside both branches (`hasPreConfiguredScope` and dynamic), replace the existing per-Zoho swap logic:

```go
if zohoIDs[srv.ID] {
	st, ok := zohoState[srv.ID]
	if !ok || !st.Configured {
		unconfigured = append(unconfigured, serverEntry{
			ID:        srv.ID,
			Name:      srv.Name,
			ToolCount: 0,
		})
		continue
	}
	source = toServerTools(st.Tools)
}
```

— substituting `source` for whatever the surrounding loop assigns. Apply the same pattern in both branches so the partition holds regardless of pre-configured scope.

Update the `consentTmpl.Execute` map at the bottom of `renderConsent`:

```go
consentTmpl.Execute(w, map[string]interface{}{
	"ClientName":          client.Name,
	"ClientID":            params.ClientID,
	"RedirectURI":         params.RedirectURI,
	"CodeChallenge":       params.CodeChallenge,
	"CodeChallengeMethod": params.CodeChallengeMethod,
	"State":               params.State,
	"CSRFToken":           csrfToken,
	"Servers":             entries,
	"UnconfiguredServers": unconfigured,
	"DocsURL":             s.docsURL,
	"PreConfigured":       hasPreConfiguredScope,
})
```

Add the `gateway` import to `authorize.go` if not already present:

```go
import (
	// ... existing ...
	"mcp-gateway/internal/gateway"
)
```

- [ ] **Step 7.4: Update `consent.html` to render the new section**

Open `internal/authserver/templates/consent.html`. After the closing `{{end}}` of the existing `{{range .Servers}}` block (but still inside the `<form>`), add:

```html
      {{if .UnconfiguredServers}}
      <p class="text-xs text-gray-500 mt-4 mb-2">Serveurs non configurés :</p>
      <div class="border border-amber-200 rounded-lg bg-amber-50">
        {{range .UnconfiguredServers}}
        <div class="flex items-center justify-between px-3 py-2 border-b border-amber-100 last:border-b-0">
          <div class="flex items-center gap-2">
            <svg class="w-4 h-4 text-amber-500 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            <span class="text-sm font-medium text-gray-800">{{.Name}}</span>
            <span class="text-xs text-amber-700 px-1.5 py-0.5 rounded bg-amber-100">Non configuré</span>
          </div>
          {{if $.DocsURL}}
          <a href="{{$.DocsURL}}" target="_blank" rel="noopener noreferrer"
             class="text-xs font-medium text-brand-600 hover:underline">
            Voir documentation →
          </a>
          {{end}}
        </div>
        {{end}}
      </div>
      {{end}}
```

- [ ] **Step 7.5: Run the rendering tests**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/authserver/ -run TestRenderConsent -v
```
Expected: PASS.

- [ ] **Step 7.6: Run the full authserver suite + the gateway suite**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./... -count=1
```
Expected: PASS.

- [ ] **Step 7.7: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/authserver/authorize.go apps-microservices/mcp-gateway-service/internal/authserver/templates/consent.html apps-microservices/mcp-gateway-service/internal/authserver/consent_test.go
git commit -m "feat(mcp-gateway-service): consent HTML splits zoho into two sections

renderConsent partitions backends into Servers (configurés) and
UnconfiguredServers. The HTML template gains a 'Serveurs non
configurés' block carrying a CTA link to {{.DocsURL}}.

feat(mcp-gateway-service): consentement HTML scinde Zoho en deux sections

renderConsent partitionne les backends en Servers (configurés) et
UnconfiguredServers. Le template HTML gagne un bloc « Serveurs
non configurés » avec un lien CTA vers {{.DocsURL}}."
```

---

## Task 8: Frontend type changes

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/types/oauth2.ts:59-63`

- [ ] **Step 8.1: Update the TypeScript interface**

Replace the `AuthorizeServer` interface (lines 59-63):

```typescript
export interface AuthorizeServer {
  id: string
  name: string
  tools: AuthorizeTool[]
  configured?: boolean
  docs_url?: string
}
```

- [ ] **Step 8.2: Run the type-check**

Run:
```bash
cd apps-microservices/mcp-gateway-frontend && npm run build
```
Expected: build succeeds. (If `npm run build` is too slow, use `npx vue-tsc --noEmit`.)

- [ ] **Step 8.3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/types/oauth2.ts
git commit -m "feat(mcp-gateway-frontend): authorize DTO carries configured + docs_url

Mirrors the backend authorizeServerDTO additions so the consent
view can render the 'Non configurés' section.

feat(mcp-gateway-frontend): DTO authorize porte configured + docs_url

Reflète l'ajout backend authorizeServerDTO pour permettre à la
vue consentement de rendre la section « Non configurés »."
```

---

## Task 9: Frontend `AuthorizeView.vue` — render two sections

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/views/AuthorizeView.vue`

- [ ] **Step 9.1: Add computed filters near the existing `servers` ref**

In the `<script setup>` block, after `const servers = ref<AuthorizeServer[]>([])`, add:

```typescript
const configuredServers = computed(() =>
  servers.value.filter((s) => s.configured !== false),
)

const unconfiguredServers = computed(() =>
  servers.value.filter((s) => s.configured === false),
)
```

Make sure `computed` is imported from Vue (it likely already is — check the existing imports).

- [ ] **Step 9.2: Replace the existing `v-for="server in servers"` loop with `configuredServers`**

In the template, find the existing loop:

```html
v-for="server in servers"
```

Change it to:

```html
v-for="server in configuredServers"
```

That single change confines the existing checkbox+tools UI to the configured list.

- [ ] **Step 9.3: Add the unconfigured section after the existing list**

Find the closing `</div>` of the configured section and insert immediately after it:

```html
<div v-if="unconfiguredServers.length > 0" class="mt-4">
  <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">
    Serveurs non configurés :
  </p>
  <div class="border border-amber-200 dark:border-amber-700 rounded-lg bg-amber-50 dark:bg-amber-900/20 divide-y divide-amber-100 dark:divide-amber-800">
    <div
      v-for="server in unconfiguredServers"
      :key="server.id"
      class="flex items-center justify-between px-3 py-2"
    >
      <div class="flex items-center gap-2">
        <span class="text-sm font-medium text-gray-800 dark:text-gray-100">
          {{ server.name }}
        </span>
        <span class="text-xs text-amber-700 dark:text-amber-300 px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40">
          Non configuré
        </span>
      </div>
      <a
        v-if="server.docs_url"
        :href="server.docs_url"
        target="_blank"
        rel="noopener noreferrer"
        class="text-xs font-medium text-brand-600 hover:underline"
      >
        Voir documentation →
      </a>
    </div>
  </div>
</div>
```

- [ ] **Step 9.4: Run a type-check + dev build**

Run:
```bash
cd apps-microservices/mcp-gateway-frontend && npm run build
```
Expected: build succeeds without TS errors.

- [ ] **Step 9.5: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/views/AuthorizeView.vue
git commit -m "feat(mcp-gateway-frontend): split authorize view into two server sections

The OAuth2 consent screen now renders 'Serveurs disponibles' for
configured backends and 'Serveurs non configurés' (with a docs
CTA link) for unconfigured ones — driven by AuthorizeServer.configured.

feat(mcp-gateway-frontend): scinde la vue authorize en deux sections

L'écran de consentement OAuth2 affiche désormais « Serveurs
disponibles » pour les backends configurés et « Serveurs non
configurés » (avec lien CTA documentation) pour les autres —
piloté par AuthorizeServer.configured."
```

---

## Task 10: End-to-end smoke + service build

**Files:**
- No code changes — verification only.

- [ ] **Step 10.1: Run the full Go test suite**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./... -count=1
```
Expected: PASS across `internal/gateway`, `internal/app`, `internal/authserver`.

- [ ] **Step 10.2: Build the gateway binary**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go build ./cmd/server/
```
Expected: no output; `server` binary produced (or no error if `-o` not used).

- [ ] **Step 10.3: Build the frontend bundle**

Run:
```bash
cd apps-microservices/mcp-gateway-frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 10.4: Manual smoke checklist (record results in the PR description)**

Against a running gateway with `GATEWAY_PUBLIC_URL=https://mcp.example.eu` and a seeded admin Zoho row:

| Scenario | Expected |
|---|---|
| Admin user logs in, admin row exists | Consent main list shows Zoho with admin tools. No unconfigured section. |
| Admin user logs in, admin row deleted | Consent shows Zoho under "Serveurs non configurés" with link `https://mcp.example.eu/docs/zohocrm`. |
| Non-admin user logs in, no user row | Consent shows Zoho under "Serveurs non configurés" with the link. **Does NOT show admin tools.** |
| Non-admin user logs in, user row + tools imported | Consent main list shows Zoho with user's own tools. No unconfigured section. |
| Anonymous browser (no session) | Consent renders unchanged from before (no email → adapter returns zero state, all Zoho backends go to unconfigured section). |
| `client_credentials` grant | `/token` never hits consent — flow untouched. |

- [ ] **Step 10.5: Mark plan complete (no commit — verification only)**

If the smoke checklist passes, the feature is ready for review.

---

## Self-Review Notes (filled in during plan-writing pass)

- **Spec coverage:** every row in the spec's "Behavior matrix" maps to a Task 3 test (`AdminWithRow`, `AdminWithoutRow`, `NonAdminWithRow`, `NonAdminWithoutRow_NoAdminFallback`, `EmptyEmail`) plus a Task 7 rendering test. JSON DTO additions are exercised in Task 6. Docs URL surfacing covered in Tasks 5 + 7 + 9.
- **Placeholder scan:** no TBDs. All code blocks contain the actual content the engineer needs.
- **Type consistency:** `ZohoCatalogState` (adapter return) vs `ZohoServerState` (gateway map value) — kept as separate types per the spec, both with identical `{Tools, Configured}` shape. `applyZohoUserState` lower-cases the docs URL parameter consistently. JSON field `configured` (lowercase) ↔ Go field `Configured` ↔ TS field `configured` — all aligned.
- **Removed legacy:** all references to `FetchZohoToolsForUser`, `ToolsForEmail`, `applyZohoUserTools`, and the live-HTTP consent fallback removed in the same commits that introduce the replacements — no dead code left.

