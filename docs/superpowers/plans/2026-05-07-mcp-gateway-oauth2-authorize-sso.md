# mcp-gateway OAuth2 Authorize via SSO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy hellopro.fr username/password form on the OAuth2 `/authorize` endpoint with a redirect through the existing account-service SSO flow, while distinguishing OAuth2 logins from admin-UI logins so they don't share gateway-admin session state.

**Architecture:** Reuse the same SSO `client_id` + `client_secret` already configured for the admin UI. Add a `Purpose` field on `PendingState` carrying either `"admin"` (today's behaviour) or `"oauth2"`. The `/sso/login` handler accepts a new `purpose` query parameter; `/sso/callback` branches on `Purpose` so the OAuth2 path skips the `gateway_users` upsert + `IsAllowed` check + `SSOSession` persistence + `gw_session` cookie, and instead writes the OAuth2 authserver's existing `mcp_session` cookie via `auth.SetSession`. The OAuth2 `/authorize` GET handler stops rendering its inline login form. **Three-tier session resolution** at `/authorize`:
1. Valid `mcp_session` cookie (OAuth2 authserver session) → render consent (existing behaviour).
2. Otherwise, valid `gw_session` cookie pointing to a non-expired `sso_sessions` row → **bridge**: mint an `mcp_session` cookie carrying the SSO row's email, render consent. No SSO roundtrip needed — admin already logged in.
3. Otherwise, redirect to `/sso/login?return_to=<full-authorize-URL>&purpose=oauth2`.

**Tech Stack:** Go 1.24, `net/http` standard library, `github.com/golang-jwt/jwt/v5` (already used), `internal/auth` (HMAC session cookie), `internal/sso` (OAuth 2.1 client to account-service). No new third-party dependencies.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps-microservices/mcp-gateway-service/internal/sso/state.go` | Add `Purpose string` to `PendingState`. |
| `apps-microservices/mcp-gateway-service/internal/sso/state_test.go` | Cover round-trip of the new `Purpose` field through `SignPendingState` / `VerifyPendingState`. |
| `apps-microservices/mcp-gateway-service/internal/sso/handlers.go` | Read `purpose` from `/sso/login` query, store in `PendingState`. Branch `/sso/callback` on `Purpose`: admin path = current behaviour, oauth2 path = call `auth.SetSession` and redirect to `ReturnTo` with no admin upsert / no `gw_session`. Inject the JWT secret + `secureCookie` config the OAuth2 path needs to write the `mcp_session` cookie. |
| `apps-microservices/mcp-gateway-service/internal/sso/handlers_test.go` | Add `purpose=oauth2` cases for `handleLogin` (state stashes Purpose) and `handleCallback` (sets `mcp_session` cookie, skips `users.UpsertOnLogin`, redirects to `ReturnTo`). |
| `apps-microservices/mcp-gateway-service/internal/authserver/handler.go` | Add `ssoSessionRepo *repository.SSOSessionRepo` field on `AuthServer` (or equivalent struct) so the `/authorize` GET path can bridge from an existing admin session. New constructor parameter or builder method. |
| `apps-microservices/mcp-gateway-service/internal/authserver/authorize.go` | Replace the inline login-form path in `showLoginOrConsent` with a three-tier resolution: (1) existing `mcp_session` → consent, (2) `gw_session` bridge → mint `mcp_session` + consent, (3) redirect to `/sso/login?return_to=<full-authorize-URL>&purpose=oauth2`. Remove the `case "login":` branch in `HandleAuthorize` (no more password form). Keep `case "consent":` untouched. |
| `apps-microservices/mcp-gateway-service/internal/authserver/authorize_test.go` | Replace tests that relied on rendering the login form with: (a) redirect-to-`/sso/login` assertions when no session at all, (b) consent rendering when a valid `gw_session` is present (bridge path), (c) consent rendering when a valid `mcp_session` is present. Keep existing consent-flow tests. |
| `apps-microservices/mcp-gateway-service/internal/authserver/templates/login.html` | Delete (no longer rendered). |
| `apps-microservices/mcp-gateway-service/internal/app/app.go` | Wire the JWT secret + `secureCookie` into the `sso.Handlers` constructor (new `WithAuthSession` builder). Also wire `ssoSessionRepo` into the `authserver` constructor. |
| `apps-microservices/mcp-gateway-service/CLAUDE.md` | Document the SSO-backed `/authorize` flow and the `purpose` query parameter. |

---

## Task 1: Add `Purpose` Field to `PendingState`

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/sso/state.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/sso/state_test.go`

The `PendingState` struct round-trips through a signed cookie between `/sso/login` and `/sso/callback`. We need an extra field that survives that round trip and tells the callback which post-auth flow to run.

- [ ] **Step 1: Write the failing test**

Append to `apps-microservices/mcp-gateway-service/internal/sso/state_test.go`:

```go
func TestSignAndVerifyPendingState_RoundTripsPurpose(t *testing.T) {
	secret := []byte("hmac-secret-for-tests")
	in := PendingState{
		Verifier: "v",
		State:    "s",
		ReturnTo: "/authorize?response_type=code&client_id=x",
		Exp:      time.Now().Add(5 * time.Minute).Unix(),
		Purpose:  "oauth2",
	}
	tok, err := SignPendingState(secret, in)
	if err != nil {
		t.Fatalf("SignPendingState: %v", err)
	}
	got, err := VerifyPendingState(secret, tok)
	if err != nil {
		t.Fatalf("VerifyPendingState: %v", err)
	}
	if got.Purpose != "oauth2" {
		t.Fatalf("Purpose round-trip failed: got %q want %q", got.Purpose, "oauth2")
	}
}

func TestSignAndVerifyPendingState_PurposeOmittedWhenEmpty(t *testing.T) {
	secret := []byte("hmac-secret-for-tests")
	in := PendingState{
		Verifier: "v",
		State:    "s",
		ReturnTo: "/",
		Exp:      time.Now().Add(5 * time.Minute).Unix(),
	}
	tok, err := SignPendingState(secret, in)
	if err != nil {
		t.Fatalf("SignPendingState: %v", err)
	}
	got, err := VerifyPendingState(secret, tok)
	if err != nil {
		t.Fatalf("VerifyPendingState: %v", err)
	}
	if got.Purpose != "" {
		t.Fatalf("expected empty Purpose for default state, got %q", got.Purpose)
	}
}
```

- [ ] **Step 2: Run the tests to verify they fail**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/sso/... -run RoundTripsPurpose -v"
```

Expected: FAIL with `unknown field Purpose in struct literal of type sso.PendingState`.

- [ ] **Step 3: Add the field**

In `apps-microservices/mcp-gateway-service/internal/sso/state.go`, inside the `PendingState` struct, append the new field:

```go
type PendingState struct {
	Verifier string `json:"v"`
	State    string `json:"s"`
	ReturnTo string `json:"r"`
	Exp      int64  `json:"e"`
	// Purpose distinguishes the post-callback flow. "" or "admin" routes the
	// callback through the admin-UI path (gateway_users upsert + gw_session
	// cookie). "oauth2" routes through the OAuth2-authorize path (no admin
	// upsert, sets mcp_session cookie via internal/auth, then redirects back
	// to /authorize so the consent screen can render).
	Purpose string `json:"p,omitempty"`
}
```

- [ ] **Step 4: Run the tests**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/sso/... -run RoundTripsPurpose -v"
```

Expected: PASS for both new tests.

Also confirm full SSO test suite stays green:

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/sso/... -v 2>&1 | tail -20"
```

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/sso/state.go \
        apps-microservices/mcp-gateway-service/internal/sso/state_test.go
git commit -m "feat(mcp-gateway): add Purpose field to SSO pending state"
```

---

## Task 2: Inject Auth-Session Dependencies into `sso.Handlers`

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/sso/handlers.go`

The OAuth2 callback path needs to write the `mcp_session` cookie via `auth.SetSession`. That helper takes a JWT secret and a `secureCookie` bool. Both already exist on the gateway config; we wire them through a new `WithAuthSession` builder so `Handlers` can reach them. We use the existing `secureCk` field for the secure-cookie bool — no duplication needed.

- [ ] **Step 1: Add the builder**

Read `apps-microservices/mcp-gateway-service/internal/sso/handlers.go`. Locate the `Handlers` struct (~line 29-43). Add a single new field:

```go
type Handlers struct {
	client    *Client
	repo      *repository.SSOSessionRepo
	users     userUpserter
	encryptor *crypto.Encryptor
	stateKey  []byte
	secureCk  bool
	gatewayPublicURL string
	slack *SlackNotifier
	// authJWTSecret is the HMAC key used by internal/auth.SetSession when the
	// SSO callback runs the OAuth2-authorize flow. Empty disables the OAuth2
	// branch (callback returns 500 if a Purpose=oauth2 pending state arrives
	// without a configured secret).
	authJWTSecret string
}
```

Add the builder right after `WithSlack` (~line 71):

```go
// WithAuthSession registers the JWT secret used to sign the mcp_session cookie
// when a Purpose=oauth2 callback completes. Wire from cfg.JWTSecret.
func (h *Handlers) WithAuthSession(jwtSecret string) *Handlers {
	h.authJWTSecret = jwtSecret
	return h
}
```

No tests yet — this is pure plumbing. Coverage lands in Task 4 alongside the callback branching.

- [ ] **Step 2: Verify it compiles**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./..."
```

Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/sso/handlers.go
git commit -m "feat(mcp-gateway): inject auth JWT secret into SSO handlers"
```

---

## Task 3: Stash `purpose` Query Parameter in `/sso/login`

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/sso/handlers.go` (`handleLogin` around line 143)
- Modify: `apps-microservices/mcp-gateway-service/internal/sso/handlers_test.go`

- [ ] **Step 1: Write the failing test**

Append to `apps-microservices/mcp-gateway-service/internal/sso/handlers_test.go`:

```go
func TestHandleLogin_StashesOAuth2Purpose(t *testing.T) {
	h := newTestHandlersForLogin(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/sso/login?return_to=%2Fauthorize%3Fclient_id%3Dx&purpose=oauth2", nil)
	h.handleLogin(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("expected 303, got %d", rec.Code)
	}

	cookies := rec.Result().Cookies()
	var pending string
	for _, c := range cookies {
		if c.Name == PendingCookieName {
			pending = c.Value
		}
	}
	if pending == "" {
		t.Fatal("pending cookie not set")
	}
	st, err := VerifyPendingState(h.stateKey, pending)
	if err != nil {
		t.Fatalf("VerifyPendingState: %v", err)
	}
	if st.Purpose != "oauth2" {
		t.Fatalf("expected Purpose=oauth2, got %q", st.Purpose)
	}
	if st.ReturnTo != "/authorize?client_id=x" {
		t.Fatalf("ReturnTo round-trip failed: %q", st.ReturnTo)
	}
}

func TestHandleLogin_DefaultsPurposeToEmpty(t *testing.T) {
	h := newTestHandlersForLogin(t)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/sso/login?return_to=%2F", nil)
	h.handleLogin(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("expected 303, got %d", rec.Code)
	}
	for _, c := range rec.Result().Cookies() {
		if c.Name != PendingCookieName {
			continue
		}
		st, err := VerifyPendingState(h.stateKey, c.Value)
		if err != nil {
			t.Fatalf("VerifyPendingState: %v", err)
		}
		if st.Purpose != "" {
			t.Fatalf("expected empty Purpose, got %q", st.Purpose)
		}
	}
}
```

If `newTestHandlersForLogin` does not yet exist in the test file, add it next to the existing fixtures (top of file, after imports). The minimum it needs:

```go
func newTestHandlersForLogin(t *testing.T) *Handlers {
	t.Helper()
	h := NewHandlers(
		&Client{
			ClientID:           "test-client",
			AccountPublicURL:   "https://account.test",
			RedirectURI:        "https://gw.test/sso/callback",
			Scope:              "openid profile email",
		},
		nil, nil, nil, false,
	).WithStateKey([]byte("hmac-secret-for-tests"))
	return h
}
```

- [ ] **Step 2: Run the tests to verify failure**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/sso/... -run HandleLogin_ -v 2>&1 | tail -30"
```

Expected: FAIL — `Purpose` is not stashed because `handleLogin` does not yet read the `purpose` query parameter.

- [ ] **Step 3: Update `handleLogin` to read `purpose`**

In `apps-microservices/mcp-gateway-service/internal/sso/handlers.go`, locate the `handleLogin` function (around line 143). Find the block that builds `pending`:

```go
	pending := PendingState{
		Verifier: verifier,
		State:    stateNonce,
		ReturnTo: returnTo,
		Exp:      time.Now().Add(5 * time.Minute).Unix(),
	}
```

Replace with:

```go
	purpose := r.URL.Query().Get("purpose")
	if purpose != "" && purpose != "oauth2" {
		// Reject unknown purposes early so a typo can't slip through and
		// silently fall back to the admin path.
		http.Error(w, "invalid purpose", http.StatusBadRequest)
		return
	}
	pending := PendingState{
		Verifier: verifier,
		State:    stateNonce,
		ReturnTo: returnTo,
		Exp:      time.Now().Add(5 * time.Minute).Unix(),
		Purpose:  purpose,
	}
```

- [ ] **Step 4: Run the tests**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/sso/... -v 2>&1 | tail -25"
```

Expected: both new tests PASS, all existing SSO tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/sso/handlers.go \
        apps-microservices/mcp-gateway-service/internal/sso/handlers_test.go
git commit -m "feat(mcp-gateway): accept 'purpose' query param on /sso/login"
```

---

## Task 4: Branch `/sso/callback` on `Purpose=oauth2`

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/sso/handlers.go` (`handleCallback` around line 186)
- Modify: `apps-microservices/mcp-gateway-service/internal/sso/handlers_test.go`

- [ ] **Step 1: Write the failing test**

Append to `apps-microservices/mcp-gateway-service/internal/sso/handlers_test.go`:

```go
// fakeAccountServer answers /token with a canned authorization_code response.
// The access token is a minimal HS256 JWT carrying sub/email/name claims so
// ParseAccessTokenIdentity returns the expected identity without crypto setup.
func fakeAccountServer(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasSuffix(r.URL.Path, "/token") {
			http.NotFound(w, r)
			return
		}
		// Hand-rolled HS256 JWT. The body json: {"sub":"u-1","email":"alice@example.com","name":"Alice","exp":<future>}
		// Signed with the same secret the test injects via WithAuthSession.
		hdr := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`))
		body := base64.RawURLEncoding.EncodeToString([]byte(
			fmt.Sprintf(`{"sub":"u-1","email":"alice@example.com","name":"Alice","exp":%d}`, time.Now().Add(time.Hour).Unix()),
		))
		toSign := hdr + "." + body
		mac := hmac.New(sha256.New, []byte("upstream-jwt-secret"))
		mac.Write([]byte(toSign))
		sig := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
		jwt := toSign + "." + sig

		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"access_token":%q,"refresh_token":"r-1","token_type":"Bearer","expires_in":3600}`, jwt)
	}))
}

func TestHandleCallback_OAuth2PurposeWritesAuthSession(t *testing.T) {
	srv := fakeAccountServer(t)
	defer srv.Close()

	authJWTSecret := "auth-session-secret"
	stateSecret := []byte("hmac-secret-for-tests")

	h := NewHandlers(&Client{
		ClientID:           "c1",
		ClientSecret:       "s1",
		AccountPublicURL:   srv.URL,
		AccountInternalURL: srv.URL,
		RedirectURI:        srv.URL + "/sso/callback",
		Scope:              "openid email",
	}, nil, nil, nil, false).
		WithStateKey(stateSecret).
		WithAuthSession(authJWTSecret)

	// Build a pending cookie with Purpose=oauth2 and a deterministic state nonce.
	pending := PendingState{
		Verifier: "verifier-xyz",
		State:    "state-abc",
		ReturnTo: "/authorize?response_type=code&client_id=mcp-x",
		Exp:      time.Now().Add(5 * time.Minute).Unix(),
		Purpose:  "oauth2",
	}
	tok, err := SignPendingState(stateSecret, pending)
	if err != nil {
		t.Fatalf("SignPendingState: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/sso/callback?code=auth-code-1&state=state-abc", nil)
	req.AddCookie(&http.Cookie{Name: PendingCookieName, Value: tok})
	rec := httptest.NewRecorder()
	h.handleCallback(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("expected 303, got %d (body: %s)", rec.Code, rec.Body.String())
	}
	if got := rec.Header().Get("Location"); got != "/authorize?response_type=code&client_id=mcp-x" {
		t.Fatalf("unexpected redirect: %q", got)
	}

	var sawAuth, sawSession bool
	for _, c := range rec.Result().Cookies() {
		if c.Name == "mcp_session" {
			sawAuth = true
		}
		if c.Name == CookieName {
			sawSession = true
		}
	}
	if !sawAuth {
		t.Fatal("expected mcp_session cookie to be set on OAuth2 path")
	}
	if sawSession {
		t.Fatal("did not expect gw_session cookie on OAuth2 path")
	}
}
```

