# mcp-gateway Auto Per-User Filter Override Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an OAuth2 access token carries an end-user email claim and that email maps to a Leexi/Ringover user, automatically scope outbound MCP requests to that user's UUID/ID — bypassing whatever filter mode the admin configured on the OAuth2 client. Non-admin users without a matching backend account are denied; gateway admins fall back to the admin-configured mode. Per-backend independent (a user might exist in Leexi but not Ringover).

**Architecture:** Three-step resolution at `inject{Leexi,Ringover}Header`:
1. No email in context (client_credentials grant) → fall through to existing admin-configured filter resolution.
2. Email maps to a backend user → return `[user.UUID]`/`[user.UserID]` (auto-self override; admin config bypassed).
3. Email present but no match in this specific backend → check gateway-admin role: admin → fall through to admin config; non-admin → deny-sentinel (fail-closed).

`ScopedGateway` gains an optional `gatewayUserFinder` (interface satisfied by `repository.UserRepo`) used only for the admin-role lookup in step 3.

The existing explicit `mode='self'` admin opt-in remains supported and behavior-identical — the new auto-override subsumes it but doesn't break it.

**Tech Stack:** Go 1.24, existing `internal/leexiadmin`, `internal/ringoveradmin`, `internal/repository.UserRepo`, `internal/auth.RoleAdmin`.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go` | Add `gatewayUserFinder` field. New helper `resolveAutoSelfOverride(ctx, kind)` returns `(uuid string, fallbackToConfig bool, ok bool)` per backend. Refactor `injectLeexiHeader` and `injectRingoverHeader` to call the helper first. |
| `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_test.go` | New test file scenarios: non-admin user-found-leexi, non-admin user-missing-leexi-deny, admin user-found, admin user-missing-fallback-to-config, no-email-falls-through, per-backend independence (user in Leexi but not Ringover). |
| `apps-microservices/mcp-gateway-service/internal/gateway/gateway.go` | Add `gatewayUserFinder` field on `Gateway`. New setter `SetGatewayUserFinder(*repository.UserRepo)` (or interface-typed). Propagate to `NewScopedGateway` so the field is non-nil at request time when configured. |
| `apps-microservices/mcp-gateway-service/internal/app/app.go` | Wire the existing `dbStack.userRepo` into the `Gateway` via the new setter at boot. |
| `apps-microservices/mcp-gateway-service/CLAUDE.md` | Document the auto-override semantics and the per-backend fallback rule. |

No DB schema changes. No frontend changes. No new dependencies.

---

## Task 1: Add `gatewayUserFinder` Interface + Field on Gateway/ScopedGateway

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/gateway.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go`

The interface mirrors `*repository.UserRepo.GetByEmail` so tests can substitute an in-memory fake.

- [ ] **Step 1: Define the interface and add the field**

In `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go`, near the existing `BDDTableResolver` declaration (or wherever other interface types live in the package), add:

```go
// gatewayUserFinder abstracts the slice of *repository.UserRepo that the
// auto-self override needs (admin-role lookup by email). Defining it as an
// interface lets tests substitute an in-memory fake without spinning up GORM.
type gatewayUserFinder interface {
	GetByEmail(email string) (*db.GatewayUser, error)
}
```

Add the import for `mcp-gateway/internal/db` if not already present.

In `internal/gateway/gateway.go`, locate the `Gateway` struct. Add the new field (place near `leexiAdmin`/`ringoverAdmin` for grouping):

```go
type Gateway struct {
	// ... existing fields ...
	leexiAdmin    *leexiadmin.Client
	ringoverAdmin *ringoveradmin.Client
	bddResolver   BDDTableResolver
	// gatewayUsers (optional) is consulted by auto-self override to learn
	// whether an authenticated end-user is a gateway admin. nil disables the
	// admin-fallback branch — non-admin behavior applies to everyone.
	gatewayUsers gatewayUserFinder
}
```

Add the setter, mirroring `SetLeexiAdmin` style:

```go
// SetGatewayUserFinder registers the user finder used by auto-self override
// to detect gateway admins. Pass *repository.UserRepo at boot.
func (g *Gateway) SetGatewayUserFinder(f gatewayUserFinder) {
	g.gatewayUsers = f
}
```

