# Zoho Imports List View + Per-Row Admin Actions

**Date:** 2026-05-13
**Scope:** `apps-microservices/mcp-gateway-service/` (backend) + `apps-microservices/mcp-gateway-frontend/` (frontend)
**Status:** Draft
**Builds on:** `2026-05-13-zoho-imports-table-design.md` (the table this view manages)

## Problem

Operators added Zoho rows two ways: per-user via the `/templates` sheet wizard, admin singleton via `POST /api/v1/zoho-imports/admin`. Neither flow surfaces the resulting data anywhere — the only way to inspect or manage rows is direct SQL or `curl`. The Google stdio templates already show their instances under `TemplateDetailView`; Zoho needs the equivalent.

## Goal

Add a list/management view for Zoho imports under `/templates/zoho-crm` (and any other `zoho-*` slug). The page exposes:

- An **Admin** tab: the singleton admin row (or an empty-state CTA when none configured).
- An **Utilisateurs** tab: paginated list of per-user rows.
- Per-row actions: Edit (URL + auth_headers), Toggle active, Delete, Test (HTTP probe).
- An **Importer** button at the top that opens the existing `GoogleSheetsImportView` wizard pre-loaded with `template_slug=zoho-crm`.

The Zoho cards on `/templates` now route to this new view instead of jumping directly to the import wizard.

## Non-goals

- No new admin nav entry. The view lives under `/templates/<slug>` like other template detail pages.
- No bulk operations (bulk delete, bulk toggle, multi-select). Each action is per-row.
- No CSV export or audit log of edits. `updated_at` is the only history surface.
- No Zoho-side identity validation. We do not call Zoho's API to verify the URL or token; the Test action only probes the URL.
- No support for multiple `is_admin=1` rows. The singleton constraint stays.
- No frontend-side decryption of `auth_headers`. The values stay opaque; the wire shape only carries the header **key names**.

## Affected surfaces

| Layer | Touched |
|---|---|
| Backend repo | `ZohoImportRepo` gains `List`, `GetByID`, `Update`, `DeleteByID` |
| Backend handlers | `zoho_admin_handlers.go` gains list / patch / delete / test handlers |
| Backend DTO | `zoho_admin_dto.go` gains list response, row DTO, update request, test response |
| Backend router | three new routes registered + added to `isAdminOnly` |
| Frontend types | `src/types/zoho.ts` (new) mirrors the DTOs |
| Frontend API client | `src/api/zohoImports.ts` (new) |
| Frontend store | `src/stores/zohoImports.ts` (new) |
| Frontend view | `TemplateDetailView.vue` conditionally renders the Zoho branch |
| Frontend catalog | `TemplatesView.vue` drops the http_batch redirect for Zoho slugs |
| Frontend components | new `ZohoAdminCard.vue`, `ZohoUserList.vue`, `ZohoImportEditModal.vue`, `ZohoTestResultBadge.vue` |

## Architecture

### Routing change

The current `templateTarget` in `TemplatesView.vue` redirects `http_batch` cards to `GoogleSheetsImportView`. Refine this to send Zoho-slug templates (`^zoho(-.*)?$`) to `TemplateDetailView` instead. Non-Zoho `http_batch` templates (e.g. `custom-http`) keep the existing direct-to-wizard behaviour.

```ts
function templateTarget(template: Template): RouteLocationRaw {
  if (template.kind === 'http_batch' && !isZohoSlug(template.slug)) {
    return { name: 'google-sheets-import', query: { from: 'templates', template_slug: template.slug } }
  }
  return { name: 'template-detail', params: { slug: template.slug } }
}
```

### `TemplateDetailView` branching

`TemplateDetailView.vue` already has a stdio path. Add a Zoho branch:

```vue
<template v-if="isZohoTemplate">
  <ZohoImportsSection :template-slug="template.slug" />
</template>
<template v-else>
  <!-- existing stdio instances block -->
</template>
```

`ZohoImportsSection` is a thin shell that renders the header + tabs + the Admin / Users children. Keeps `TemplateDetailView` from ballooning.

### List endpoint contract

`GET /api/v1/zoho-imports`

| Query param | Default | Notes |
|---|---|---|
| `is_admin` | unset = both | `true` to fetch only the admin row, `false` for per-user rows |
| `page` | `1` | 1-indexed |
| `limit` | `20` | max 100 |
| `search` | `""` | optional substring match on `name` or `created_by` (case-insensitive) |

Response:

```json
{
  "rows": [
    {
      "id": "uuid",
      "name": "alice's zoho",
      "url": "https://mcp.zoho.eu/abc",
      "is_admin": false,
      "is_active": true,
      "created_by": "alice@hp.fr",
      "auth_header_keys": ["Authorization"],
      "template_slug": "zoho-crm",
      "created_at": "2026-05-13T08:12:01Z",
      "updated_at": "2026-05-13T08:12:01Z"
    }
  ],
  "total": 17,
  "page": 1,
  "limit": 20
}
```

