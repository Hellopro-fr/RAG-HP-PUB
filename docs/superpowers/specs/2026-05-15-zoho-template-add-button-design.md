# Zoho Template — "Add" Button + Tabbed Form

**Date:** 2026-05-15
**Status:** Design approved by sandrianirinaharivelo@hellopro.fr
**Scope:** mcp-gateway-service (Go backend) + mcp-gateway-frontend (Vue 3 SPA)

## Problem

The Zoho template detail page (`/admin/templates/zoho`) exposes the `ZohoImportsSection` with two tabs — **Admin** (singleton row) and **Utilisateurs** (per-user rows). Today the only way to create a row is the bulk **"Importer depuis Sheets"** flow. Users want a single-row, manual, tabbed "Add" form mirroring the same fields the sheet importer collects, with the same multi-step wizard layout as the existing "Add server" page (`ServerFormView`).

## Goals

- Add `+ Ajouter` button in the `ZohoImportsSection` header, alongside `Importer depuis Sheets`.
- Open a dedicated form view (full route, not modal) reusing the `StepTabs` pattern from `ServerFormView` / `GoogleSheetsImportView`.
- One view, scope-aware: creates the admin singleton when launched from the Admin tab, or a user row when launched from the Utilisateurs tab.
- Field set mirrors what the sheet import collects for a Zoho row: `name`, `url`, `auth_headers`, `created_by` (user rows only), `is_active`, `template_slug` (implicit).

## Non-Goals

- No bulk creation (still owned by the Sheets import).
- No template_slug picker (auto-set from the current template route param).
- No icon picker, tags, or `tool_prefix` — those belong to `mcp_servers`, not `zoho_imports`.
- No edit flow change — existing `ZohoImportEditModal` keeps its edit role.

## User Flow

1. User opens `/admin/templates/zoho`.
2. `ZohoImportsSection` renders. Header now shows two buttons: `+ Ajouter` (new) and `Importer depuis Sheets` (existing).
3. Click `+ Ajouter` → `router.push({ name: 'zoho-import-new', params: { slug }, query: { scope: activeTab } })`.
4. New view loads (`ZohoImportFormView`). Header: `← Retour` button + page title:
   - Admin scope: "Nouveau compte admin Zoho"
   - Users scope: "Nouvel import Zoho"
5. `StepTabs` renders three steps: **Identité → Endpoint → Récapitulatif**.
6. User fills the form, clicks `Créer` on Step 2.
7. Submit branch:
   - Admin scope → `store.upsertAdmin({ name, url, auth_headers })`.
   - Users scope → `store.createUserImport({ name, url, created_by, auth_headers, is_active, template_slug })`.
8. Toast (`success`), then `router.push({ name: 'template-detail', params: { slug }, query: { zoho_tab: scope } })`. `ZohoImportsSection` reads `zoho_tab` from the route query on mount to pre-select the correct tab.

## Frontend Changes

### New file: `src/views/ZohoImportFormView.vue`

- Props: `slug: string` (from route param via `props: true`).
- Local state:
  - `scope: 'admin' | 'users'` — from `route.query.scope`, default `'users'`.
  - `currentStep: number` — 0 / 1 / 2.
  - `form: { name, url, authHeadersJson, created_by, is_active }`.
  - `authHeadersError`, `submitting`.
- Header: `← Retour` (returns to `template-detail`) + dynamic title.
- `StepTabs` (reused from `@/components/shared/StepTabs.vue`), labels `['Identité', 'Endpoint', 'Récapitulatif']`.
- **Step 0 — Identité:**
  - `name` field (required, `BaseInput`).
  - `created_by` field (required, email, hidden when `scope === 'admin'`).
  - Warning banner when `scope === 'admin'` and `store.admin` is non-null: *"Un compte admin existe déjà — la création remplacera la configuration actuelle."*
- **Step 1 — Endpoint:**
  - `url` field (required, type=url, `BaseInput`).
  - `auth_headers` JSON textarea (parse logic identical to `ZohoImportEditModal.vue`).
  - `is_active` checkbox (default `true`, hidden when `scope === 'admin'` — admin row has no toggle semantics).