In `internal/gateway/scoped_gateway.go`, add the field on `ScopedGateway`:

```go
type ScopedGateway struct {
	// ... existing fields ...
	leexiAdmin    *leexiadmin.Client
	ringoverAdmin *ringoveradmin.Client
	bddResolver   BDDTableResolver
	gatewayUsers  gatewayUserFinder
}
```

Update `NewScopedGateway` to copy the field from the parent `Gateway`:

```go
func NewScopedGateway(gw *Gateway, allowedServerIDs map[string]bool, allowedTools map[string]map[string]bool, instructions []InstructionView) *ScopedGateway {
	return &ScopedGateway{
		name:          gw.name,
		version:       gw.version,
		registry:      gw.registry,
		allowedIDs:    allowedServerIDs,
		allowedTools:  allowedTools,
		instructions:  instructions,
		leexiAdmin:    gw.leexiAdmin,
		ringoverAdmin: gw.ringoverAdmin,
		bddResolver:   gw.bddResolver,
		gatewayUsers:  gw.gatewayUsers,
	}
}
```

- [ ] **Step 2: Build and verify**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./..."
```

Expected: clean. (No tests yet — Task 2 covers behavior.)

- [ ] **Step 3: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB
git add apps-microservices/mcp-gateway-service/internal/gateway/gateway.go \
        apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go
git commit -m "feat(mcp-gateway): add gatewayUserFinder plumbing for auto-self override"
```

---

## Task 2: Implement Auto-Self Override in Header Injectors

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go`
- Create: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_auto_self_test.go`

The override runs before the existing mode-based resolution. Behavior matrix:

| email present? | backend user found? | gateway admin? | Outcome |
|---|---|---|---|
| no (client_creds) | — | — | use admin-configured mode (existing path) |
| yes | yes | — | inject `[user.UUID/ID]` (override admin config) |
| yes | no | yes | use admin-configured mode (admin fallback) |
| yes | no | no | deny-sentinel (fail-closed) |

The matrix is identical for Leexi and Ringover but evaluated independently per backend.

- [ ] **Step 1: Write the failing tests**

Create `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_auto_self_test.go`:

```go
package gateway

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/leexiadmin"
	"mcp-gateway/internal/ringoveradmin"
	"mcp-gateway/internal/scopetoken"
)

// fakeUserRepo lets the auto-self-override tests stub gateway_users lookups
// without touching GORM. Only GetByEmail is exercised.
type fakeUserRepo struct {
	rows map[string]*db.GatewayUser
}

func (f *fakeUserRepo) GetByEmail(email string) (*db.GatewayUser, error) {
	if u, ok := f.rows[email]; ok {
		return u, nil
	}
	return nil, errors.New("not found")
}

func leexiServerWithAlice(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasSuffix(r.URL.Path, "/admin/users") {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"users":[{"uuid":"u-alice","email":"alice@example.com"}]}`))
	}))
}

