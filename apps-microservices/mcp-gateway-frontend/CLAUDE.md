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
    bdd/BDDFieldBlock.vue         # single-field block (mirrors InstructionRow pattern)
    common/Paginator.vue          # generic page <-> page navigator
  router/       # Vue Router with auth guard
  stores/       # Pinia stores (auth, servers)
  types/        # TypeScript interfaces matching Go backend
  views/        # LoginView, ServersView, TokensView, OAuth2View, AuthorizeView, BDDTablesView
    BDDTableAddView.vue           # 3-step add wizard
    BDDTableFieldsView.vue        # fields-edit page (WYSIWYG + import/export + block builder)
    ZohoImportFormView.vue        # 3-step Zoho import form (admin or user scope)
nginx.conf      # Production reverse proxy config
Dockerfile      # Multi-stage: node build → nginx serve
```

## Conventions

- All API calls go through `src/api/client.ts` (typed fetch wrapper)
- Auth is cookie-based (HttpOnly JWT) — no token stored in JS
- Components follow `{domain}/{ComponentName}.vue` structure
- Global state (auth, servers) in Pinia; local state in composables
- French UI labels, English code identifiers

## BDD admin onglet (v2)

The "Tables BDD" admin section is split into a 3-tier flow:

1. **List view** at `/bdd-tables` — paginated, server-side, with an "All" tab
   plus per-database tabs. Uses the `bddApi.listUsed({ database_id, search,
   page, limit })` endpoint and renders status badges per row.
2. **Add wizard** at `/bdd-tables/new` — three steps: pick a database, then
   multi-select catalog tables, then preview a recap before firing
   `POST /bdd/used/tables/bulk` (atomic, cap 50 items).
3. **Fields-edit** at `/bdd-tables/:id/fields` — Tiptap WYSIWYG description
   editor + per-field block-builder (`BDDFieldBlock.vue`) + per-table
   import/export (JSON via `GET /bdd/used/tables/export` and `POST
   /bdd/used/tables/import`, capped at 1 MiB).

Both `/bdd-tables/new` and `/bdd-tables/:id/fields` are admin-gated through
the global `router.beforeEach` guard (`meta.minRole = 'admin'`).

## Provider-scope filter panels

The token and OAuth2 forms expose per-provider ownership-scope pickers when a
backend with the matching `tool_prefix` is selected:

| Component | Tool prefix | Backend DB field |
|---|---|---|
| `components/tokens/LeexiFilterPanel.vue` | `leexi` | `leexi_filter` (UUID strings) |
| `components/tokens/RingoverFilterPanel.vue` | `ringover` | `ringover_filter` (integer IDs) |
| `components/tokens/BDDFilterPanel.vue` | `bdd` | `bdd_filter.used_table_ids` |

Each panel fetches `GET /api/v1/{provider}/users|teams` (or the BDD
used-tables registry) from the gateway and gracefully renders a disabled
state on 503. The selected scope is serialised into the create / update
payload only when the corresponding backend is in the picked set.

## Zoho imports admin onglet

Single-row manual creation is exposed at
`/admin/templates/:slug/zoho-imports/new?scope=admin|users`. The view
(`ZohoImportFormView.vue`) reuses the `StepTabs` wizard pattern (`Identité
→ Endpoint → Récapitulatif`) from `ServerFormView`. The `+ Ajouter` button
in `ZohoImportsSection` passes the active tab as `scope`; the form
branches between `store.upsertAdmin` (admin) and `store.createUserImport`
(users) on submit. On success it routes back to the template detail page
with `?zoho_tab=<scope>` so the section re-mounts on the correct tab.
Admin-gated through the global `router.beforeEach` guard.

## What This Provides to Other Services

- Admin UI for managing MCP servers, scope tokens, and OAuth2 clients
- OAuth2 authorization flow UI (login + consent)
- Admin onglet to curate which Hellopro BDD tables are exposed via MCP, with per-table description + per-field curation.
- Single entry point (nginx) for both frontend and Go backend
