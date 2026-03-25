# api-chatbot-html-service

Chatbot UI for HTML-based conversational search.

## Tech Stack

- **Framework:** Next.js 15.2.4 (React 19, TypeScript)
- **UI:** Radix UI, Tailwind CSS 4, shadcn/ui, Framer Motion
- **Forms:** React Hook Form + Zod
- **Charts:** Recharts
- **Package Manager:** pnpm
- **Runtime:** Node.js 20

## Commands

| Action | Command |
|--------|---------|
| Dev | `pnpm dev` |
| Build | `pnpm build` |
| Start | `pnpm start` |
| Lint | `pnpm lint` (eslint) |

## Docker

- Port: **3000**
- Base: `node:20`
- Build: `pnpm run build` then `pnpm start`

## Folder Structure

```
app/
  api/chat/route.js    # Chat API route
  page.tsx             # Main chatbot page
  layout.tsx
  globals.css
components/            # Reusable UI components
hooks/
lib/
styles/
public/
```

## API Endpoints

- `POST /api/chat` -- Chat completion route

## Conventions

- Path alias: `@/*` maps to project root
- TypeScript strict mode enabled
- Target: ES6, module: ESNext
- Images: unoptimized (via next.config.mjs)

## Dependencies

- Calls an external LLM/chat backend via the `/api/chat` route
