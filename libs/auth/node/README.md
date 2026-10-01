# @hellopro/auth

Framework-free account-service OAuth 2.1 + PKCE login core (config, oauth, session, flow).
Service-agnostic: reads `SERVICE_NAME` to derive `ACCOUNT_CLIENT_ID_<SLUG>`.

## Consume (Node/Next service)
1. `package.json`: `"@hellopro/auth": "file:../../libs/auth/node"`
2. Next: add `transpilePackages: ["@hellopro/auth"]` to `next.config`.
3. Docker: build from repo-root context, `COPY libs/auth/node` + your service, `pnpm install`.
4. Import: `import { startLogin, completeCallback, readSession, SESSION_COOKIE } from "@hellopro/auth"`.

Keep your own thin route handlers + middleware. See redis-client-frontend for a reference consumer.