Add the missing imports to the test file (`encoding/base64`, `crypto/hmac`, `crypto/sha256`, `fmt`, `net/http/httptest`, `strings`, `time`) if they are not yet present.

- [ ] **Step 2: Run the test to verify failure**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/sso/... -run OAuth2PurposeWritesAuthSession -v 2>&1 | tail -40"
```

Expected: FAIL — the existing callback runs the admin path, hits `users.UpsertOnLogin` on a `nil` `users` field, and panics or 500s. We branch in Step 3.

- [ ] **Step 3: Branch `handleCallback` on `Purpose`**

In `apps-microservices/mcp-gateway-service/internal/sso/handlers.go`, locate `handleCallback` (around line 186). Find the section that runs after `tok, err := h.client.ExchangeCode(...)` and `sub, email, name, err := ParseAccessTokenIdentity(tok.AccessToken)` (around line 247). Currently the next block runs `h.users.UpsertOnLogin(...)` unconditionally.

Insert a `Purpose` branch between the identity parse and the admin-only logic. The new shape:

```go
	sub, email, name, err := ParseAccessTokenIdentity(tok.AccessToken)
	if err != nil || email == "" {
		// existing error handling — leave untouched
		// ...
		return
	}

	if pending.Purpose == "oauth2" {
		if err := h.completeOAuth2Login(w, r, pending, tok, email, name); err != nil {
			log.Printf("[sso] callback: oauth2 path failed: %v", err)
			h.notify(r, SSOErrorEvent{Kind: "oauth2_session_failed", Reason: err.Error(), UserEmail: email, Sub: sub})
			h.redirectError(w, r, "oauth2_session_failed", "Authentification OAuth2 impossible.")
		}
		return
	}

	// existing admin path: upsert gateway_users, IsAllowed check, persist
	// SSOSession, set gw_session cookie, redirect. Leave untouched.
	user, err := h.users.UpsertOnLogin(email, name)
	// ... rest unchanged
