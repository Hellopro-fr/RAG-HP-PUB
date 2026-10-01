# Account Service — Client Integration Guide

How to wire SSO via account-service into a downstream service.

> Audience: engineers adding "Login with Hellopro" to a service that needs authentication. Examples in Go (net/http) and Python (FastAPI). Same flow translates 1:1 to any language with an HTTP client.

---

## TL;DR

```
1. Admin registers your service in the account-service UI
   → receives client_id + client_secret + a redirect_uri allowlist.
2. Your service implements 3 endpoints:
   - GET  /auth/login    → 302 to account-service /authorize  (PKCE start)
   - GET  /auth/callback → exchange code for tokens, set local session
   - POST /auth/logout-webhook → receive back-channel logout (HMAC verify)
3. Add middleware: gate routes on a local session cookie that holds the
   user's email + sid coming from the JWT.
```

No password, no signup, no user table on your side. Account-service is the IdP.

---

## 1. Register your service

Admin UI: `https://<account-service>/admin/services/new`

Required fields:
- **Name** — display name shown on the login page (`Connexion à <name>`).
- **Redirect URIs** — exact match required. List every URL your callback will run on (dev + prod). Example: `https://my-service.example.com/auth/callback`.
- **Logout webhook URL** — where account-service POSTs back-channel logout events (next section). Optional but strongly recommended.

Optional:
- `token_ttl_s` (default 60s — short by design).
- `refresh_ttl_s` (default 30 days).
- `claim_mappings` — extra fields you want in the JWT (e.g. `is_admin → role_admin`).
- `allowed_roles` — restrict who can SSO into this service (`["admin"]` to admin-only).

Save → modal shows `client_id` + `client_secret` **once**. Store both in your service's secret store. The secret cannot be re-displayed; if lost, hit "Regenerate secret" and update.

---

## 2. The OAuth 2.1 PKCE flow

```
Browser              Your service             account-service
  │                       │                          │
  │  GET /auth/login      │                          │
  ├──────────────────────►│                          │
  │                       │ generate verifier        │
  │                       │ challenge=S256(verifier) │
  │                       │ store verifier in cookie │
  │  302 to /authorize?...│                          │
  │◄──────────────────────┤                          │
  │  GET /authorize?client_id=...&code_challenge=... │
  ├──────────────────────────────────────────────────►
  │                       │       login form (or skip if session cookie)
  │◄──────────────────────────────────────────────────
  │  user submits creds   │                          │
  ├──────────────────────────────────────────────────►
  │                       │       302 to redirect_uri?code=...&state=...
  │◄──────────────────────────────────────────────────
  │  GET /auth/callback?code=...&state=...           │
  ├──────────────────────►│                          │
  │                       │ POST /token              │
  │                       │  grant_type=authorization_code
  │                       │  code, code_verifier,    │
  │                       │  Basic client_id:secret  │
  │                       ├─────────────────────────►│
  │                       │ {access_token, refresh_token}
  │                       │◄─────────────────────────┤
  │                       │ set local session cookie │
  │  302 to /             │                          │
  │◄──────────────────────┤                          │
```

Discovery (optional but recommended): hit `GET /.well-known/oauth-authorization-server` once at boot to learn `authorization_endpoint` / `token_endpoint` instead of hardcoding paths.

### Required client behavior

| Step | What you must do | Why |
|---|---|---|
| Generate verifier | `verifier = base64url(rand 32 bytes)` | Cryptographic random. Never reuse. |
| Generate challenge | `challenge = base64url(SHA-256(verifier))` | RFC 7636 S256 |
| Generate state | `state = base64url(rand 16 bytes)` | CSRF protection on callback |
| Store verifier + state | Cookie or server-side cache, scoped to this auth attempt | You need them at callback to exchange + verify |
| Validate state on callback | Compare query `state` to stored value | Drop request if mismatch (CSRF) |
| Send code_verifier on /token | Account-service computes SHA-256, compares to stored challenge | PKCE proof the same client started the flow |

