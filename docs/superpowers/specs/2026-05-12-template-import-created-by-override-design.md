# Template Import — `created_by` Override from Sheet Column

**Date:** 2026-05-12
**Scope:** `apps-microservices/mcp-gateway-service/`, `apps-microservices/mcp-gateway-frontend/`
**Status:** Draft

## Problem

Both Google-Sheets import flows accessible from the `/templates` page stamp every imported row's `created_by` with the connected user's email (the importer). There is no way to record a different owner per row — e.g. when an admin imports instances on behalf of other users.

## Goal

On both import flows reachable from `/templates`, allow the operator to optionally pick a sheet column whose value will populate `created_by`. Defaults to the connected user when no column is mapped or the cell is empty.

## Non-goals

- No schema migration. The two target columns already exist:
  - `mcp_servers.created_by` (varchar(255), default `''`, indexed)
  - `template_instances.created_by` (varchar(255), default `''`)
- No retroactive update of pre-existing rows.
- No users-table existence check on the cell value (free string — same contract as the existing `userEmail` plumbing).
- No new permissions, no Settings view changes, no documentation-page changes.
- No "fixed user" text input — only column mapping plus fallback.

## Affected flows

The `/templates` catalog routes to two distinct import flows depending on the template's `kind`:

| Template kind | Frontend view | Backend handler | Created rows |
|---|---|---|---|
| `stdio` (e.g. `ga`, `gsc`) | `TemplateInstanceSheetImportView.vue` | `handleImportInstancesFromSheet` | `template_instances` + linked `mcp_servers` |
| `http_batch` (e.g. custom-http) | `GoogleSheetsImportView.vue` | `handleSheetImport` → `importSheetRow` | `mcp_servers` only |

Both flows already pass a `createdBy` value into the create path. The change is the **source** of that value: row-resolved cell with fallback, instead of constant connected-user email.

## Design

### Resolution algorithm (identical in both handlers)

```
column := req.CreatedByColumn        // or mapping.CreatedBy for http_batch
fallback := auth.UserEmailFromContext(r.Context())

per row:
  if column == "":
    createdBy = fallback
  else:
    cell = trim(row[colIndex[column]])
    createdBy = cell if cell != "" else fallback
```

- Cell stored as-is (free string, capped by `varchar(255)` at the DB layer).
- stdio handler: if `created_by_column` is non-empty but missing from sheet headers, fail fast with `created_by column "X" not found in sheet headers` — mirrors the existing pre-flight pattern used for `name_column`, `credentials_column`, and `extra_env_columns`.
- http_batch handler: missing header is silently treated as "no override" (per-row `getVal` returns `""` → fallback). Mirrors the existing http_batch pattern for every other optional `ColumnMapping` field — adding pre-flight only for `created_by` would be asymmetric.

### Backend changes

`internal/api/google_dto.go`

```go
type ColumnMapping struct {
    Name string `json:"name"`
    URL  string `json:"url"`
    // ... existing fields ...
    CreatedBy string `json:"created_by,omitempty"` // optional column header
}

type InstanceSheetImportRequest struct {
    // ... existing fields ...
    CreatedByColumn string `json:"created_by_column,omitempty"`
}
```

`internal/api/google_handlers.go`

- `importSheetRow`: replace `CreatedBy: userEmail` with resolved-with-fallback value computed from `getVal(mapping.CreatedBy)`. No pre-flight check (matches the existing per-row laziness for every other optional mapping in this handler).
- `handleImportInstancesFromSheet`: pre-flight check that `req.CreatedByColumn`, when non-empty, exists in `colIndex`. Inside the per-row loop, resolve `createdBy` from the column with fallback to the existing outer `createdBy` (connected user). Reuse the already-declared `createdBy` name by shadowing inside the loop.
- No signature change to `createInstanceFromSpec` — last argument is already `createdBy string`.

### Frontend changes

`src/types/google.ts`

```ts
export interface ColumnMapping {
  name: string
  url: string
  // ... existing fields ...
  created_by?: string
}

export interface InstanceSheetImportRequest {
  // ... existing fields ...
  created_by_column?: string
}
```

`src/api/google.ts` — pass-through (typed).