```

Then add the new method anywhere below `handleCallback`:

```go
// completeOAuth2Login finishes the SSO callback for Purpose=oauth2: writes the
// mcp_session cookie consumed by internal/authserver, then redirects the
// browser back to the original /authorize URL stashed in pending.ReturnTo.
//
// Deliberately does NOT upsert gateway_users (random Hellopro employees should
// not appear in the admin user table just because they OAuth2'd into an MCP
// client), does NOT set gw_session (admin UI session is unrelated), and does
// NOT persist an SSOSession row (the OAuth2 client receives its own
// access+refresh token pair from /token after consent — the upstream
// account-service tokens are short-lived and discarded here).
func (h *Handlers) completeOAuth2Login(w http.ResponseWriter, r *http.Request, pending PendingState, tok *TokenResponse, email, name string) error {
	if h.authJWTSecret == "" {
		return fmt.Errorf("authJWTSecret not configured (call WithAuthSession at boot)")
	}
	if err := auth.SetSession(w, h.authJWTSecret, auth.SessionData{
		DisplayName: name,
		Email:       email,
		Token:       tok.AccessToken,
	}, h.secureCk); err != nil {
		return fmt.Errorf("set auth session: %w", err)
	}
	target := pending.ReturnTo
	if target == "" || !strings.HasPrefix(target, "/") {
		target = "/"
	}
	http.Redirect(w, r, target, http.StatusSeeOther)
	return nil
}
```

Add the import for `mcp-gateway/internal/auth` to `handlers.go` if not already present.

- [ ] **Step 4: Run the tests**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/sso/... -v 2>&1 | tail -30"
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./... 2>&1 | tail -25"
```

