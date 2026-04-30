# account_service — Integration Guide for Consumers

**Audience:** developers or LLM agents integrating an existing service (e.g., `api-gateway`, `mcp-gateway-frontend`, future) with `account_service` for centralized login.

**Companion design spec:** `2026-04-30-account-service-design.md` in this same folder. Read it first if you need the full architecture rationale.

---

## Domain Note

- All consumer services and `account_service` itself are hosted under **`*.hellopro.eu`** (e.g. `account.hellopro.eu`, `gateway.hellopro.eu`, `my-service.hellopro.eu`).
- The **upstream HelloPro credential validation endpoint** (`HELLOPRO_AUTH_URL`, used internally by `account-service-backend` via `httpx`) lives on **`hellopro.fr`**. This is a backend-to-backend call only — it is never exposed to browsers, consumer services, or end users.
- Consumers only ever talk to `*.hellopro.eu` endpoints.

## TL;DR

`account_service` is an OAuth2 Authorization Code + PKCE provider. Your service:

1. Redirects unauthenticated users to the account-service login page with a `client_id`, `redirect_uri`, `state`, and PKCE `code_challenge`.
2. Receives an authorization `code` on its `/auth/callback` route.
3. Exchanges the `code` for an `access_token` (RS256 JWT, 15 min) + `refresh_token` (opaque, 30 d) via the token endpoint.
4. Stores both tokens in HttpOnly Secure cookies on its own domain.
5. Validates the access token on each request by verifying the RS256 signature with a cached JWKS public key (no backend round-trip on the hot path).
6. Refreshes when the access token expires.
7. Revokes the refresh token on logout.

---

## 1. Register Your Service as an OAuth Client

Ask the account_service admin (or use the admin endpoint with `X-Admin-Key`) to create an `OAuthClient` row:

```bash
curl -X POST https://account.hellopro.eu/admin/clients \
  -H "X-Admin-Key: $GATEWAY_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "my-service",
    "name": "My Service",
    "redirect_uris": ["https://my-service.hellopro.eu/auth/callback"],
    "post_logout_redirect_uris": ["https://my-service.hellopro.eu/"],
    "skip_consent": true
  }'
```

Response includes `client_secret` exactly **once**. Store it in your service's secret manager / `.env`.

**Important:** `redirect_uris` are matched **exactly** — no trailing slashes, no wildcards, no path differences. List every variant your service needs.

---

## 2. Required Environment Variables

Add these to your service's `app/core/settings.py` (Pydantic `BaseSettings`):

```python
class Settings(BaseSettings):
    OAUTH_CLIENT_ID: str
    OAUTH_CLIENT_SECRET: str
    OAUTH_AUTHORIZE_URL: str          # e.g. https://account.hellopro.eu/signin
    OAUTH_TOKEN_URL: str              # e.g. https://account.hellopro.eu/token
    OAUTH_JWKS_URL: str               # e.g. https://account.hellopro.eu/.well-known/jwks.json
    OAUTH_REVOKE_URL: str             # e.g. https://account.hellopro.eu/revoke
    OAUTH_LOGOUT_URL: str             # e.g. https://account.hellopro.eu/logout
    OAUTH_REDIRECT_URI: str           # e.g. https://my-service.hellopro.eu/auth/callback
    SESSION_SECRET: str               # cookie signing key
```

Never hardcode these — project rule: all infra connection strings via env (`.claude/rules/security.md`).

---

## 3. Login Flow — Consumer Side

### 3.1 Generate PKCE + redirect to account_service

When the user hits a protected route without a valid session:

```python
import base64, hashlib, secrets
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()

def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


@router.get("/auth/start")
async def auth_start(request: Request, next: str = "/"):
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)

    # Store verifier + state + post-login destination in the user's session
    request.session["oauth_verifier"] = verifier
    request.session["oauth_state"] = state
    request.session["oauth_next"] = next

    params = {
        "client_id": settings.OAUTH_CLIENT_ID,
        "redirect_uri": settings.OAUTH_REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{settings.OAUTH_AUTHORIZE_URL}?{qs}", status_code=303)
```

### 3.2 Handle the callback