`auth_header_keys` is the redacted view: the gateway decrypts the blob server-side, lists the JSON map keys, and discards the values before serializing. The frontend never sees the secrets.

### PATCH endpoint contract

`PATCH /api/v1/zoho-imports/{id}`

Body — every field optional:

```json
{
  "name": "alice (updated)",
  "url": "https://mcp.zoho.eu/abc-new",
  "auth_headers": { "Authorization": "Bearer ..." },
  "is_active": false
}
```

Behavior:

- Empty body → 400.
- `name`, `url` updated when present.
- `auth_headers`: when present and non-empty, replaces the encrypted blob (encrypted with `ENCRYPTION_KEY` before write). When present and empty `{}`, blob is set to `NULL`.
- `is_active` toggles the flag.
- `created_by` and `is_admin` are never editable through this endpoint (admin row uses the dedicated `/admin` endpoint).
- Response: the updated row DTO (same shape as a list item).

### DELETE endpoint contract

`DELETE /api/v1/zoho-imports/{id}`

- 204 No Content on success.
- 404 when row missing.
- 400 when the target is the singleton admin row, with body `{"error":"use /api/v1/zoho-imports/admin to delete the admin row"}`.

### Test endpoint contract

`POST /api/v1/zoho-imports/{id}/test`

- No body.
- Server-side: load the row, decrypt headers, issue `POST <row.url>` with body `{"jsonrpc":"2.0","method":"tools/list","id":1}` and a 10 s timeout. Use the decrypted headers verbatim.
- Response:

```json
{
  "ok": true,
  "status_code": 200,
  "latency_ms": 312
}
```

Failure shapes:

```json
{ "ok": false, "status_code": 401, "latency_ms": 89 }
{ "ok": false, "error": "timeout", "latency_ms": 10000 }
{ "ok": false, "error": "dial tcp: lookup mcp.zoho.eu: no such host" }
```

The endpoint never echoes back the decrypted headers or the upstream response body.

### Layout sketch

```
TemplateDetailView (slug='zoho-crm')
├─ <PageBreadcrumb page-title="Zoho CRM" />
├─ Header row
│   ├─ Icon + name + description
│   └─ [ Importer depuis Sheets ] button → /servers/import-google?from=templates&template_slug=zoho-crm
├─ Tabs:  Admin (n)  |  Utilisateurs (n)
│
├─ Admin tab body
│   ├─ Card: name | url | header keys | toggle | actions row
│   │   Actions: [ Modifier ]  [ Tester ]  [ Désactiver / Activer ]  [ Supprimer ]
│   └─ Empty state: "Aucun compte admin configuré"
│       └─ [ Configurer le compte admin ] → opens AdminFormModal
│
└─ Utilisateurs tab body
    ├─ Search input + page selector (when total > limit)
    ├─ Table:
    │   ┌────────────────────────────────────────────────────────────────┐
    │   │ created_by | name | url | active | keys | created_at | actions │
    │   └────────────────────────────────────────────────────────────────┘
    │   Per-row actions: [ Tester ]  [ Toggle ]  [ Modifier ]  [ Supprimer ]
    └─ Empty state: "Aucun import"
        └─ [ Importer depuis Sheets ]
```

### Components

| File | Responsibility |
|---|---|
| `src/components/zoho/ZohoImportsSection.vue` | Tab orchestrator. Loads admin + users on mount via store. Renders `ZohoAdminCard` + `ZohoUserList`. |
| `src/components/zoho/ZohoAdminCard.vue` | Admin singleton view. Renders the row or the empty CTA. Wires Edit / Test / Toggle / Delete buttons against the store. |
| `src/components/zoho/ZohoUserList.vue` | Paginated table. Search input. Renders per-row actions. |
| `src/components/zoho/ZohoImportEditModal.vue` | Single modal reused for both admin and user rows. Pre-fills `name` + `url`. `auth_headers` field empty (user re-enters when they want to rotate). When opened for a brand-new admin row, the `created_by` field is hidden. |
| `src/components/zoho/ZohoTestResultBadge.vue` | Renders the test outcome inline next to the row's actions (green check + latency, red cross + error). Fades out after 5 s. |

### Frontend store

`src/stores/zohoImports.ts` (Pinia):

```ts
state: {
  admin: ZohoImportRow | null,
  users: ZohoImportRow[],
  usersTotal: number,
  usersPage: number,
  usersLimit: number,
  usersSearch: string,
  isLoading: boolean,
  error: string | null,
}
actions: {
  fetchAdmin(),
  fetchUsers({ page, search }),
  upsertAdmin(payload: ZohoAdminCreateRequest),
  deleteAdmin(),
  updateRow(id, patch),
  deleteRow(id),
  testRow(id): Promise<ZohoImportTestResponse>,
  toggleActive(id),  // thin wrapper around updateRow
}
```