Expected: new test PASSES, all existing SSO + admin tests stay green, full module suite green.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/sso/handlers.go \
        apps-microservices/mcp-gateway-service/internal/sso/handlers_test.go
git commit -m "feat(mcp-gateway): branch SSO callback on Purpose=oauth2"
```

---

## Task 5: Wire `WithAuthSession` at Application Boot

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/app/app.go`

The new builder must actually be called when the gateway boots, otherwise Task 4's branch will return the configuration error.

- [ ] **Step 1: Locate the existing SSO handlers wiring**

```bash
grep -n "sso.NewHandlers\|WithStateKey\|WithGatewayPublicURL\|WithSlack" apps-microservices/mcp-gateway-service/internal/app/app.go
```

You should see a chain like `sso.NewHandlers(...).WithStateKey(...).WithGatewayPublicURL(...).WithSlack(...)`. The exact line numbers vary — read the surrounding 30 lines to confirm.

- [ ] **Step 2: Append `.WithAuthSession(cfg.JWTSecret)` to the chain**

Use Edit. Replace whatever the existing terminal builder call is (e.g. `.WithSlack(slackNotifier)`) with the same call followed by `.WithAuthSession(cfg.JWTSecret)`. Example before/after:

Before:
```go
ssoHandlers := sso.NewHandlers(ssoClient, ssoSessionRepo, userRepo, encryptor, cfg.SecureCookie).
	WithStateKey([]byte(cfg.JWTSecret)).
	WithGatewayPublicURL(cfg.GatewayPublicURL).
	WithSlack(loginSlackNotifier)
```

