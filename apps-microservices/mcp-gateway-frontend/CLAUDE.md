# mcp-gateway-frontend

Vue 3 SPA frontend for the MCP Gateway Service admin UI.

## Tech Stack

- Vue 3.5 + TypeScript 5.7
- Vite 6 (build + dev server)
- PrimeVue 4 (Aura theme) + Radix Vue (headless dialogs)
- Tailwind CSS 4 (CSS-based config via @theme)
- Pinia (auth + servers stores) + composables
- vue-draggable-plus (nested DnD)
- nginx 1.27-alpine (production serving + reverse proxy)

## Run

```bash
# Development (requires Go backend on :8581)
cd apps-microservices/mcp-gateway-frontend
npm install
npm run dev
# Open http://localhost:5173

# Docker build
docker build -t mcp-gateway-frontend .
docker run -p 8581:8581 mcp-gateway-frontend
```

## File Inventory

```
src/
  api/          # Typed fetch wrapper + per-resource API modules
  composables/  # useClipboard, useToast, useDragDrop
  components/   # layout/, servers/, tokens/, oauth2/, bdd/, shared/
  router/       # Vue Router with auth guard
  stores/       # Pinia stores (auth, servers)
  types/        # TypeScript interfaces matching Go backend
  views/        # LoginView, ServersView, TokensView, OAuth2View, AuthorizeView, BDDTablesView
nginx.conf      # Production reverse proxy config
Dockerfile      # Multi-stage: node build → nginx serve
```

## Conventions

- All API calls go through `src/api/client.ts` (typed fetch wrapper)
- Auth is cookie-based (HttpOnly JWT) — no token stored in JS
- Components follow `{domain}/{ComponentName}.vue` structure
- Global state (auth, servers) in Pinia; local state in composables
- French UI labels, English code identifiers

## Provider-scope filter panels

The token and OAuth2 forms expose per-provider ownership-scope pickers when a
backend with the matching `tool_prefix` is selected:

| Component | Tool prefix | Backend DB field |
|---|---|---|
| `components/tokens/LeexiFilterPanel.vue` | `leexi` | `leexi_filter` (UUID strings) |
| `components/tokens/RingoverFilterPanel.vue` | `ringover` | `ringover_filter` (integer IDs) |
| `components/bdd/BDDFilterPanel.vue` | `bdd` | `bdd_filter.used_table_ids` |

Each panel fetches `GET /api/v1/{provider}/users|teams` (or the BDD
used-tables registry) from the gateway and gracefully renders a disabled
state on 503. The selected scope is serialised into the create / update
payload only when the corresponding backend is in the picked set.

## What This Provides to Other Services

- Admin UI for managing MCP servers, scope tokens, and OAuth2 clients
- OAuth2 authorization flow UI (login + consent)
- Admin onglet to curate which Hellopro BDD tables are exposed via MCP, with per-table description + per-field curation.
- Single entry point (nginx) for both frontend and Go backend