func ringoverServerWithBob(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasSuffix(r.URL.Path, "/admin/users") {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"users":[{"user_id":7,"email":"bob@example.com"}]}`))
	}))
}

func ctxWithEmail(email string) context.Context {
	return context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, email)
}

// 1. JWT carries email + Leexi user matches → override admin config (mode=users).
func TestInjectLeexiHeader_AutoSelfOverridesUsersMode(t *testing.T) {
	srv := leexiServerWithAlice(t)
	defer srv.Close()

	sg := &ScopedGateway{leexiAdmin: leexiadmin.NewClient(srv.URL, "tok")}
	ctx := ctxWithEmail("alice@example.com")
	// Admin configured a fixed user list — the override should replace it.
	ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
		Mode:             "users",
		AllowedUserUUIDs: []string{"u-bob", "u-charlie"},
	})
	headers := map[string]string{}
	sg.injectLeexiHeader(ctx, headers)
	if got := headers[LeexiAllowedParticipantsHeader]; got != "u-alice" {
		t.Fatalf("expected u-alice, got %q", got)
	}
}

// 2. JWT email present, no Leexi match, end-user is NOT a gateway admin → deny.
func TestInjectLeexiHeader_NonAdminEmailMissingDeniesAll(t *testing.T) {
	srv := leexiServerWithAlice(t)
	defer srv.Close()

	sg := &ScopedGateway{
		leexiAdmin:   leexiadmin.NewClient(srv.URL, "tok"),
		gatewayUsers: &fakeUserRepo{}, // empty: ghost@ is not in gateway_users
	}
	ctx := ctxWithEmail("ghost@example.com")
	ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
		Mode:             "users",
		AllowedUserUUIDs: []string{"u-bob"},
	})
	headers := map[string]string{}
	sg.injectLeexiHeader(ctx, headers)
	if got := headers[LeexiAllowedParticipantsHeader]; got != "00000000-0000-0000-0000-000000000000" {
		t.Fatalf("expected deny-sentinel, got %q", got)
	}
}

// 3. JWT email present, no Leexi match, end-user IS a gateway admin → fall
// back to admin-configured filter (mode=users yields the admin's list).
func TestInjectLeexiHeader_AdminEmailMissingFallsBackToConfig(t *testing.T) {
	srv := leexiServerWithAlice(t)
	defer srv.Close()

	sg := &ScopedGateway{
		leexiAdmin: leexiadmin.NewClient(srv.URL, "tok"),
		gatewayUsers: &fakeUserRepo{rows: map[string]*db.GatewayUser{
			"sysadmin@example.com": {Email: "sysadmin@example.com", Role: auth.RoleAdmin},
		}},
	}
	ctx := ctxWithEmail("sysadmin@example.com") // admin, not in Leexi
	ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
		Mode:             "users",
		AllowedUserUUIDs: []string{"u-bob", "u-charlie"},
	})
	headers := map[string]string{}
	sg.injectLeexiHeader(ctx, headers)
	if got := headers[LeexiAllowedParticipantsHeader]; got != "u-bob,u-charlie" {
		t.Fatalf("expected admin's list, got %q", got)
	}
}

// 4. No email (client_credentials grant) → use admin-configured filter as
// before, no auto-override applied.
func TestInjectLeexiHeader_NoEmailFallsThroughToConfig(t *testing.T) {
	sg := &ScopedGateway{}
	ctx := context.WithValue(context.Background(), scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
		Mode:             "users",
		AllowedUserUUIDs: []string{"u-bob"},
	})
	headers := map[string]string{}
	sg.injectLeexiHeader(ctx, headers)
	if got := headers[LeexiAllowedParticipantsHeader]; got != "u-bob" {
		t.Fatalf("expected u-bob (admin-configured), got %q", got)
	}
}

// 5. Same matrix for Ringover — independent backend.
func TestInjectRingoverHeader_AutoSelfOverridesUsersMode(t *testing.T) {
	srv := ringoverServerWithBob(t)
	defer srv.Close()

	sg := &ScopedGateway{ringoverAdmin: ringoveradmin.NewClient(srv.URL, "tok")}
	ctx := ctxWithEmail("bob@example.com")
	ctx = context.WithValue(ctx, scopetoken.RingoverFilterContextKey, &scopetoken.RingoverFilterContext{
		Mode:           "users",
		AllowedUserIDs: []int{99},
	})
	headers := map[string]string{}
	sg.injectRingoverHeader(ctx, headers)
	if got := headers[RingoverAllowedUserIDsHeader]; got != "7" {
		t.Fatalf("expected 7, got %q", got)
	}
}

// 6. Per-backend independence: same user logged in, has Leexi but not
// Ringover, NOT gateway admin. Leexi gets override; Ringover denies.
func TestPerBackendIndependence_LeexiOverrideRingoverDeny(t *testing.T) {
	leexiSrv := leexiServerWithAlice(t)
	defer leexiSrv.Close()
	ringoverSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"users":[]}`)) // alice not in Ringover
	}))
	defer ringoverSrv.Close()

	sg := &ScopedGateway{
		leexiAdmin:    leexiadmin.NewClient(leexiSrv.URL, "tok"),
		ringoverAdmin: ringoveradmin.NewClient(ringoverSrv.URL, "tok"),
		gatewayUsers:  &fakeUserRepo{}, // alice not gateway admin
	}
	ctx := ctxWithEmail("alice@example.com")
	ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{Mode: "none"})
	ctx = context.WithValue(ctx, scopetoken.RingoverFilterContextKey, &scopetoken.RingoverFilterContext{Mode: "none"})

	leexiHeaders := map[string]string{}
	sg.injectLeexiHeader(ctx, leexiHeaders)
	if got := leexiHeaders[LeexiAllowedParticipantsHeader]; got != "u-alice" {
		t.Fatalf("Leexi: expected u-alice, got %q", got)
	}

	ringoverHeaders := map[string]string{}
	sg.injectRingoverHeader(ctx, ringoverHeaders)
	if got := ringoverHeaders[RingoverAllowedUserIDsHeader]; got != "0" {
		t.Fatalf("Ringover: expected deny-sentinel 0, got %q", got)
	}
}
```

- [ ] **Step 2: Run the tests to verify failure**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/gateway/... -run 'AutoSelf|NonAdmin|AdminEmail|NoEmailFallsThrough|PerBackendIndependence' -v 2>&1 | tail -50"
```