After:
```go
ssoHandlers := sso.NewHandlers(ssoClient, ssoSessionRepo, userRepo, encryptor, cfg.SecureCookie).
	WithStateKey([]byte(cfg.JWTSecret)).
	WithGatewayPublicURL(cfg.GatewayPublicURL).
	WithSlack(loginSlackNotifier).
	WithAuthSession(cfg.JWTSecret)
```

If the existing chain reads from a variable other than `cfg.JWTSecret` for the JWT secret, mirror that name here. Verify by searching the file for `JWTSecret` and using the same accessor.

- [ ] **Step 3: Build**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./..."
```

Expected: clean build.

- [ ] **Step 4: Run the full module test suite**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./... 2>&1 | tail -25"
```

Expected: every package passes.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/app/app.go
git commit -m "feat(mcp-gateway): inject JWT secret into SSO handlers at boot"
```

---

## Task 6: Three-Tier Session Resolution at `/authorize`

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/authserver/handler.go` (add `ssoSessionRepo` field + builder method)
- Modify: `apps-microservices/mcp-gateway-service/internal/authserver/authorize.go`
- Modify: `apps-microservices/mcp-gateway-service/internal/authserver/authorize_test.go`
- Delete: `apps-microservices/mcp-gateway-service/internal/authserver/templates/login.html`
- Modify: `apps-microservices/mcp-gateway-service/internal/app/app.go` (wire `ssoSessionRepo` into authserver)

The OAuth2 authorize endpoint stops handling username/password itself — the inline password form is gone. The `showLoginOrConsent` function becomes a three-tier resolver:

1. Valid `mcp_session` cookie → render consent (existing behaviour).
2. Valid `gw_session` cookie pointing to a non-expired `sso_sessions` row → **bridge**: mint a fresh `mcp_session` from the SSO row's email + name, render consent. No SSO roundtrip.
3. Otherwise → 303 to `/sso/login?return_to=<full-authorize-URL>&purpose=oauth2`.

The bridge handles the common case where an admin user is already signed into the Vue admin UI and uses a separate browser tab to walk an MCP client through OAuth2 — they should not have to authenticate twice.

- [ ] **Step 1: Add `ssoSessionRepo` field + builder to `AuthServer`**

Read `apps-microservices/mcp-gateway-service/internal/authserver/handler.go`. Locate the `AuthServer` struct (around line 14-25 in current code). Add a new field:

```go
type AuthServer struct {
	jwtSecret      string
	authURL        string
	secureCookie   bool
	oauth2Repo     *repository.OAuth2Repo
	authCodeRepo   *repository.AuthCodeRepo
	refreshRepo    *repository.RefreshRepo
	consentRepo    *repository.ConsentRepo
	serverRepo     *repository.ServerRepo
	refreshTTL     int
	// ssoSessionRepo is the optional bridge into the admin SSO session store.
	// When set, GET /authorize with no mcp_session cookie but a valid gw_session
	// cookie reuses the SSO identity instead of bouncing through /sso/login.
	// Nil disables the bridge — falls through to the SSO-redirect path.
	ssoSessionRepo *repository.SSOSessionRepo
}
```

(Match the actual existing field names in the file — read first.)

Add a builder method right after `NewAuthServer`:

```go
// WithSSOSessionRepo enables the bridge from an existing gw_session admin
// session to a fresh mcp_session for the OAuth2 /authorize flow. Pass the
// SSOSessionRepo wired at app boot.
func (s *AuthServer) WithSSOSessionRepo(repo *repository.SSOSessionRepo) *AuthServer {
	s.ssoSessionRepo = repo
	return s
}
```

Add the import for `mcp-gateway/internal/repository` if not already present.

- [ ] **Step 2: Wire `WithSSOSessionRepo` at boot**

Locate the `authserver.NewAuthServer(...)` call in `apps-microservices/mcp-gateway-service/internal/app/app.go`. Append `.WithSSOSessionRepo(ssoSessionRepo)` to the chain (`ssoSessionRepo` is the same variable already passed to `sso.NewHandlers` in Task 5; verify the variable name by reading the file).

```go
authsrv := authserver.NewAuthServer(...).WithSSOSessionRepo(ssoSessionRepo)
```

If the existing call is not already chainable (returns by value not pointer), refactor `NewAuthServer` to return a pointer; pointer receivers are already used elsewhere on `AuthServer`.

- [ ] **Step 3: Write the failing tests**

Append to `apps-microservices/mcp-gateway-service/internal/authserver/authorize_test.go`:

