# Account Service SSO — Smoke Runbook

End-to-end verification of the OAuth 2.1 + skip-consent + back-channel logout flow.

## Prerequisites

```bash
# .env at repo root must define:
ACCOUNT_PUBLIC_URL=https://account.example.com   # or http://localhost:8600 for dev
ACCOUNT_MYSQL_DSN=account:account@tcp(mysql:3306)/account_db?parseTime=true
ACCOUNT_ENCRYPTION_KEY=$(openssl rand -hex 32)
ACCOUNT_JWT_SECRET=$(openssl rand -hex 16)
ACCOUNT_JWT_AUDIENCE=https://www.hellopro.fr
HELLOPRO_AUTH_URL=https://www.hellopro.fr/login
ACCOUNT_ADMIN_EMAILS=youremail@hellopro.fr
ACCOUNT_FRONTEND_PORT=8601
```

## 1. Bring up the stack

```bash
docker compose up -d mysql account-service-backend account-service-frontend
docker compose logs -f account-service-backend &
```

Expected backend logs: `auto migrate ok`, then `listening :8600`. Container healthcheck flips to healthy within ~30s.

## 2. Hit health & metadata

```bash
curl -fsS http://localhost:8601/api/v1/admin/services -i        # expect 401 (no session)
curl -fsS http://localhost:8601/.well-known/oauth-authorization-server | jq
```

Metadata response must include `"issuer"`, `"authorization_endpoint"`, `"token_endpoint"`, `"code_challenge_methods_supported": ["S256"]`.

## 3. Admin login via UI

Open `http://localhost:8601/login` and submit credentials of an email listed in `ACCOUNT_ADMIN_EMAILS`. After login you land on `/admin/services`.

## 4. Register a test client service

In the UI, click **+ Nouveau service**. Fill:
- name: `test-client`
- redirect_uris: `https://example.com/cb`
- logout_webhook_url: `https://webhook.site/<your-token>`

After save, the modal shows `client_id` + `client_secret` ONCE. Copy both.

## 5. Run the OAuth 2.1 PKCE flow

```bash
CLIENT_ID=<from UI>
CLIENT_SECRET=<from UI>
VERIFIER=$(openssl rand -hex 32)
CHALLENGE=$(echo -n "$VERIFIER" | openssl dgst -sha256 -binary | base64 | tr '/+' '_-' | tr -d '=')
echo "open: http://localhost:8601/authorize?response_type=code&client_id=$CLIENT_ID&redirect_uri=https://example.com/cb&code_challenge=$CHALLENGE&code_challenge_method=S256&state=demo"
```

Open the printed URL. Login form appears (with branding fetched from `/authorize/branding/{client_id}.json`). Submit creds. Browser is 302'd to `https://example.com/cb?code=...&state=demo`. Copy the `code` param from the URL.

```bash
CODE=<from redirect>
curl -s -u "$CLIENT_ID:$CLIENT_SECRET" \
     -d grant_type=authorization_code \
     -d code="$CODE" \
     -d redirect_uri=https://example.com/cb \
     -d code_verifier="$VERIFIER" \
     http://localhost:8601/token | jq
```

Expected: `{access_token, token_type:"Bearer", expires_in:60, refresh_token}`.

## 6. Refresh + reuse-detection

```bash
REFRESH=<refresh_token from previous>
curl -s -u "$CLIENT_ID:$CLIENT_SECRET" \
     -d grant_type=refresh_token \
     -d refresh_token="$REFRESH" \
     http://localhost:8601/token | jq    # success: new tokens, refresh rotated
curl -s -u "$CLIENT_ID:$CLIENT_SECRET" \
     -d grant_type=refresh_token \
     -d refresh_token="$REFRESH" \
     http://localhost:8601/token | jq    # expected: {"error":"invalid_grant"}
```

In the UI: `Admin → Audit` shows a `token_reuse_attack`-style entry; `User → Sessions` shows all sessions for that user as `revoked`.

## 7. Back-channel logout

In the UI, click `Révoquer` next to the active user. Watch the `webhook.site` URL.

Expected POST:
- Header `X-Logout-Signature: sha256=<hex>` matches `HMAC_SHA256(client_secret, body)`.
- Body JSON `{iss, sub, sid, iat, events: {"http://schemas.openid.net/event/backchannel-logout": {}}}`.
- Replay window: `iat` must be within 5 minutes — clients SHOULD reject older events.

## 8. Smoke result template

Paste into PR description on `features/account-service`:

```
[ ] /health 200
[ ] /.well-known returns metadata
[ ] Admin login UI succeeds
[ ] Client registered, secret captured once
[ ] PKCE flow returns access + refresh tokens (TTL 60s)
[ ] Refresh rotates; reuse triggers chain revocation + audit entry
[ ] Logout webhook delivered with valid HMAC signature
```

## Failure signatures

- `connection refused` from backend → MYSQL_DSN wrong or mysql not healthy.
- `ENCRYPTION_KEY must be 32 bytes hex` → set via `openssl rand -hex 32`.
- `auth URL must use HTTPS` → AUTH_URL must be HTTPS unless localhost.
- `redirect_uri not registered` (400) on /authorize → form must POST the same redirect_uri that's registered on the client; check JSON column `oauth2_clients.redirect_uris`.
- `PKCE mismatch` (400) on /token → verifier sent doesn't match challenge stored. Confirm `S256(verifier)` is base64url-without-padding.