Expected: most or all FAIL — current `injectLeexiHeader`/`injectRingoverHeader` only honor the configured mode and never override.

- [ ] **Step 3: Refactor `injectLeexiHeader`**

Read `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go`. Locate `injectLeexiHeader` (around line 190).

Use Edit. Replace the entire function body with:

```go
func (sg *ScopedGateway) injectLeexiHeader(ctx context.Context, headers map[string]string) {
	// Step 1 — auto-self override (per-backend independent).
	if uuid, denied := sg.tryAutoSelfLeexi(ctx); uuid != "" {
		headers[LeexiAllowedParticipantsHeader] = uuid
		return
	} else if denied {
		log.Printf("[scoped] leexi auto-self denied: end-user has no Leexi match and is not a gateway admin")
		headers[LeexiAllowedParticipantsHeader] = "00000000-0000-0000-0000-000000000000"
		return
	}

	// Step 2 — admin-configured filter (existing path; reached when no email
	// in context OR end-user is a gateway admin without a Leexi account).
	filter, ok := scopetoken.LeexiFilterFromContext(ctx)
	if !ok || filter == nil {
		return
	}
	participants := sg.resolveLeexiParticipants(ctx, filter)
	if len(participants) == 0 {
		log.Printf("[scoped] leexi filter mode=%q resolved to empty allow-list — sending deny sentinel", filter.Mode)
		headers[LeexiAllowedParticipantsHeader] = "00000000-0000-0000-0000-000000000000"
		return
	}
	headers[LeexiAllowedParticipantsHeader] = strings.Join(participants, ",")
}

// tryAutoSelfLeexi runs the auto-self override for the Leexi backend. Return
// values:
//   - (uuid, false) — override succeeded, caller should inject the UUID.
//   - ("", true)    — email present, no Leexi match, end-user is not a
//                     gateway admin → deny-sentinel.
//   - ("", false)   — no email OR end-user is a gateway admin → caller should
//                     fall through to the admin-configured filter.
func (sg *ScopedGateway) tryAutoSelfLeexi(ctx context.Context) (string, bool) {
	email, ok := scopetoken.EndUserEmailFromContext(ctx)
	if !ok {
		return "", false // client_credentials path — fall through
	}
	if sg.leexiAdmin == nil || !sg.leexiAdmin.Enabled() {
		return "", false // no Leexi integration — fall through
	}
	user, err := sg.leexiAdmin.FindUserByEmail(ctx, email)
	if err == nil {
		return user.UUID, false
	}
	// Email present but no Leexi match — admin role grants fallback.
	if sg.isGatewayAdmin(email) {
		return "", false
	}
	return "", true // deny
}

// isGatewayAdmin returns true when the email belongs to a gateway_users row
// with Role=admin. Returns false when the repo isn't configured, the row is
// missing, or the role is anything else.
func (sg *ScopedGateway) isGatewayAdmin(email string) bool {
	if sg.gatewayUsers == nil {
		return false
	}
	user, err := sg.gatewayUsers.GetByEmail(email)
	if err != nil || user == nil {
		return false
	}
	return user.Role == auth.RoleAdmin
}
```

Add the import for `mcp-gateway/internal/auth` if not already present.

