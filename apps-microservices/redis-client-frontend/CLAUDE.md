# redis-client-frontend

Web UI for browsing and managing Redis cache entries.

## Tech Stack

- **Framework:** Next.js 16 (React 19, TypeScript)
- **UI:** Radix UI, Tailwind CSS 4, shadcn/ui
- **Redis:** `redis` npm package (v4)
- **Forms:** React Hook Form + Zod
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
  page.tsx                    # Main Redis browser page
  layout.tsx
  globals.css
  actions/
    cache-actions.ts          # Server actions for Redis operations
components/                   # UI components
hooks/
lib/
styles/
public/
```

## Conventions

- `output: 'standalone'` in next.config.mjs
- Server actions (`cache-actions.ts`) connect directly to Redis
- TypeScript build errors ignored (`ignoreBuildErrors: true`)

## Dependencies

- **Redis** server (connection via `redis` npm package)