```go
// TestHandleAuthorize_NoSessionRedirectsToSSOLoginWithOAuth2Purpose covers
// tier 3 of showLoginOrConsent: no mcp_session, no gw_session bridge → 303 to
// /sso/login with purpose=oauth2.
func TestHandleAuthorize_NoSessionRedirectsToSSOLoginWithOAuth2Purpose(t *testing.T) {
	s := newTestAuthServer(t) // no WithSSOSessionRepo: bridge disabled
	clientID := seedTestOAuth2Client(t, s, []string{"https://app.test/cb"})

	q := url.Values{}
	q.Set("response_type", "code")
	q.Set("client_id", clientID)
	q.Set("redirect_uri", "https://app.test/cb")
	q.Set("code_challenge", "abc")
	q.Set("code_challenge_method", "S256")
	q.Set("state", "xyz")

	req := httptest.NewRequest(http.MethodGet, "/authorize?"+q.Encode(), nil)
	rec := httptest.NewRecorder()
	s.HandleAuthorize(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("expected 303, got %d (body: %s)", rec.Code, rec.Body.String())
	}
	loc := rec.Header().Get("Location")
	parsed, err := url.Parse(loc)
	if err != nil {
		t.Fatalf("url.Parse: %v", err)
	}
	if !strings.HasPrefix(parsed.Path, "/sso/login") {
		t.Fatalf("expected redirect to /sso/login, got %q", loc)
	}
	if got := parsed.Query().Get("purpose"); got != "oauth2" {
		t.Fatalf("expected purpose=oauth2, got %q", got)
	}
	returnTo := parsed.Query().Get("return_to")
	if !strings.HasPrefix(returnTo, "/authorize?") {
		t.Fatalf("return_to should round-trip the original /authorize URL, got %q", returnTo)
	}
}

// TestHandleAuthorize_BridgesGwSessionToMcpSession covers tier 2: a valid
// gw_session cookie pointing to a fresh sso_sessions row → consent screen
// rendered, mcp_session cookie minted on the fly.
func TestHandleAuthorize_BridgesGwSessionToMcpSession(t *testing.T) {
	s := newTestAuthServerWithSSORepo(t) // builder above + seeded SSOSessionRepo
	clientID := seedTestOAuth2Client(t, s, []string{"https://app.test/cb"})

	// Seed an unexpired SSO session row.
	sid := "test-sso-session-id"
	seedTestSSOSession(t, s, sid, "alice@example.com", time.Now().Add(time.Hour))

	q := url.Values{}
	q.Set("response_type", "code")
	q.Set("client_id", clientID)
	q.Set("redirect_uri", "https://app.test/cb")
	q.Set("code_challenge", "abc")
	q.Set("code_challenge_method", "S256")
	q.Set("state", "xyz")

	req := httptest.NewRequest(http.MethodGet, "/authorize?"+q.Encode(), nil)
	req.AddCookie(&http.Cookie{Name: sso.CookieName, Value: sid})
	rec := httptest.NewRecorder()
	s.HandleAuthorize(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 (consent screen), got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "alice@example.com") {
		t.Fatalf("consent screen should display the bridged user email, body=%q", rec.Body.String())
	}
	var sawMcp bool
	for _, c := range rec.Result().Cookies() {
		if c.Name == "mcp_session" {
			sawMcp = true
		}
	}
	if !sawMcp {
		t.Fatal("expected mcp_session cookie to be minted on bridge")
	}
}

// TestHandleAuthorize_BridgeIgnoresExpiredSSOSession confirms an expired SSO
// row falls through to tier 3 (redirect).
func TestHandleAuthorize_BridgeIgnoresExpiredSSOSession(t *testing.T) {
	s := newTestAuthServerWithSSORepo(t)
	clientID := seedTestOAuth2Client(t, s, []string{"https://app.test/cb"})

	sid := "expired-sso-session"
	seedTestSSOSession(t, s, sid, "alice@example.com", time.Now().Add(-time.Hour)) // expired

	q := url.Values{}
	q.Set("response_type", "code")
	q.Set("client_id", clientID)
	q.Set("redirect_uri", "https://app.test/cb")
	q.Set("code_challenge", "abc")
	q.Set("code_challenge_method", "S256")
	q.Set("state", "xyz")

	req := httptest.NewRequest(http.MethodGet, "/authorize?"+q.Encode(), nil)
	req.AddCookie(&http.Cookie{Name: sso.CookieName, Value: sid})
	rec := httptest.NewRecorder()
	s.HandleAuthorize(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("expected 303 (expired bridge falls through), got %d", rec.Code)
	}
	if !strings.HasPrefix(rec.Header().Get("Location"), "/sso/login") {
		t.Fatalf("expected redirect to /sso/login, got %q", rec.Header().Get("Location"))
	}
}
```

If `newTestAuthServerWithSSORepo` and `seedTestSSOSession` do not exist, add them next to the existing fixtures. The minimum:

```go
func newTestAuthServerWithSSORepo(t *testing.T) *AuthServer {
	t.Helper()
	s := newTestAuthServer(t)
	repo := repository.NewSSOSessionRepo(testGormDB(t)) // reuse whatever the suite already does for SQLite-in-memory
	return s.WithSSOSessionRepo(repo)
}

func seedTestSSOSession(t *testing.T, s *AuthServer, sid, email string, accessExp time.Time) {
	t.Helper()
	if err := s.ssoSessionRepo.Create(&db.SSOSession{
		ID:           sid,
		UserID:       1,
		Sub:          "test-sub",
		Email:        email,
		AccessToken:  []byte("encrypted-access"),
		RefreshToken: []byte("encrypted-refresh"),
		AccessExp:    accessExp,
		RefreshExp:   accessExp.Add(24 * time.Hour),
		LastSeenAt:   time.Now(),
	}); err != nil {
		t.Fatalf("seed sso session: %v", err)
	}
}
```

If the existing test suite doesn't have a SQLite-in-memory GORM helper, look for `testGormDB` or `setupTestDB` in any `*_test.go` file under `internal/repository/` — repo tests must already wire one. Reuse, do not reinvent.

