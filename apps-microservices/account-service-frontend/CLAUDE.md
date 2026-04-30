# account-service-frontend

Vue 3 SPA — login UI for `account-service-backend`. Forked and pruned from `public/admin-dashboad/`. Served by Nginx, proxies `/authorize`, `/token`, `/revoke`, `/introspect`, `/userinfo`, `/admin`, `/.well-known/*` to the backend container.

## Tech Stack

- Vue 3.5 + Vue Router 4.5
- Vite 6 + TypeScript 5.7
- Tailwind 4 + @tailwindcss/forms + @tailwindcss/typography
- Vitest (happy-dom) + @vue/test-utils

## Run

```bash
npm install
npm run dev          # dev server on http://localhost:5173
npm run build        # produces dist/
npm run test         # vitest
npm run type-check   # vue-tsc
```

## Routes

| Path | Purpose |
|------|---------|
| `/signin` | Email + password form, posts to `/authorize` |
| `/consent` | Allow/deny screen (auto-skipped for trusted clients server-side) |
| `/logout` | Confirmation page after revoke |
| `/error` | Generic error page |

## File Inventory

```
src/
  main.ts                       app bootstrap
  App.vue                       <router-view/>
  router/index.ts               4 routes + catch-all
  views/Auth/{Signin,Consent,Logout,Error}.vue
  composables/
    useOAuthFlow.ts             reads OAuth params from URL, posts /authorize
    useApi.ts                   fetch wrapper
  components/auth/AuthCard.vue  layout shell
  assets/main.css               Tailwind imports
nginx.conf                      proxy + SPA fallback
Dockerfile                      node:22-alpine build → nginx:1.27-alpine runtime
```

## Conventions

- TypeScript strict mode.
- All API calls via `useApi.postJson`.
- OAuth params read from `route.query` only; NEVER stored in localStorage.
- Generic error messages — never enumerate (no "user not found" vs "wrong password").
- Tailwind utility classes; design follows project frontend guidelines.
