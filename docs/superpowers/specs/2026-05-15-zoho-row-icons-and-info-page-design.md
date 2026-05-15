# Zoho Row Icons + Per-Row Info Page — Design Spec

**Date:** 2026-05-15
**Status:** Design approved by sandrianirinaharivelo@hellopro.fr
**Scope:** mcp-gateway-frontend (Vue 3 SPA) + mcp-gateway-service (Go backend)
**Builds on:** [2026-05-15-zoho-template-add-button-design.md](2026-05-15-zoho-template-add-button-design.md)

## Problem

The Zoho admin/user row actions today (`Tester`, `Découvrir`, `Modifier`, `Supprimer`, `Activer`/`Désactiver`) are full-text buttons that crowd the row, especially in `ZohoUserList`'s DataTable (6 buttons per row). There is also no way to drill into a single import row to inspect its persisted tool catalog or full metadata — the only signals are the truncated URL + redacted header keys shown inline.

## Goals

- Replace every text action button on `ZohoAdminCard` and `ZohoUserList` with an icon-only button (PrimeIcons + native tooltip), via one shared `IconActionButton.vue` component.
- Add a sixth `pi pi-info-circle` action that opens a dedicated detail page for that row.
- New detail page shows row metadata, the persisted tool catalog, and inline Tester / Découvrir actions.
- Backend exposes a new `GET /api/v1/zoho-imports/{id}/tools` so the detail page can fetch the catalog.

## Non-Goals

- No edit form on the detail page — keep the existing `Modifier` flow.
- No per-tool editing / deletion / muting.
- No SSE / live updates after Discover — refresh-on-click only.
- No icon-button rollout outside the two Zoho components in this spec.
- No change to the existing 5 row actions' semantics — same emits, same handlers.

## User Flow

1. User opens `/admin/templates/zoho`.
2. Each Zoho row (admin singleton or user) now shows 5 or 6 icon-only buttons:
   - **Info** (`pi-info-circle`)
   - **Tester** (`pi-bolt`)
   - **Découvrir** (`pi-sync`, brand tone)
   - **Toggle** *(user rows only)* — `pi-pause` when active, `pi-play` when inactive
   - **Modifier** (`pi-pencil`)
   - **Supprimer** (`pi-trash`, danger tone)
3. Hovering any button shows the native tooltip ("Détails", "Tester", etc.).
4. Click Info → `router.push({ name: 'zoho-import-detail', params: { slug, id } })`.
5. Detail page loads. Header shows row name + a small badge ("Compte admin" or "Utilisateur").
6. Metadata block lists: nom, url, créé par (hidden for admin), actif, template, header keys, created_at, updated_at.
7. Test / Découverte block: two buttons + last test badge + last discover summary.
8. Tools block: list of `{name, description, input_schema}` items, each with a collapsible `<details>` for the schema. Empty-state message when the persisted catalog is empty.
9. Click `← Retour` → `router.push({ name: 'template-detail', params: { slug } })`.

## Frontend Changes

### New file — `src/components/ui/IconActionButton.vue`

Single source of truth for the icon-only buttons. ~40 lines.

Props:
- `icon: string` — PrimeIcon class suffix (e.g. `'pi-bolt'`).
- `label: string` — used for both `title` attribute and `aria-label`.
- `tone?: 'neutral' | 'brand' | 'danger'` — default `'neutral'`.
- `disabled?: boolean`.

Emits: `click: [MouseEvent]`.

Tailwind classes:
- Base: `inline-flex items-center justify-center w-8 h-8 rounded-md border text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed`.
- neutral: `border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5`
- brand: `border-brand-300 dark:border-brand-700 text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-500/10`
- danger: `border-error-300 dark:border-error-700 text-error-600 hover:bg-error-50 dark:hover:bg-error-500/10`

### Modified — `src/components/zoho/ZohoAdminCard.vue`

Replace lines 17-40 (the four text buttons) with five `<IconActionButton>` instances in this order: Info / Tester / Découvrir / Modifier / Supprimer. Add `info` to `defineEmits`. Import `IconActionButton`.

### Modified — `src/components/zoho/ZohoUserList.vue`