```python
import httpx
from fastapi import HTTPException, Response


@router.get("/auth/callback")
async def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        raise HTTPException(400, f"OAuth error: {error}")

    expected_state = request.session.pop("oauth_state", None)
    if not state or state != expected_state:
        raise HTTPException(400, "Invalid state (possible CSRF)")

    verifier = request.session.pop("oauth_verifier", None)
    if not verifier:
        raise HTTPException(400, "Missing PKCE verifier")

    next_url = request.session.pop("oauth_next", "/")

    # Exchange code for tokens
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            settings.OAUTH_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.OAUTH_REDIRECT_URI,
                "client_id": settings.OAUTH_CLIENT_ID,
                "client_secret": settings.OAUTH_CLIENT_SECRET,
                "code_verifier": verifier,
            },
        )
    if r.status_code != 200:
        raise HTTPException(502, f"Token exchange failed: {r.text}")

    tokens = r.json()
    response = RedirectResponse(next_url, status_code=303)
    _set_auth_cookies(response, tokens)
    return response


def _set_auth_cookies(response: Response, tokens: dict) -> None:
    response.set_cookie(
        "access_token",
        tokens["access_token"],
        max_age=tokens["expires_in"],
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        tokens["refresh_token"],
        max_age=30 * 24 * 3600,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/auth",       # only sent to refresh / logout endpoints
    )
```

### 3.3 Validate the access token on each request

```python
import time
import jwt
import httpx
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, Request

_JWKS_CLIENT: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _JWKS_CLIENT
    if _JWKS_CLIENT is None:
        _JWKS_CLIENT = PyJWKClient(settings.OAUTH_JWKS_URL, cache_keys=True, lifespan=86400)
    return _JWKS_CLIENT


async def require_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(401, "Not authenticated")

    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],                           # NEVER allow alg=none
            audience=settings.OAUTH_CLIENT_ID,
            options={"require": ["exp", "iat", "sub", "aud"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}")

    return {"sub": claims["sub"], "email": claims.get("email"), "display_name": claims.get("display_name")}
```

Use as a FastAPI dependency:

```python
@router.get("/me")
async def me(user: dict = Depends(require_user)):
    return user
```

### 3.4 Refresh on expiry

When access token is expired but refresh token is present, exchange:

```python
@router.post("/auth/refresh")
async def auth_refresh(request: Request):
    refresh = request.cookies.get("refresh_token")
    if not refresh:
        raise HTTPException(401, "No refresh token")

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            settings.OAUTH_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": settings.OAUTH_CLIENT_ID,
                "client_secret": settings.OAUTH_CLIENT_SECRET,
            },
        )
    if r.status_code != 200:
        # refresh revoked or expired → force re-login
        response = RedirectResponse("/auth/start", status_code=303)
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/auth")
        return response

    tokens = r.json()
    response = JSONResponse({"refreshed": True})
    _set_auth_cookies(response, tokens)
    return response
```

Keep refresh transparent: middleware can detect `ExpiredSignatureError` and call `/auth/refresh` automatically before failing.

### 3.5 Logout

```python
@router.post("/auth/logout")
async def auth_logout(request: Request):
    refresh = request.cookies.get("refresh_token")
    if refresh:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                settings.OAUTH_REVOKE_URL,
                data={
                    "refresh_token": refresh,
                    "client_id": settings.OAUTH_CLIENT_ID,
                    "client_secret": settings.OAUTH_CLIENT_SECRET,
                },
            )

    response = RedirectResponse(
        f"{settings.OAUTH_LOGOUT_URL}?post_logout_redirect_uri=https://my-service.hellopro.eu/",
        status_code=303,
    )
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/auth")
    return response
```

---

## 4. Login Flow — Vue / SPA Consumer

If your service is a pure SPA (no backend session), the steps mirror the above but PKCE state must be stored in `sessionStorage` (NOT `localStorage`, to scope to the tab) and tokens in memory or HttpOnly cookies set by a tiny backend endpoint.

**Recommended:** keep a thin backend (even one route) for the token exchange so `client_secret` never ships to the browser. If you cannot, register a **public client** (no secret) — but this requires updating account_service to support public clients (not in v1 scope).

```ts
// composables/useOAuthFlow.ts (sketch — only if service has its own SPA login)
async function pkcePair(): Promise<[string, string]> {
  const arr = new Uint8Array(32)
  crypto.getRandomValues(arr)
  const verifier = base64url(arr)
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
  const challenge = base64url(new Uint8Array(digest))
  return [verifier, challenge]
}
```

For most consumers in this monorepo (FastAPI-backed), prefer the section 3 flow.

---

## 5. Security Checklist (must pass before merging integration)

