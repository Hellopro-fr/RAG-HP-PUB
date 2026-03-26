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
  App.jsx        # Main application component
  main.jsx       # Entry point
  App.css
  index.css
  assets/
index.html       # Vite entry HTML
nginx.conf       # Production nginx config
vite.config.js   # Dev proxy: /api -> localhost:3001
```

## Conventions

- Dev proxy: `/api` requests forwarded to `http://localhost:3001` (crawler-monitor-backend)
- Plain JSX (no TypeScript)
- ESM modules (`"type": "module"`)

## Dependencies

- **crawler-monitor-backend** (Express, port 3001) for API and WebSocket data