Replace lines 78-107 (the six text buttons) with six `<IconActionButton>` instances in this order: Info / Tester / Découvrir / Toggle / Modifier / Supprimer. The Toggle button reads `data.is_active` to pick `pi-pause` vs `pi-play` and to set its label. Add `info: [r: ZohoImportRow]` to `defineEmits`. Drop the `Actions` column header-style width from `22rem` to `18rem` (six icon-only buttons fit comfortably in less space). Import `IconActionButton`.

### Modified — `src/components/zoho/ZohoImportsSection.vue`

Wire `@info` from both children. Two new handlers:

```ts
function onInfoAdmin() {
  if (!store.admin) return
  router.push({
    name: 'zoho-import-detail',
    params: { slug: props.templateSlug, id: store.admin.id },
  })
}
function onInfoUser(r: ZohoImportRow) {
  router.push({
    name: 'zoho-import-detail',
    params: { slug: props.templateSlug, id: r.id },
  })
}
```

Bindings: `<ZohoAdminCard ... @info="onInfoAdmin">` and `<ZohoUserList ... @info="onInfoUser">`.

### New file — `src/views/ZohoImportDetailView.vue`

~250 lines. Props: `slug: string`, `id: string` (via `props: true`).

Layout:
- Header: `← Retour` button + `<h1>` showing `row.name` + small badge ("Compte admin" / "Utilisateur").
- Metadata card (`<dl>` block): nom, url, créé par (only if `!row.is_admin`), actif, template_slug, auth_header_keys (joined), created_at, updated_at.
- Test/Discover card: two `IconActionButton`s (or larger labelled buttons — implementer's call, but keep style consistent with detail-page conventions in `BDDTableDetailView` if it exists). Renders `ZohoTestResultBadge` + a `Découverte : N outils` badge after each action.
- Tools card: heading `Outils ({{ total }})`; for each tool a small block with name, description, and a `<details>` containing the `input_schema` JSON pretty-printed. Empty state: *"Aucun outil découvert. Lancez « Découvrir » pour peupler le catalogue."*

Data loading on mount:
1. `zohoImportsApi.getByID(id)` → row metadata. 404 → render "Import introuvable" + back link.
2. `zohoImportsApi.listTools(id)` → tool catalog. Error → toast `Erreur lors du chargement du catalogue` and render the empty state (non-fatal).

Action handlers:
- Tester → `store.testRow(id)` → store result locally, render `ZohoTestResultBadge`.
- Découvrir → `store.discoverRow(id)` → store result locally; on success, re-fetch `listTools` and re-render the Tools card.

### Modified — `src/router/index.ts`

Add route immediately above the `zoho-import-new` route (specific paths before parent catch-alls):

```ts
{
  path: '/admin/templates/:slug/zoho-imports/:id',
  name: 'zoho-import-detail',
  component: () => import('@/views/ZohoImportDetailView.vue'),
  meta: { requiresAuth: true, title: 'Détails import Zoho', minRole: 'admin' },
  props: true,
},
```

### Modified — `src/api/zohoImports.ts`

Add a `listTools` method on `zohoImportsApi`:

```ts
listTools(id: string): Promise<ZohoImportToolsResponse> {
  return api.get<ZohoImportToolsResponse>(`${BASE}/${encodeURIComponent(id)}/tools`)
},
```

### Modified — `src/types/zoho.ts`

Add:

```ts
export interface ZohoImportTool {
  name: string
  description: string
  input_schema: string
  updated_at: string
}

export interface ZohoImportToolsResponse {
  tools: ZohoImportTool[]
  total: number
}
```

## Backend Changes

### Modified — `internal/api/zoho_admin_handlers.go`

In `handleZohoImportByID`, add a new subroute branch alongside the existing `test` / `discover` branches:

```go
if rest == "tools" {
    h.handleZohoImportTools(w, r, id)
    return
}
```

New handler `handleZohoImportTools(w, r, id)`:
1. Reject non-GET → 405.
2. `repo.GetByID(id)` → 404 if missing, 500 on error.
3. `repo.ListTools(id)` → 500 on error.
4. Marshal `[]db.ZohoImportTool` to `[]ZohoImportToolDTO` via `zohoImportToolToDTO`.
5. Respond 200 with `{tools: [...], total: N}`.

### Modified — `internal/api/zoho_admin_dto.go`

Add:

```go
// ZohoImportToolDTO is one row of the GET /api/v1/zoho-imports/{id}/tools
// response. input_schema is returned as the raw JSON string persisted in
// zoho_import_tools — the client parses it for display.
type ZohoImportToolDTO struct {
    Name        string `json:"name"`
    Description string `json:"description"`
    InputSchema string `json:"input_schema"`
    UpdatedAt   string `json:"updated_at"`
}
```

Add private helper `zohoImportToolToDTO(*db.ZohoImportTool) ZohoImportToolDTO`.

## Tests

### Backend (`zoho_admin_handlers_test.go`)

1. `TestHandleZohoImportTools_Happy` — seed a user row + 2 tools via `repo.ReplaceTools`, GET `/api/v1/zoho-imports/{id}/tools`, expect 200 with `total: 2` and both names present in the body.
2. `TestHandleZohoImportTools_RowNotFound` — GET against an unknown id → 404.
3. `TestHandleZohoImportTools_EmptyCatalog` — row exists, no `ReplaceTools` call → 200 with `total: 0` and `tools: []`.
4. `TestHandleZohoImportTools_MethodNotAllowed` — POST → 405.

Use the existing `newTestZohoAdminHandler(t)` fixture.

### Frontend (`src/api/zohoImports.spec.ts`)

One new test: `zohoImportsApi.listTools` issues `GET /api/v1/zoho-imports/{id}/tools` (via `api.get`) and resolves to the `{tools, total}` response. Mirrors the existing `create` test.

### Manual smoke

- Open `/admin/templates/zoho`. Confirm all rows show 5 (admin) or 6 (user) icon-only buttons in the correct order; native tooltips render French labels on hover.
- Click Info on the admin card → detail page renders metadata + empty-state tools list (assuming a fresh row).
- Click Découvrir on the detail page → tool list refreshes; spinner-free, badge updates.
- Click Tester → badge renders ok/error.
- Click Info on a user row → same page renders with `created_by` visible.
- Navigate to a non-existent id → "Import introuvable" view + back link works.

## CLAUDE.md Updates

### `apps-microservices/mcp-gateway-service/CLAUDE.md`

In the "Zoho Imports Admin" subsection, append:

> - `GET /api/v1/zoho-imports/{id}/tools` — list the persisted tool catalog for one row. Body: `{tools: [{name, description, input_schema, updated_at}], total}`. Returns 200 (empty list when catalog empty), 404 when the row is missing. Read-only — refresh the catalog via `POST /api/v1/zoho-imports/{id}/discover`.

### `apps-microservices/mcp-gateway-frontend/CLAUDE.md`

Extend the "Zoho imports admin onglet" subsection with:

> Per-row detail page: `/admin/templates/:slug/zoho-imports/:id` (`ZohoImportDetailView.vue`). Renders metadata, persisted tool catalog from `GET /api/v1/zoho-imports/{id}/tools`, plus inline Tester / Découvrir actions. Reachable via the `pi pi-info-circle` icon on every row in `ZohoAdminCard` + `ZohoUserList`. All row actions (Détails / Tester / Découvrir / Activer-Désactiver / Modifier / Supprimer) use the shared `components/ui/IconActionButton.vue` (icon-only with native tooltip, three tones: neutral / brand / danger).

Also add `IconActionButton.vue` and `ZohoImportDetailView.vue` to the File Inventory.

## Acceptance Criteria

- `IconActionButton.vue` created and consumed by both `ZohoAdminCard` and `ZohoUserList`. No other text-button code paths remain in those two files.
- Action order: Info → Tester → Découvrir → (Toggle, user-only) → Modifier → Supprimer.
- Toggle button picks `pi-pause` (active) / `pi-play` (inactive) and changes its tooltip accordingly.
- New route `zoho-import-detail` registered, admin-gated, props injected.
- `ZohoImportDetailView` renders metadata, tools list (or empty state), and working Tester + Découvrir actions that update the displayed catalog after a successful discover.
- Backend `GET /api/v1/zoho-imports/{id}/tools` returns the documented shape; covered by 4 unit tests.
- Frontend api client gains `listTools`, covered by 1 vitest spec.
- Both CLAUDE.md files updated.

## Out of Scope / Future Work

- Per-tool actions (mute/disable individual tools).
- Tool catalog diffing or history.
- Live websocket/SSE refresh.
- Bulk re-discovery from the list views (already covered by per-row Discover).
- Migration of the `auth_header_keys` rendering to its own component.