- [ ] `client_secret` never logged, never committed, never exposed in browser bundles.
- [ ] `state` parameter generated with `secrets.token_urlsafe(32)` (or equivalent CSPRNG), verified on callback.
- [ ] `code_verifier` stored server-side per session, not in cookies or query strings.
- [ ] All cookies: `HttpOnly=True`, `Secure=True`, `SameSite=Lax` (or `Strict` if no cross-site post-login redirect needed).
- [ ] `refresh_token` cookie path scoped to `/auth` (not `/`) — so it isn't sent on every API request.
- [ ] JWT verification uses RS256 only — explicitly reject `alg=none` and HS256.
- [ ] `audience` claim verified against `OAUTH_CLIENT_ID`.
- [ ] JWKS cached (24h) with refetch on `kid` mismatch — no per-request fetch.
- [ ] HTTPS enforced everywhere in production.
- [ ] No service URLs / secrets hardcoded — all via Pydantic `BaseSettings`.
- [ ] `Authorization` and `Cookie` headers redacted in logs.

---

## 6. Common Pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| `invalid_redirect_uri` on `/authorize` | URI not exact-match in `OAuthClient.redirect_uris` | Update client row; ensure no trailing slash mismatch |
| `invalid_grant` on `/token` immediately after login | Code already consumed (browser back button → re-submit) | Render error page; tell user to re-login |
| `invalid_grant` on `/token` after a refresh that "worked" elsewhere | Refresh-token reuse triggered chain revocation | Don't share refresh tokens between tabs / processes; rely on rotation |
| Token validates but `aud` mismatch | Wrong `OAUTH_CLIENT_ID` env var | Match the registered `client_id` exactly |
| Sporadic 401s after deploy | JWKS cache stale during key rotation | Refetch JWKS on `kid` not in cache, then retry once |
| `Set-Cookie` not honored cross-tab | Cookie path scoped too narrowly | `path="/"` for access token; `path="/auth"` only for refresh |
| Browser drops cookie | Missing `Secure` on HTTPS site, or `SameSite=None` without `Secure` | Always set both `Secure=True` and `SameSite=Lax` |

---

## 7. Local Development

In `docker-compose.override.yml`, point your service at the local account_service:

```yaml
my-service:
  environment:
    - OAUTH_CLIENT_ID=my-service-dev
    - OAUTH_CLIENT_SECRET=${MY_SERVICE_OAUTH_SECRET}
    - OAUTH_AUTHORIZE_URL=http://localhost:8081/signin
    - OAUTH_TOKEN_URL=http://account-service-backend:8000/token
    - OAUTH_JWKS_URL=http://account-service-backend:8000/.well-known/jwks.json
    - OAUTH_REVOKE_URL=http://account-service-backend:8000/revoke
    - OAUTH_LOGOUT_URL=http://localhost:8081/logout
    - OAUTH_REDIRECT_URI=http://localhost:PORT/auth/callback
```

Register a `my-service-dev` client with `redirect_uris=["http://localhost:PORT/auth/callback"]`. Note: cookies set by HTTP localhost will NOT have `Secure=True` (browser would drop them) — toggle `Secure` based on `ENV == "dev"`.

---

## 8. Testing Your Integration

Minimum tests to add to your service:

```python
# tests/test_auth_integration.py

async def test_protected_route_redirects_when_no_cookie(client):
    r = await client.get("/protected", follow_redirects=False)
    assert r.status_code == 303
    assert "OAUTH_AUTHORIZE_URL" in r.headers["location"] or "/signin" in r.headers["location"]


async def test_callback_rejects_bad_state(client, fake_session):
    fake_session["oauth_state"] = "expected"
    r = await client.get("/auth/callback?code=x&state=wrong")
    assert r.status_code == 400


async def test_protected_route_passes_with_valid_jwt(client, valid_jwt_cookie):
    r = await client.get("/protected", cookies={"access_token": valid_jwt_cookie})
    assert r.status_code == 200


async def test_protected_route_rejects_alg_none(client, alg_none_token):
    r = await client.get("/protected", cookies={"access_token": alg_none_token})
    assert r.status_code == 401
```

Use `pytest-httpx` or `respx` to mock the token endpoint.

---

## 9. When to Skip This Service

Don't onboard your service to `account_service` if:

- It's a purely internal RPC service that never sees end-user traffic (use service-to-service tokens via api-gateway instead).
- It needs role-based access control today — v1 issues identity-only JWTs. Wait for v2 or layer your own RBAC on top of the `sub` claim.
- It needs sub-15-minute revocation — v1 access tokens are valid until `exp`. Use api-gateway proxy with introspect if you need this.

---

## 10. References

- Design spec: `docs/superpowers/specs/2026-04-30-account-service-design.md`
- OAuth2 Authorization Code: RFC 6749 §4.1
- PKCE: RFC 7636
- JWT: RFC 7519, JWKS: RFC 7517
- Refresh-token reuse detection: RFC 6819 §5.2.2.3
- Project security rules: `.claude/rules/security.md`