---

## 3. Implementation — Go (net/http + standard library)

```go
package auth

import (
    "context"
    "crypto/rand"
    "crypto/sha256"
    "encoding/base64"
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "net/http"
    "net/url"
    "strings"
    "time"
)

const (
    accountBaseURL = "https://account.hellopro.fr" // ACCOUNT_PUBLIC_URL of account-service
    clientID       = "<from admin UI>"
    clientSecret   = "<from admin UI>"
    redirectURI    = "https://my-service.example.com/auth/callback"
)

// ---- /auth/login: start PKCE flow ----------------------------------------

func HandleLogin(w http.ResponseWriter, r *http.Request) {
    verifier := randB64(32)
    sum := sha256.Sum256([]byte(verifier))
    challenge := base64.RawURLEncoding.EncodeToString(sum[:])
    state := randB64(16)

    // Store verifier+state in a short-lived HttpOnly cookie. Server-side
    // store works too if you'd rather not let the browser hold it.
    http.SetCookie(w, &http.Cookie{Name: "auth_verifier", Value: verifier, Path: "/", MaxAge: 600, HttpOnly: true, SameSite: http.SameSiteLaxMode})
    http.SetCookie(w, &http.Cookie{Name: "auth_state", Value: state, Path: "/", MaxAge: 600, HttpOnly: true, SameSite: http.SameSiteLaxMode})

    q := url.Values{
        "response_type":         {"code"},
        "client_id":             {clientID},
        "redirect_uri":          {redirectURI},
        "code_challenge":        {challenge},
        "code_challenge_method": {"S256"},
        "state":                 {state},
    }
    http.Redirect(w, r, accountBaseURL+"/authorize?"+q.Encode(), http.StatusFound)
}

// ---- /auth/callback: exchange code for tokens ----------------------------

type TokenResponse struct {
    AccessToken  string `json:"access_token"`
    RefreshToken string `json:"refresh_token"`
    TokenType    string `json:"token_type"`
    ExpiresIn    int    `json:"expires_in"`
}

func HandleCallback(w http.ResponseWriter, r *http.Request) {
    code := r.URL.Query().Get("code")
    state := r.URL.Query().Get("state")

    storedState, err := r.Cookie("auth_state")
    if err != nil || storedState.Value != state {
        http.Error(w, "state mismatch", http.StatusBadRequest)
        return
    }
    verifier, err := r.Cookie("auth_verifier")
    if err != nil {
        http.Error(w, "missing verifier", http.StatusBadRequest)
        return
    }

    tok, err := exchangeCode(r.Context(), code, verifier.Value)
    if err != nil {
        http.Error(w, "token exchange failed: "+err.Error(), http.StatusBadGateway)
        return
    }

    // Clear PKCE cookies, set application session cookie pointing at the JWT.
    http.SetCookie(w, &http.Cookie{Name: "auth_verifier", MaxAge: -1, Path: "/"})
    http.SetCookie(w, &http.Cookie{Name: "auth_state", MaxAge: -1, Path: "/"})

    // Store the access_token (or just sub+sid extracted from it) + refresh_token
    // in your session store. Examples below assume a server-side session keyed
    // by a session_id cookie.
    sid := persistSession(tok)
    http.SetCookie(w, &http.Cookie{Name: "app_session", Value: sid, Path: "/", HttpOnly: true, SameSite: http.SameSiteLaxMode, MaxAge: 86400})
    http.Redirect(w, r, "/", http.StatusFound)
}

func exchangeCode(ctx context.Context, code, verifier string) (*TokenResponse, error) {
    body := url.Values{
        "grant_type":    {"authorization_code"},
        "code":          {code},
        "redirect_uri":  {redirectURI},
        "code_verifier": {verifier},
    }
    req, _ := http.NewRequestWithContext(ctx, http.MethodPost,
        accountBaseURL+"/token", strings.NewReader(body.Encode()))
    req.SetBasicAuth(clientID, clientSecret)
    req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    raw, _ := io.ReadAll(resp.Body)
    if resp.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("token endpoint %d: %s", resp.StatusCode, string(raw))
    }
    var t TokenResponse
    if err := json.Unmarshal(raw, &t); err != nil {
        return nil, err
    }
    return &t, nil
}

// ---- middleware --------------------------------------------------------

func RequireAuth(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        c, err := r.Cookie("app_session")
        if err != nil || c.Value == "" {
            http.Redirect(w, r, "/auth/login", http.StatusFound)
            return
        }
        sess := loadSession(c.Value)
        if sess == nil {
            http.Redirect(w, r, "/auth/login", http.StatusFound)
            return
        }
        // Optional: refresh access token if exp is close
        next.ServeHTTP(w, r)
    })
}

// ---- helpers -----------------------------------------------------------

func randB64(n int) string {
    b := make([]byte, n)
    _, _ = io.ReadFull(rand.Reader, b)
    return base64.RawURLEncoding.EncodeToString(b)
}

// persistSession + loadSession are application-specific. Use Redis, an
// in-memory map, an encrypted cookie, etc. Keep at minimum:
//   - sid (uuid from JWT, used for back-channel logout matching)
//   - sub (user email)
//   - access_token + refresh_token (encrypted at rest if cookie-stored)
//   - exp
func persistSession(t *TokenResponse) string { /* ... */ return "" }
func loadSession(sid string) *Session         { /* ... */ return nil }

type Session struct {
    SID, Sub, AccessToken, RefreshToken string
    Exp                                 time.Time
}

var ErrSessionExpired = errors.New("session expired")
```