- **Step 2 — Récapitulatif:**
  - `<dl>` block mirroring `ServerFormView` recap section.
  - Auth-header keys redacted: render only the JSON keys, not the values.
- Buttons: Précédent / Annuler / Suivant / Créer (same shape as `ServerFormView` Section "Create mode: step navigation").
- Submit handler branches on `scope` and calls the matching store action.

### Modified file: `src/components/zoho/ZohoImportsSection.vue`

- Header `<template #actions>` slot now contains two buttons:
  ```html
  <button @click="goToAdd">+ Ajouter</button>
  <button @click="goToImport">Importer depuis Sheets</button>
  ```
- New method `goToAdd()` → `router.push({ name: 'zoho-import-new', params: { slug: props.templateSlug }, query: { scope: activeTab.value } })`.
- `onMounted` extended: when `route.query.zoho_tab` is `'admin'` or `'users'`, set `activeTab.value` accordingly before kicking off the data fetches.

### Modified file: `src/stores/zohoImports.ts`

Add action:
```ts
async createUserImport(payload: ZohoUserCreateRequest): Promise<ZohoImportRow> {
  const row = await zohoImportsApi.create(payload)
  this.users = [row, ...this.users]
  this.usersTotal += 1
  return row
}
```

### Modified file: `src/api/zohoImports.ts`

Add method:
```ts
create(payload: ZohoUserCreateRequest): Promise<ZohoImportRow> {
  return api.post<ZohoImportRow>(BASE, payload)
}
```

### Modified file: `src/types/zoho.ts`

Add interface:
```ts
export interface ZohoUserCreateRequest {
  name: string
  url: string
  created_by: string
  auth_headers?: Record<string, string>
  is_active?: boolean
  template_slug?: string
}
```

### Modified file: `src/router/index.ts`

Add route:
```ts
{
  path: '/admin/templates/:slug/zoho-imports/new',
  name: 'zoho-import-new',
  component: () => import('@/views/ZohoImportFormView.vue'),
  props: true,
  meta: { requiresAuth: true, minRole: 'admin' },
}
```

## Backend Changes

### Modified file: `internal/api/zoho_admin_handlers.go`

In `handleZohoImports`, replace the current `if r.Method != http.MethodGet` rejection with a switch:

```go
switch r.Method {
case http.MethodGet:
    // existing list logic
case http.MethodPost:
    h.handleZohoUserCreate(w, r)
default:
    writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
}
```

New function `handleZohoUserCreate(w, r)`:

1. Decode body into `ZohoUserCreateRequest`. On JSON error → 400.
2. Validate:
   - `name` non-empty → else 400.
   - `url` non-empty, passes `validateUpstreamURL` (same helper used by the admin upsert) → else 400.
   - `created_by` non-empty and matches a basic email shape → else 400.
   - `template_slug` defaults to `"zoho"` when empty.
3. Call `repo.FindUserImportByEmail(created_by)` — if a row exists → 409 with body `{"error": "already exists for this email"}`.
4. Encrypt `auth_headers` with `h.encryptor` (reuse the same encryption path as the admin upsert).
5. Build `db.ZohoImport{ IsAdmin: false, IsActive: payload.IsActive defaulting true, Name, URL, CreatedBy, TemplateSlug, AuthHeaders }`.
6. Call `repo.CreateUserImport(&row)`. On error → 500.
7. Respond 201 with `zohoImportToRowDTO(&row, h)`.

### Modified file: `internal/api/zoho_admin_dto.go`

Add struct:
```go
type ZohoUserCreateRequest struct {
    Name         string            `json:"name"`
    URL          string            `json:"url"`
    CreatedBy    string            `json:"created_by"`
    AuthHeaders  map[string]string `json:"auth_headers,omitempty"`
    IsActive     *bool             `json:"is_active,omitempty"`
    TemplateSlug string            `json:"template_slug,omitempty"`
}
```

