# agent-task-manager-frontend

Agent Task Board UI (live board, task detail, questions inbox, agents presence) for the Rust
backend in `apps-microservices/agent-task-manager-backend`.

## Tech Stack
- Next.js 16.4 (App Router, `proxy.ts` instead of middleware, async `params`/`cookies`), React 19
- TanStack Query 5, openapi-fetch + openapi-typescript (generated `src/lib/api/schema.d.ts`)
- Tailwind 4 + shadcn/ui-style primitives in `src/components/ui.tsx`
- TypeScript 5.9 (pinned: openapi-typescript 7.13 requires ^5), Vitest, Playwright
- Port 3020; same origin as the API in production (Caddy ingress on 8620)

## Rules
- Never hand-write API types: `npm run gen:api` after a backend change (the backend's
  `scripts/check-openapi-drift.sh` fails otherwise).
- Only `src/realtime/reducers.ts` applies events to cached data; keep it pure and add a test for
  every new event type it handles.
- No optimistic workflow transitions: the server decides; show "pending" until the event arrives.
- All UI copy goes through `src/lib/i18n/fr.ts` (French); code and identifiers stay English.
- Next.js never touches the database: everything goes through the Rust API.

## Run / test
```bash
npm run dev | npm run build
npm run typecheck && npm run lint && npm test
npx playwright test     # needs the compose stack up (see README)
```