---

## 4. Implementation — Python (FastAPI)

```python
import base64
import hashlib
import os
import secrets
from typing import Optional

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

ACCOUNT_BASE_URL = os.environ["ACCOUNT_BASE_URL"]
CLIENT_ID        = os.environ["ACCOUNT_CLIENT_ID"]
CLIENT_SECRET    = os.environ["ACCOUNT_CLIENT_SECRET"]
REDIRECT_URI     = os.environ["ACCOUNT_REDIRECT_URI"]

router = APIRouter()


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@router.get("/auth/login")
def login(response: Response):
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    state = _b64url(secrets.token_bytes(16))

    response = RedirectResponse(
        f"{ACCOUNT_BASE_URL}/authorize?"
        f"response_type=code&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&code_challenge={challenge}&code_challenge_method=S256"
        f"&state={state}",
        status_code=302,
    )
    response.set_cookie("auth_verifier", verifier, httponly=True, samesite="lax", max_age=600)
    response.set_cookie("auth_state",    state,    httponly=True, samesite="lax", max_age=600)
    return response


@router.get("/auth/callback")
async def callback(request: Request, code: str, state: str):
    if request.cookies.get("auth_state") != state:
        raise HTTPException(400, "state mismatch")
    verifier = request.cookies.get("auth_verifier")
    if not verifier:
        raise HTTPException(400, "missing verifier")

    async with httpx.AsyncClient() as cli:
        r = await cli.post(
            f"{ACCOUNT_BASE_URL}/token",
            data={
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  REDIRECT_URI,
                "code_verifier": verifier,
            },
            auth=(CLIENT_ID, CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
    if r.status_code != 200:
        raise HTTPException(502, f"token exchange failed: {r.text}")
    tok = r.json()

    # Persist session + set cookie. Replace with your session store of choice.
    sid = persist_session(tok)
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie("auth_verifier")
    resp.delete_cookie("auth_state")
    resp.set_cookie("app_session", sid, httponly=True, samesite="lax", max_age=86400)
    return resp


def persist_session(tok: dict) -> str:
    # Decode the JWT to grab sub + sid (no signature verification needed
    # client-side as long as you trust it came from the /token POST).
    import json as _json
    payload = tok["access_token"].split(".")[1]
    payload += "=" * (4 - len(payload) % 4)
    claims = _json.loads(base64.urlsafe_b64decode(payload))
    sid = claims["sid"]
    # ... store {sub: claims["sub"], sid: sid, refresh: tok["refresh_token"], exp: claims["exp"]}
    return sid
```