- [ ] **Step 4: Run the tests to verify failure**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/authserver/... -run 'HandleAuthorize_' -v 2>&1 | tail -50"
```

Expected: all three new tests FAIL — current `showLoginOrConsent` either renders the login form (200 HTML) or redirects to `/sso/login` without checking `gw_session`.

- [ ] **Step 5: Replace `showLoginOrConsent` with three-tier resolution**

In `apps-microservices/mcp-gateway-service/internal/authserver/authorize.go`, locate `showLoginOrConsent` (around line 124). Replace its body:

```go
func (s *AuthServer) showLoginOrConsent(w http.ResponseWriter, r *http.Request, client *db.OAuth2Client, params *authorizeParams) {
	// Tier 1: existing OAuth2 authserver session — render consent directly.
	session, err := auth.GetSession(r, s.jwtSecret)
	if err == nil {
		if _, err := auth.ValidateJWT(session.Token, s.jwtSecret, ""); err == nil {
			s.renderConsent(w, client, params, session.Email)
			return
		}
	}

	// Tier 2: bridge from an active admin SSO session if one exists. Mint a
	// fresh mcp_session so subsequent requests in this OAuth2 flow find the
	// authserver session via tier 1.
	if email, ok := s.bridgeFromSSOSession(r); ok {
		if err := s.mintAuthSession(w, email, ""); err != nil {
			log.Printf("[authserver] bridge mint session: %v", err)
			// Fall through to tier 3 on failure so the user can still log in.
		} else {
			s.renderConsent(w, client, params, email)
			return
		}
	}

	// Tier 3: no usable session — redirect to /sso/login with the original
	// authorize URL preserved so the browser lands back here once the cookie
	// is set and tier 1 picks up.
	returnTo := "/authorize?" + r.URL.RawQuery
	q := url.Values{}
	q.Set("return_to", returnTo)
	q.Set("purpose", "oauth2")
	http.Redirect(w, r, "/sso/login?"+q.Encode(), http.StatusSeeOther)
}

// bridgeFromSSOSession returns the email of an authenticated admin user when
// the request carries a valid, non-expired gw_session cookie pointing to an
// sso_sessions row. The boolean distinguishes "no bridge possible" (cookie
// absent / row missing / expired / repo not configured) from "successful
// bridge".
func (s *AuthServer) bridgeFromSSOSession(r *http.Request) (string, bool) {
	if s.ssoSessionRepo == nil {
		return "", false
	}
	sid, err := sso.GetSessionID(r)
	if err != nil {
		return "", false
	}
	row, err := s.ssoSessionRepo.FindByID(sid)
	if err != nil || row == nil {
		return "", false
	}
	if !row.AccessExp.IsZero() && time.Now().After(row.AccessExp) {
		return "", false
	}
	if row.Email == "" {
		return "", false
	}
	return row.Email, true
}

// mintAuthSession writes the mcp_session cookie used by tier 1. The Token
// field stashes a freshly-minted JWT so auth.ValidateJWT in subsequent
// requests passes — the upstream account-service token is not available here,
// and the consent flow only needs the email + a non-empty session.
func (s *AuthServer) mintAuthSession(w http.ResponseWriter, email, displayName string) error {
	claims := auth.Claims{
		Exp:  time.Now().Add(24 * time.Hour).Unix(),
		Iat:  time.Now().Unix(),
		Name: displayName,
	}
	tok, err := auth.SignJWT(s.jwtSecret, claims)
	if err != nil {
		return err
	}
	return auth.SetSession(w, s.jwtSecret, auth.SessionData{
		DisplayName: displayName,
		Email:       email,
		Token:       tok,
	}, s.secureCookie)
}
```

Add the imports: `mcp-gateway/internal/sso` (for `sso.GetSessionID` and `sso.CookieName`), `time`, `log`, `net/url`. Most are likely already present — confirm before adding.

- [ ] **Step 6: Remove the `case "login":` branch in `HandleAuthorize`**

In the same file, locate `HandleAuthorize` (around line 36). Find the `switch action := ...` block:

```go
		switch action {
		case "login":
			s.handleLogin(w, r, client, params)
		case "consent":
			s.handleConsent(w, r, client, params)
		default:
			http.Error(w, "invalid action", http.StatusBadRequest)
		}
```

Delete the `case "login":` arm — the SSO flow no longer posts back here:

```go
		switch action {
		case "consent":
			s.handleConsent(w, r, client, params)
		default:
			http.Error(w, "invalid action", http.StatusBadRequest)
		}
```

Also delete the now-unused `handleLogin` function (around line 145) and any references. Check the `templateFS` `embed.FS` declaration:

```go
//go:embed templates/*.html
var templateFS embed.FS

var (
	loginTmpl   = template.Must(template.ParseFS(templateFS, "templates/login.html"))
	consentTmpl = template.Must(template.ParseFS(templateFS, "templates/consent.html"))
)
```

Remove `loginTmpl` (no longer used). The embed glob still matches `consent.html`.

```bash
rm apps-microservices/mcp-gateway-service/internal/authserver/templates/login.html
```

If the existing `s.authURL` field on `AuthServer` is now unused, leave it for now — it is still used by `internal/authserver/authorize_api.go` (the JSON CLI login path), which is out of scope for this plan.

- [ ] **Step 4: Remove the `case "login":` branch in `HandleAuthorize`**

In the same file, locate `HandleAuthorize` (around line 36). Find the `switch action := ...` block:

```go
		switch action {
		case "login":
			s.handleLogin(w, r, client, params)
		case "consent":
			s.handleConsent(w, r, client, params)
		default:
			http.Error(w, "invalid action", http.StatusBadRequest)
		}
```

Delete the `case "login":` arm — the SSO flow no longer posts back here:

```go
		switch action {
		case "consent":
			s.handleConsent(w, r, client, params)
		default:
			http.Error(w, "invalid action", http.StatusBadRequest)
		}