### No new files, no DB migration

- `zoho_imports` table already carries every column we need.
- `repository.CreateUserImport` already exists.
- The admin-only prefix guard in `handler.go:572` already covers `POST /api/v1/zoho-imports`.

## Tests

### Backend (`internal/api/zoho_admin_handlers_test.go`)

Five new cases:
1. `POST /api/v1/zoho-imports` with valid body → 201, row appears in subsequent `GET /api/v1/zoho-imports?is_admin=false`.
2. Missing `created_by` → 400.
3. Duplicate `created_by` → 409.
4. Invalid JSON body → 400.
5. Invalid URL (private IP when `ALLOW_INTERNAL_URLS=false`) → 400, reusing the existing URL-validation test fixture.

### Frontend API client (`src/api/zohoImports.spec.ts`)

Add one case: `create()` issues `POST /api/v1/zoho-imports` with the expected body and resolves to a `ZohoImportRow`.

### Frontend store (`src/stores/zohoImports.spec.ts`)

Add one case: `createUserImport()` calls the API, prepends the returned row to `users`, increments `usersTotal`.

### Manual smoke

- Open `/admin/templates/zoho`.
- Click `+ Ajouter` on Admin tab → form titled "Nouveau compte admin Zoho", no `created_by` field, warning banner if admin row already exists. Submit → toast + Admin tab shows updated row.
- Click `+ Ajouter` on Utilisateurs tab → form titled "Nouvel import Zoho", `created_by` field visible, `is_active` checkbox visible. Submit → toast + new row at the top of the users list.
- Test 409 path: re-submit the same `created_by` → backend error surfaced in toast.

## CLAUDE.md Updates

### `apps-microservices/mcp-gateway-service/CLAUDE.md`

In the "Zoho Imports Admin" subsection, add bullet:

> - `POST /api/v1/zoho-imports` — create a per-user import row. Body: `{name, url, created_by, auth_headers?, is_active?, template_slug?}`. Returns 201 + row DTO on success, 400 on validation errors, 409 when `created_by` already has a row. The singleton admin row is still created via `POST /api/v1/zoho-imports/admin`.

### `apps-microservices/mcp-gateway-frontend/CLAUDE.md`

In the file inventory, append `ZohoImportFormView.vue` under `views/`.
In a new "Zoho imports admin onglet" subsection (or appended to an existing Zoho mention), document the route:

> Manual single-row creation is exposed at `/admin/templates/:slug/zoho-imports/new?scope=admin|users`. The view (`ZohoImportFormView.vue`) reuses the `StepTabs` wizard pattern (`Identité → Endpoint → Récapitulatif`) from `ServerFormView`. The `+ Ajouter` button in `ZohoImportsSection` passes the active tab as `scope` and the view branches between `store.upsertAdmin` (admin scope) and `store.createUserImport` (users scope) on submit. Admin-gated through the global `router.beforeEach` guard.

## Acceptance Criteria

- `+ Ajouter` button visible in both Zoho tabs, routes to the new view with `scope` reflecting the active tab.
- Three-step wizard renders identically in look-and-feel to `ServerFormView` (same `StepTabs`, same navigation button shape).
- Form fields: `name`, `url`, `auth_headers` JSON, `created_by` (users only), `is_active` (users only). `template_slug` auto-injected from the route.
- Admin scope hits `POST /api/v1/zoho-imports/admin` (existing); user scope hits the new `POST /api/v1/zoho-imports`.
- 409 surfaced as a toast when `created_by` is already taken.
- On success, the user lands back on the template detail page with the matching Zoho tab pre-selected and the new row visible.
- Both CLAUDE.md files updated.
- Backend unit tests cover the five cases listed above; frontend store + api spec each gain one case.

## Out of Scope / Future Work

- No drag-to-reorder, no per-row filter scope edit from this view.
- No automatic `tools/list` probe after create — operator can hit "Tester" / "Découvrir" on the freshly created row from the existing tab UI.
- No CLI / scripted creation path — this is admin UI only.