- [ ] **Step 4: Refactor `injectRingoverHeader` symmetrically**

Replace the body of `injectRingoverHeader` (around line 208) with:

```go
func (sg *ScopedGateway) injectRingoverHeader(ctx context.Context, headers map[string]string) {
	// Step 1 — auto-self override (per-backend independent).
	if id, denied := sg.tryAutoSelfRingover(ctx); id != "" {
		headers[RingoverAllowedUserIDsHeader] = id
		return
	} else if denied {
		log.Printf("[scoped] ringover auto-self denied: end-user has no Ringover match and is not a gateway admin")
		headers[RingoverAllowedUserIDsHeader] = "0"
		return
	}

	// Step 2 — admin-configured filter (existing path).
	filter, ok := scopetoken.RingoverFilterFromContext(ctx)
	if !ok || filter == nil {
		return
	}
	ids := sg.resolveRingoverAllowedUsers(ctx, filter)
	if len(ids) == 0 {
		log.Printf("[scoped] ringover filter mode=%q resolved to empty allow-list — sending deny sentinel", filter.Mode)
		headers[RingoverAllowedUserIDsHeader] = "0"
		return
	}
	parts := make([]string, len(ids))
	for i, id := range ids {
		parts[i] = strconv.Itoa(id)
	}
	headers[RingoverAllowedUserIDsHeader] = strings.Join(parts, ",")
}

// tryAutoSelfRingover mirrors tryAutoSelfLeexi for the Ringover backend.
// Returns (idStr, deny). idStr is non-empty when override succeeded; deny is
// true when the end-user has no Ringover match and is not a gateway admin.
func (sg *ScopedGateway) tryAutoSelfRingover(ctx context.Context) (string, bool) {
	email, ok := scopetoken.EndUserEmailFromContext(ctx)
	if !ok {
		return "", false
	}
	if sg.ringoverAdmin == nil || !sg.ringoverAdmin.Enabled() {
		return "", false
	}
	user, err := sg.ringoverAdmin.FindUserByEmail(ctx, email)
	if err == nil {
		return strconv.Itoa(user.UserID), false
	}
	if sg.isGatewayAdmin(email) {
		return "", false
	}
	return "", true
}
```

`strconv` is already imported in this file.

- [ ] **Step 5: Run the tests**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/gateway/... -v 2>&1 | tail -40"
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./... 2>&1 | tail -25"
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./..."
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go vet ./..."
```

Expected: all 6 new tests PASS. Existing scoped-gateway tests (the `_self_test.go` from the previous feature) still PASS — they exercise the resolver functions directly, which we didn't touch. Full module suite green.

If pre-existing tests on `injectLeexiHeader`/`injectRingoverHeader` (e.g. resolving "users"/"creator"/"teams" modes) break because the new step-1 short-circuit fires when they didn't expect it, the tests need a context with NO `EndUserEmailContextKey` — that already mirrors the client_credentials path. Read each failure carefully; most likely the existing tests already construct contexts without an email, in which case nothing breaks.

- [ ] **Step 6: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB
git add apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go \
        apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway_auto_self_test.go
git commit -m "feat(mcp-gateway): auto-self filter override per backend with admin fallback"
```

---

## Task 3: Wire `UserRepo` Into Gateway at Boot

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/app/app.go`

The setter exists from Task 1; we just call it with the existing `dbStack.userRepo`.

- [ ] **Step 1: Locate the gateway construction**

```bash
grep -n "gateway.New\|gw :=\|gw\.Set" apps-microservices/mcp-gateway-service/internal/app/app.go | head -20
```

You'll see the `gw := gateway.New(...)` call followed by other `gw.Set*` calls (`SetLeexiAdmin`, `SetRingoverAdmin`).

- [ ] **Step 2: Add the wiring**

Right after the existing `SetLeexiAdmin` / `SetRingoverAdmin` block (around lines 96-105), add:

```go
if dbStack.userRepo != nil {
	gw.SetGatewayUserFinder(dbStack.userRepo)
	log.Println("[main] gateway_users wired into Gateway for auto-self admin fallback")
}
```

`dbStack.userRepo` is the `*repository.UserRepo` already built by `buildDBStack`. Confirm by reading the surrounding 40 lines.

- [ ] **Step 3: Build and run the suite**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./..."
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./... 2>&1 | tail -25"
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go vet ./..."
```