```

Also delete the now-unused `handleLogin` function (around line 145) and its references. Search for any leftover `loginTmpl` template references and the `templates/login.html` file. Once the function is gone, also delete the template:

```bash
rm apps-microservices/mcp-gateway-service/internal/authserver/templates/login.html
```

Then check the `templateFS` `embed.FS` declaration at the top of `authorize.go`:

```go
//go:embed templates/*.html
var templateFS embed.FS

var (
	loginTmpl   = template.Must(template.ParseFS(templateFS, "templates/login.html"))
	consentTmpl = template.Must(template.ParseFS(templateFS, "templates/consent.html"))
)
```

Remove `loginTmpl` (no longer used). The embed glob still matches `consent.html`.

If the existing `s.authURL` field on `AuthServer` is now unused, leave it for now — it is still used by `internal/authserver/authorize_api.go` (the JSON CLI login path), which is out of scope for this plan.

- [ ] **Step 7: Run the tests**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./internal/authserver/... -v 2>&1 | tail -50"
```

Expected: all three new tests PASS, all existing consent-flow tests still PASS. Any pre-existing tests that asserted the login-form HTML body must be deleted or rewritten as redirect tests — search the file for `loginTmpl`, `Tous les champs`, or assertions on `text/html` content from `/authorize` and either delete them or convert them.

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./... 2>&1 | tail -25"
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./... 2>&1"
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go vet ./... 2>&1"
```

Expected: everything green.

- [ ] **Step 8: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/authserver/authorize.go \
        apps-microservices/mcp-gateway-service/internal/authserver/authorize_test.go \
        apps-microservices/mcp-gateway-service/internal/authserver/handler.go \
        apps-microservices/mcp-gateway-service/internal/app/app.go
git rm apps-microservices/mcp-gateway-service/internal/authserver/templates/login.html
git commit -m "feat(mcp-gateway): bridge admin SSO session into OAuth2 /authorize"
```

---

## Task 7: Document the New Flow in CLAUDE.md

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`

- [ ] **Step 1: Append the OAuth2-via-SSO description**

Locate the OAuth2 Authorization Server section in `apps-microservices/mcp-gateway-service/CLAUDE.md` (the bullet that mentions RFC 8414 / 7591 / PKCE). Add a new bullet immediately below it:

```markdown
- **OAuth2 `/authorize` login**: three-tier session resolution.
  1. Valid `mcp_session` cookie → render consent.
  2. Otherwise, valid `gw_session` cookie pointing to a non-expired `sso_sessions` row → bridge: mint `mcp_session` from the admin SSO row's email, render consent. No SSO roundtrip — admin already logged in.
  3. Otherwise, 303 to `/sso/login?purpose=oauth2&return_to=<full-authorize-URL>`. The same SSO `client_id`/`client_secret` as the admin UI is reused; the `purpose` query parameter tells `/sso/callback` to skip the admin upsert + `IsAllowed` check + `SSOSession` persistence + `gw_session` cookie, and instead set the `mcp_session` cookie via `internal/auth.SetSession` before redirecting back to the original `/authorize` URL so the consent screen can render.
  `client_credentials` grants are unaffected (they never hit `/authorize`).
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/mcp-gateway-service/CLAUDE.md
git commit -m "docs(mcp-gateway): document SSO-backed OAuth2 /authorize flow"
```

---

## Task 8: Final Verification

- [ ] **Step 1: Run the full module test suite**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go test ./... 2>&1 | tail -25"
```

Expected: every package passes.

- [ ] **Step 2: Build the binary**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go build -buildvcs=false ./..."
```

Expected: clean build, no errors.

- [ ] **Step 3: `go vet`**

```
docker exec gateway-go sh -c "cd /work/apps-microservices/mcp-gateway-service && go vet ./..."
```

Expected: clean.

- [ ] **Step 4: Manual smoke (optional, requires staging)**

1. Open the OAuth2 client app's "Sign in" link, which hits `/authorize?response_type=code&client_id=...&redirect_uri=...&code_challenge=...&state=...`.
2. Observe a 303 to `/sso/login?return_to=...&purpose=oauth2`.
3. Account-service login page appears. Sign in.
4. `/sso/callback` runs the OAuth2 branch: redirects back to `/authorize?...` with `mcp_session` cookie set.
5. `/authorize` GET sees the session and renders the consent screen.
6. Approve. Browser redirects to the registered `redirect_uri` with `?code=...&state=...`.
7. Confirm `gateway_users` table has NO new row for the test user, and `sso_sessions` has NO new row.
8. Confirm the existing admin-UI flow (`/sso/login` without `purpose`) still works end-to-end.

---

## Out of Scope (Explicit YAGNI)

- Replacing `internal/authserver/authorize_api.go` (the JSON CLI login path). It still uses `auth.AuthenticateHellopro` directly. Migrating that path to SSO is a separate plan because CLI clients can't follow a browser redirect.
- Persisting an `SSOSession` row for OAuth2 flows. The OAuth2 client gets its own access+refresh tokens at `/token`; the upstream account-service tokens are intentionally discarded once `mcp_session` is set.
- Single-sign-out from OAuth2 clients. Today's `/logout` only handles admin sessions; OAuth2 clients revoke their own tokens via the existing `/oauth2/clients/{id}/revoke` admin endpoint. Adding RP-initiated logout to the OAuth2 path is a follow-up.
- UI changes. The Vue admin SPA has its own login flow; this plan only touches the gateway's HTTP-rendered `/authorize` page used by MCP clients.
- Renaming `mcp_session` to a more specific name. The cookie is shared with the legacy `authorize_api.go` JSON path; renaming requires coordinating both call sites.