`src/views/TemplateInstanceSheetImportView.vue`

- Add `const createdByColumn = ref('')`.
- In the Mapping step, after the Credentials column `<select>`, insert a new `<select>` labelled `Colonne créateur (optionnel)`. Empty option = "Utilisateur connecté (défaut)". Helper text: `Par défaut, l'utilisateur connecté est utilisé.`.
- Extend `autoDetectMapping` to look for aliases `createdby,created_by,owner,email,createur,createur`. Apply only when `createdByColumn` is empty (preserve user choice on re-entry).
- In `handleImport`, send `created_by_column: createdByColumn.value || undefined`.

`src/components/google/ColumnMappingTable.vue` + `src/views/GoogleSheetsImportView.vue`

- Add a `created_by` entry to the `ColumnMappingTable` fields list (label `Créateur (optionnel)`, helper `Par défaut, l'utilisateur connecté est utilisé.`).
- Extend the view's `fieldMap` with `created_by: ['createdby', 'created_by', 'owner', 'email', 'createur']`.
- `handleImport` already spreads `columnMapping.value` into the request payload — adding the key on the type is enough; no additional plumbing needed beyond the type definition.

### UI placement (sketch)

stdio mapping step (after credentials):

```
[Nom *]              [select column]
[Credentials JSON *] [select column]
[Créateur (optionnel)] [select column]   ← new, "Utilisateur connecté (défaut)"
[Required extra env fields…]
```

http_batch mapping table: `created_by` appears as one more optional row in the table, identical chrome to the other optional columns.

## Validation rules

| Condition | Behavior |
|---|---|
| `created_by` not mapped | Connected user (existing default). |
| `created_by` mapped, cell non-empty | Cell value stored as-is, trimmed. |
| `created_by` mapped, cell empty | Connected user (per-row fallback). |
| `created_by` header missing — stdio | 400 up-front, no rows processed. |
| `created_by` header missing — http_batch | Treated as empty per row → fallback to connected user. |
| Cell longer than 255 chars | Surface as a row error from GORM (no client-side cap). |

## Tests

Backend (extend `google_handlers_test.go`):

1. `handleSheetImport`: mapping with `created_by` set, row cell non-empty → `mcp_servers.created_by` equals cell.
2. `handleSheetImport`: mapping with `created_by` set, row cell empty → fallback to JWT user email.
3. `handleSheetImport`: mapping without `created_by` → fallback to JWT user email (regression).
4. `handleSheetImport`: mapping with `created_by="Doesnotexist"` (header missing) → all rows fall back to connected user (no 400).
5. `handleImportInstancesFromSheet`: same first three cases against `template_instances.created_by` and linked `mcp_servers.created_by`.
6. `handleImportInstancesFromSheet`: `created_by_column="Doesnotexist"` → 400 with explicit message.

Frontend (spec files):

- Assert request payload shape: `created_by_column` present only when the picker is set.
- Assert auto-detect picks `createdby`/`owner`/`email` headers on a synthetic sheet.

## Rollout

- No DB migration.
- Backwards-compatible: request without `created_by`/`created_by_column` behaves exactly as today.
- Single PR, single commit per layer (backend, then frontend) per project convention.

## Impact

| Service / module | Touched |
|---|---|
| `internal/api/google_dto.go` | 2 fields added |
| `internal/api/google_handlers.go` | resolution logic in 2 handlers |
| `internal/api/google_handlers_test.go` | 8 new cases |
| `src/types/google.ts` | 2 fields added |
| `src/views/TemplateInstanceSheetImportView.vue` | new select + auto-detect + payload |
| `src/views/GoogleSheetsImportView.vue` | fieldMap entry |
| `src/components/google/ColumnMappingTable.vue` | one row entry |

No shared library, proto, or infrastructure change.

## Risks

- Operator pastes a non-email free string into `created_by` (e.g. "Acme corp"). Acceptable — the existing column accepts the same shape from the JWT pipeline and is already free-form in `varchar(255)`.
- Sheet header collision with the literal `created_by` causing accidental mapping. Mitigation: empty default for `createdByColumn`; auto-detect only suggests, never forces, and is overridable by the operator.
