# crawler-monitor-frontend

Real-time dashboard for monitoring web crawler jobs.

## Tech Stack

- **Framework:** Vite 7 + React 19 (JSX, no TypeScript)
- **UI:** Tailwind CSS 3, Lucide React, Recharts 3
- **Virtualization:** react-window
- **Date:** date-fns, react-date-range
- **Package Manager:** yarn

## Commands

| Action | Command |
|--------|---------|
| Dev | `yarn dev` |
| Build | `yarn build` |
| Preview | `yarn preview` |
| Lint | `yarn lint` (eslint) |

## Docker

- Multi-stage: yarn build, then served via **nginx**
- Port: **8099**
- Static SPA deployed behind nginx

## Folder Structure

```
src/
  App.jsx        # Main application component (monolithic)
  main.jsx       # Entry point
  App.css
  index.css
  assets/
tests/
  App.test.js    # Test stubs (node:test, placeholder)
index.html       # Vite entry HTML
nginx.conf       # Production nginx config
vite.config.js   # Dev proxy: /api -> localhost:3001
```

## Job Statuses

The frontend handles all crawler-service statuses:
- `running` (blue, spinning) — Crawl in progress
- `finished` (green) — Crawl completed successfully
- `failed` (red) — Crawl failed
- `stopping` (yellow) — Stop requested, awaiting completion
- `archived` (gray) — Job archived to GCS
- `restarting_oom` (orange, spinning) — OOM restart in progress

## Dashboard Features

- **Global stat cards** — Total, Success, Failed, Running, Archived counts
- **Capacity bar** — Real-time running/max slots from Redis
- **Failed callbacks badge** — Header alert when webhooks fail
- **Replica monitor** — Live CPU/RAM gauges per crawler replica
- **Job details** — Crawl mode (Standard/Update), OOM restart count, previous crawl ID
- **Request queue editor** — Browse, search, analyze, clean patterns, drop queue
- **Dataset analyzer** — Duplicate detection and purging
- **Advanced log viewer** — Search, filter by level, download (TXT/JSON/CSV)

## Conventions

- Dev proxy: `/api` requests forwarded to `http://localhost:3001` (crawler-monitor-backend)
- Plain JSX (no TypeScript)
- ESM modules (`"type": "module"`)
- French UI labels (no i18n)

## Dependencies

- **crawler-monitor-backend** (Express, port 3001) for API and WebSocket data
