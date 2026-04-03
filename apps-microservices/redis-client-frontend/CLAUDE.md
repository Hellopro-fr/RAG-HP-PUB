# redis-client-frontend

Web UI for browsing and managing Redis cache entries.

## Tech Stack

- **Framework:** Next.js 16 (React 19, TypeScript)
- **UI:** Radix UI (alert-dialog, slot, toast), Tailwind CSS 4, shadcn/ui
- **Redis:** `redis` npm package (v4)
- **Package Manager:** pnpm

## Commands

| Action | Command |
|--------|---------|
| Dev | `pnpm dev` |
| Build | `pnpm build` |
| Start | `pnpm start` |
| Lint | `pnpm lint` (eslint) |

## Docker

- Multi-stage pnpm build, standalone output
- Port: **3000**
- Non-root user (`nextjs:nodejs`)

## Folder Structure

```
app/
  page.tsx                    # Main Redis browser page (Server Component)
  layout.tsx
  globals.css
  login/
    page.tsx                  # Token-based login page
  actions/
    cache-actions.ts          # Server actions for Redis mutations
middleware.ts                 # Auth middleware (ADMIN_TOKEN env var)
components/                   # UI components (cache-header, cache-table, confirm-dialog)
hooks/
lib/
  domain/cache-entry.ts      # CacheEntry + CacheMetadata interfaces
  infrastructure/             # Redis repository (Singleton + SCAN)
  application/                # getCachedData use case (parallel fetches)
  utils.ts                    # cn(), formatBytes()
public/
```

## Conventions

- `output: 'standalone'` in next.config.mjs
- TypeScript build errors are enforced (`ignoreBuildErrors: false`)
- Redis uses `SCAN` (not `KEYS *`) for non-blocking key enumeration
- Authentication via `ADMIN_TOKEN` env var (middleware-based, cookie or Bearer header)
- Server actions validate key format before Redis operations
- Shared `formatBytes()` utility in `lib/utils.ts`

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `REDIS_HOST` | Yes | Redis server hostname |
| `REDIS_PORT` | Yes | Redis server port |
| `REDIS_SECRET` | Yes | Redis password |
| `ADMIN_TOKEN` | No | Auth token (if unset, auth is disabled — dev mode) |

## Dependencies

- **Redis** server (connection via `redis` npm package)