The store re-fetches the affected list after every mutation so optimistic local updates don't drift from server state.

## Validation rules

| Condition | Behaviour |
|---|---|
| List `?is_admin=true` returns 0 rows | `{rows:[], total:0}` |
| List `?limit=999` | Clamped to 100 |
| List `?page=0` or negative | Clamped to 1 |
| PATCH with no fields | 400 |
| PATCH `auth_headers={}` | Clears encrypted blob (set to NULL) |
| PATCH on admin row via this endpoint | Allowed for `name/url/auth_headers/is_active`; `is_admin` and `created_by` ignored (silently scrubbed) |
| DELETE on admin row | 400 with redirect message |
| Test row not found | 404 |
| Test upstream 4xx/5xx | `{ok:false, status_code, latency_ms}` — not an HTTP error from gateway |
| Test upstream timeout | `{ok:false, error:"timeout", latency_ms:10000}` |
| Test network error | `{ok:false, error:"<dial msg>"}` |
| Non-admin caller on any endpoint | 403 (existing `isAdminOnly` matches) |

## Tests

Backend (`internal/api/zoho_admin_handlers_test.go` and `internal/repository/zoho_import_repo_test.go`):

1. `Repo.List` returns paginated rows in `created_at DESC` order; filter by `is_admin` works.
2. `Repo.Update` mutates only the specified fields; auth_headers blob round-trips through encrypt/decrypt.
3. `Repo.DeleteByID` removes a per-user row; idempotent.
4. `GET /api/v1/zoho-imports` redacts `auth_headers` values to key names.
5. `GET ?is_admin=true` returns only the singleton.
6. `PATCH` with all fields updates and returns new row.
7. `PATCH` with `auth_headers={}` clears the blob.
8. `DELETE` per-user row → 204; subsequent GET → 404.
9. `DELETE` admin row → 400 with redirect message.
10. `POST /test` with `httptest.NewServer` upstream → `ok=true`, latency present.
11. `POST /test` against a timeout server → `ok=false`, `error="timeout"`.
12. Non-admin caller on every endpoint → 403.

Frontend:

- Store: `fetchUsers` populates state and clamps pagination params.
- Store: `deleteRow` calls API then refetches.
- Component: `ZohoImportsSection` mounts only when slug is Zoho; tabs render counts from store state.
- Component: `ZohoImportEditModal` submits only fields that changed.

## Rollout

1. Deploy gateway + frontend together (no schema migration needed; table already exists from prior spec).
2. Smoke: open `/templates`, click Zoho card, confirm the new detail view loads with the existing imported rows.
3. Try Edit / Test / Toggle / Delete on a non-prod row to validate.
4. Document the new endpoints in the gateway `CLAUDE.md` API section.

## Impact

| Component | LOC estimate |
|---|---|
| Backend repo additions | ~120 |
| Backend handlers + DTOs | ~250 |
| Backend tests | ~250 |
| Frontend types + API client + store | ~200 |
| Frontend components | ~500 |
| Frontend view branching | ~50 |
| CLAUDE.md updates | ~30 |
| **Total** | **~1400** |

## Risks

- **Test endpoint as side-channel.** An admin can probe arbitrary URLs *that are stored in `zoho_imports`*. Since rows are written by the same admin role, no privilege escalation. Mitigation: log every Test call with the row ID + caller email; do not log the URL itself.
- **PATCH `auth_headers` invalidation.** Replacing auth_headers does not invalidate the service's 60 s cache. A bad rotation lingers up to a minute. Mitigation: document the latency; future v2 can add a cache-bust webhook from gateway to service.
- **Test endpoint blocks the handler for ≤ 10 s.** With a small admin user base this is fine. A flood would exhaust the gateway's handler pool. Mitigation (deferred): rate-limit per admin email (1 test per row per 5 s).
- **Empty-body PATCH semantics.** Distinguish `auth_headers: null` (do not touch) vs `auth_headers: {}` (clear). Documented in Validation rules.
- **DELETE on admin via wrong endpoint** is a 400 (not 405) to redirect operators clearly. Documented in spec; tested.

## Open questions (resolved)

- Edit modal pre-fill: name + url shown; auth_headers field left empty. Operator must re-enter the full header map to rotate (we never decrypt to the wire). Acknowledged: this means rotation requires the operator to have the original token handy. Acceptable.
- Test method: chose `POST tools/list` over `HEAD /` because Zoho MCP backends typically require POST with the JSON-RPC body to surface a meaningful response. Acknowledged as a Zoho-specific probe.
- Pagination cap: 100 per page is overkill for likely traffic (10s of users) but matches the existing `/api/v1/bdd/used/tables` cap. Symmetric.
