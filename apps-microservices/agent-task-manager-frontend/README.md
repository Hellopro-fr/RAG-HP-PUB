# Agent Task Board — frontend (`agent-task-manager-frontend`)

Next.js 16 (App Router, TypeScript strict), TanStack Query, Tailwind 4 with shadcn/ui-style
primitives. UI copy in French (`src/lib/i18n/fr.ts`); code, logs and API in English.
Backend and full stack: [`../agent-task-manager-backend`](../agent-task-manager-backend).

## Architecture: server-authoritative cache fed by an ordered event stream

- **Server Components** load the initial snapshot (board with its `seq`, task context, inbox,
  presence) from the Rust server, forwarding the httpOnly session cookie (`src/lib/api/server.ts`).
- **Client components** own the live view: one `EventSource` per open project
  (`src/realtime/stream.tsx`) starting `after=<snapshot seq>`; the browser resumes with
  `Last-Event-ID` after a disconnect.
- **`src/realtime/reducers.ts`** is the only code that turns events into cache updates: pure,
  unit-tested, duplicate-safe, and it requests a refetch on any seq gap or unknown entity.
- **No optimistic workflow transitions**: the server decides; a card moves when its event arrives.
  Drag-and-drop only supports cancellation (the one human transition of phase 1).
- **API types are generated** from the backend's `openapi.json` (`npm run gen:api`), never written by hand.

## Pages (phase 1)

`/projects`, `/projects/[id]` (board), `/tasks/[id]` (spec + criteria, timeline, attempts,
inline answers), `/questions` (cross-project inbox, live via `/api/stream?topics=questions`),
`/agents` (presence; heartbeats are not events, so it polls every 5 s), `/login`.
`TODO(phase-2)`: reviews queue, spec editor. `TODO(phase-3)`: DAG view (`@xyflow/react`), time travel.

## Develop

```bash
npm ci
npm run dev          # http://localhost:3020; /api is rewritten to http://localhost:8621
# SSE through the dev proxy may be buffered: open it directly on the server instead
NEXT_PUBLIC_STREAM_ORIGIN=http://localhost:8621 npm run dev   # backend needs CORS_ORIGINS=http://localhost:3020
npm run typecheck && npm run lint && npm test
npm run gen:api      # after a backend API change
```

## End-to-end tests (Playwright)

Run against the full compose stack (ingress on :8620); credentials come from the backend `.env`.

```bash
(cd ../agent-task-manager-backend && docker compose up -d --build --wait)
npx playwright install chromium   # once
npx playwright test               # board-live (AC-1.7, < 1 s on two boards) + pages
```
