# account-service-frontend

Vue 3 SPA admin UI + dual-mode login form for the centralized SSO server (account-service-backend).

## Tech Stack

- Vue 3.5 + TypeScript 5.7
- Vite 6 (build + dev server)
- Pinia (auth store)
- Tailwind CSS 4 (TailAdmin Pro 2.0 template — cloned from `public/admin-dashboad`)
- Vitest (unit tests)
- nginx 1.27-alpine (production serving + reverse proxy to backend on port 8600)

## Run

```bash
cd apps-microservices/account-service-frontend
npm install
ACCOUNT_BACKEND_URL=http://localhost:8600 npm run dev
# Open http://localhost:5173
```

## Spec & Plan

- Spec: `docs/superpowers/specs/2026-05-04-account-service-sso-design.md`
- Plan: `docs/superpowers/plans/2026-05-04-account-service-sso.md` (Phases 8-12)