---

## 5. Refresh handling

Access tokens are intentionally short (60s default). Two strategies:

**A. Refresh on demand.** Catch 401 on a downstream call → POST `/token` `grant_type=refresh_token` → retry once.

**B. Background refresh.** Schedule refresh ~5s before `exp`.

```go
form := url.Values{
    "grant_type":    {"refresh_token"},
    "refresh_token": {sess.RefreshToken},
}
req, _ := http.NewRequest(http.MethodPost, accountBaseURL+"/token", strings.NewReader(form.Encode()))
req.SetBasicAuth(clientID, clientSecret)
req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
// On 200: replace stored access_token + refresh_token (rotation: old refresh is now invalid).
// On 400 invalid_grant: drop session, redirect user to /auth/login.
```

> The refresh endpoint **rotates** the refresh token. Store the new one. Reusing the old one after rotation triggers reuse-detection on account-service: the entire chain is revoked + audit alert fires.

---

## 6. Back-channel logout webhook

Your service exposes a POST endpoint configured in the admin UI. Account-service POSTs there when a user logs out (their action) or an admin revokes their sessions.

### Request shape

```
POST /auth/logout-webhook  HTTP/1.1
Content-Type: application/json
X-Logout-Signature: sha256=<hex>

{
  "iss": "https://account.hellopro.fr",
  "sub": "alice@hellopro.fr",
  "sid": "ad6a...c2f",
  "iat": 1735000000,
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
```

### Verification (Go)

```go
import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "io"
    "net/http"
    "time"
)

const replayWindow = 5 * time.Minute

func HandleLogoutWebhook(w http.ResponseWriter, r *http.Request) {
    body, _ := io.ReadAll(r.Body)

    presented := r.Header.Get("X-Logout-Signature")
    mac := hmac.New(sha256.New, []byte(clientSecret))
    mac.Write(body)
    expected := "sha256=" + hex.EncodeToString(mac.Sum(nil))
    if !hmac.Equal([]byte(presented), []byte(expected)) {
        http.Error(w, "bad signature", http.StatusUnauthorized)
        return
    }

    var p struct {
        Sub string `json:"sub"`
        Sid string `json:"sid"`
        Iat int64  `json:"iat"`
    }
    if err := json.Unmarshal(body, &p); err != nil {
        http.Error(w, "bad body", http.StatusBadRequest)
        return
    }
    if time.Since(time.Unix(p.Iat, 0)) > replayWindow {
        http.Error(w, "stale", http.StatusUnauthorized)
        return
    }

    // Destroy local sessions matching sub (and sid if non-empty: targeted
    // single-session revoke; empty sid means "all sessions for sub").
    revokeLocalSessions(p.Sub, p.Sid)
    w.WriteHeader(http.StatusNoContent)
}
```

Webhook handlers MUST be:
- **Idempotent** — account-service retries 3× with exp backoff on 5xx/timeout.
- **Fast** (< 5s) — that's the delivery timeout.
- **HMAC-verified** — never act on the body before checking the signature.
- **Time-bounded** — reject `iat` older than 5 minutes (replay protection).

---

## 7. Token introspection (optional)

If your service caches access tokens for longer than ~1 minute (e.g. resource servers), poll `/introspect` to confirm the token isn't revoked yet:

```
POST /introspect
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64(client_id:client_secret)>

token=<access_token>

→ 200 {"active": true, "sub": "...", "sid": "...", "exp": 1735000060, ...}
   or {"active": false}
```