Expected: clean build, all tests pass.

- [ ] **Step 4: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB
git add apps-microservices/mcp-gateway-service/internal/app/app.go
git commit -m "feat(mcp-gateway): wire gateway_users repo into Gateway at boot"
```

---

## Task 4: Document the Auto-Override Semantics

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`

- [ ] **Step 1: Add a new bullet right above the existing Leexi/Ringover filter bullet**

Locate the `Scope tokens and OAuth2 clients carry an optional **Leexi ownership filter**` bullet. Insert this new bullet right above it:

```markdown
- **Auto-self filter override (OAuth2 only)**: when an OAuth2 access token's `email` claim resolves to a user in the target backend (Leexi or Ringover), the gateway injects that user's UUID/ID into the outbound header automatically — bypassing whatever filter mode the admin set on the OAuth2 client. Per-backend independent: a user might exist in Leexi but not Ringover; each backend resolves on its own. When the email is present but has no match in this backend: gateway admins (`gateway_users.role = "admin"`) fall back to the admin-configured filter; non-admin users get the deny-sentinel (`00000000-0000-0000-0000-000000000000` for Leexi, `0` for Ringover). Client-credentials grants (no email) bypass the override and use the admin-configured mode as before.
```

- [ ] **Step 2: Commit**

```bash
cd /home/sandratra/RAG-HP-PUB
git add apps-microservices/mcp-gateway-service/CLAUDE.md
git commit -m "docs(mcp-gateway): document auto-self filter override and admin fallback"
```

---

## Task 5: Final Verification

- [ ] **Step 1: Full test + build + vet**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./... 2>&1 | tail -25"
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./..."
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go vet ./..."
```

Expected: every package passes, build clean, vet clean.

- [ ] **Step 2: Cross-cutting review**

Confirm by reading the diff for Task 2 that:
- Existing `_self_test.go` tests (from prior `mode='self'` feature) still pass — they exercise `resolveLeexiParticipants` / `resolveRingoverAllowedUsers` directly with a `LeexiFilterContext{Mode:"self"}` value, not via `injectLeexiHeader`. The new code path doesn't touch those resolvers.
- `client_credentials` flow unchanged — the `EndUserEmailFromContext` returns `("", false)` and `tryAutoSelfXxx` falls through to the admin config.
- `mode='none'` (no `LeexiFilterContextKey` in context) still works — step 1 falls through, step 2 sees `!ok` and returns without injecting a header.

- [ ] **Step 3: Manual smoke (optional, requires staging)**

1. Create a non-`self`-mode OAuth2 client (e.g. `mode='users'` with a fixed list).
2. Log in as user A (Leexi user) via OAuth2 SSO. Issue a Leexi MCP request. Confirm the outbound `X-Leexi-Allowed-Participants` carries A's UUID, NOT the admin's `users` list.
3. Log in as user B (also Leexi user). Confirm the header carries B's UUID, not A's.
4. Log in as a non-Leexi gateway admin (`gateway_users.role = 'admin'`). Confirm the header carries the admin-configured `users` list (fallback).
5. Log in as a non-Leexi non-admin user. Confirm the request is denied (sentinel UUID).
6. Run a `client_credentials` grant against the same client. Confirm the header carries the admin-configured `users` list.

---

## Out of Scope (Explicit YAGNI)

- Removing the existing explicit `mode='self'` admin opt-in. It's now redundant for OAuth2 clients but harmless — keep as backward-compat. A future cleanup task can deprecate it after confirming no clients depend on its quirks.
- Per-user audit logging of the override decision (which mode was bypassed, why). Useful for forensics but not required for correctness.
- UI hint to admins that their configured mode will be bypassed for end-users. Wait for user feedback before adding.
- Caching the gateway-admin lookup. `UserRepo.GetByEmail` is a single-row indexed query (`uniqueIndex:uq_user_email`) and only runs on the no-match-deny branch. Premature optimization.
- Frontend changes. The Vue admin panel's filter pickers stay as-is; the override is invisible from the admin's perspective.