For most apps this isn't needed — short JWT TTL + back-channel logout cover it. Use introspection if you have multi-minute API caches that can't tolerate a stale token.

---

## 8. Local session vs JWT — pick one

You have two options for what your service's session cookie holds:

| Approach | Pros | Cons |
|---|---|---|
| **Server-side session** (sid cookie → Redis/DB row holding the JWT + refresh) | Easy revoke, easy refresh, JWT never leaves your server | Requires session storage |
| **Stateless JWT cookie** | Zero infrastructure | Hard to invalidate before exp; back-channel logout MUST blocklist the sid until exp |

Server-side is the default recommendation. Use stateless only when you genuinely cannot run Redis.

---

## 9. Production checklist

- [ ] `redirect_uri` in admin UI matches your prod URL **exactly** (scheme, host, port, path). No trailing slash mismatch.
- [ ] `client_secret` stored in a secret manager (Vault, AWS SM, K8s Secret) — never in git.
- [ ] Both PKCE cookies (`auth_verifier` + `auth_state`) are HttpOnly + SameSite=Lax + Secure (in HTTPS).
- [ ] Application session cookie is HttpOnly + SameSite=Lax + Secure (in HTTPS).
- [ ] Logout webhook endpoint reachable from account-service and HMAC-verified.
- [ ] `state` validated on every callback; mismatch = reject.
- [ ] `code_verifier` stored once per attempt and cleared after use.
- [ ] Refresh token rotation handled: store the new refresh on every `/token` reply.
- [ ] On `invalid_grant` from `/token`: drop session, send user back to `/auth/login`.
- [ ] Health-check that hits `/.well-known/oauth-authorization-server` from your service at boot to fail-fast on misconfigured ACCOUNT_BASE_URL.

---

## 10. Common failure signatures

| Symptom | Cause | Fix |
|---|---|---|
| 400 `redirect_uri not registered` on `/authorize` | UI list doesn't include the URL exactly | Edit service in admin UI, add the URI. |
| 400 `invalid_grant` on `/token` (PKCE mismatch) | Lost the verifier (different cookie, different process) | Make verifier cookie name unique per attempt; store server-side if multi-instance. |
| 401 `invalid_client` on `/token` | Wrong `client_secret` | Regenerate in admin UI. |
| Token works once then 400 on second `/token` refresh | Refresh-token reuse — old token re-presented after rotation | Always overwrite stored refresh on each successful `/token`. |
| Webhook never fires | `logout_webhook_url` empty or unreachable from account-service | Set URL in admin UI; verify network reachability + HTTPS cert. |
| Webhook fires but signature fails | Reading body twice (raw bytes lost) | Buffer the raw body before parsing JSON; HMAC over the exact bytes. |
| Browser keeps bouncing through login | `Secure` cookie set over HTTP | Set `Secure` only when behind HTTPS; in dev, `SECURE_COOKIE=false`. |

---

## 11. Quick test (curl, no service)

```bash
ACCOUNT=http://localhost:8601
CLIENT_ID=<from UI>
CLIENT_SECRET=<from UI>

VERIFIER=$(openssl rand -hex 32)
CHALLENGE=$(echo -n "$VERIFIER" | openssl dgst -sha256 -binary | base64 | tr '/+' '_-' | tr -d '=')

# Open in browser, login, copy `code` from redirect URL:
echo "$ACCOUNT/authorize?response_type=code&client_id=$CLIENT_ID&redirect_uri=https://example.com/cb&code_challenge=$CHALLENGE&code_challenge_method=S256&state=demo"

CODE=<paste code>
curl -s -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d grant_type=authorization_code \
  -d code="$CODE" \
  -d redirect_uri=https://example.com/cb \
  -d code_verifier="$VERIFIER" \
  $ACCOUNT/token | jq
```

If that returns access + refresh tokens, your client_id/secret + redirect_uri are correctly registered. From there, port the curl into Go/Python/whatever.
