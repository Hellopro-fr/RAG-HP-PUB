# Template Import `created_by` Override — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let operators map a Google Sheet column to `created_by` on both `/templates` import flows (stdio + http_batch), with row-level fallback to the connected user.

**Architecture:** Add one optional column-header field per request DTO. Extract a single pure resolver helper used by both handlers. Frontend adds one `<select>` to the stdio Mapping step and one row to the http_batch `ColumnMappingTable`. No schema changes — both `mcp_servers.created_by` and `template_instances.created_by` columns already exist.

**Tech Stack:** Go 1.24 / net/http / GORM (backend), Vue 3 / TypeScript / Vite / Vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-05-12-template-import-created-by-override-design.md`.

---

## File Structure

### Files to modify

| File | Responsibility | Change shape |
|---|---|---|
| `apps-microservices/mcp-gateway-service/internal/api/google_dto.go` | Request/response DTOs for Google Sheet import | Add `ColumnMapping.CreatedBy` + `InstanceSheetImportRequest.CreatedByColumn` |
| `apps-microservices/mcp-gateway-service/internal/api/google_handlers.go` | HTTP handlers for both import flows | Add `resolveCreatedBy` helper; replace constant `createdBy`/`userEmail` with per-row resolved value in both handlers; pre-flight column existence check (stdio only) |
| `apps-microservices/mcp-gateway-service/internal/api/google_handlers_test.go` | Unit tests | Add table-driven test for the resolver helper |
| `apps-microservices/mcp-gateway-frontend/src/types/google.ts` | TS types matching Go DTOs | Add `created_by?` on `ColumnMapping` + `created_by_column?` on `InstanceSheetImportRequest` |
| `apps-microservices/mcp-gateway-frontend/src/views/TemplateInstanceSheetImportView.vue` | stdio import wizard | Add `createdByColumn` ref, `<select>` in Mapping step, auto-detect, payload field |
| `apps-microservices/mcp-gateway-frontend/src/views/GoogleSheetsImportView.vue` | http_batch import wizard | Add `created_by` entry to `fieldMap` (auto-detect aliases) |
| `apps-microservices/mcp-gateway-frontend/src/components/google/ColumnMappingTable.vue` | Reusable mapping table for http_batch | Add `created_by` entry to the `fields` array |

### Files unchanged

- DB models (`internal/db/models.go`) — columns already exist.
- API client (`src/api/google.ts`) — passes payload through; type change is sufficient.
- Router, stores, other views.

---

## Conventions

- **Go**: `go build ./...` from `apps-microservices/mcp-gateway-service/`. Tests with `go test ./internal/api/...`. Project uses the persistent gateway-go container at `/work` per memory; if running locally and that container is unavailable, fall back to `go test` directly.
- **Frontend**: `npm run typecheck` and `npm run test` from `apps-microservices/mcp-gateway-frontend/`. Build with `npm run build` to catch type errors.
- **Commits**: Conventional Commits, bilingual (EN + FR per `.claude/rules/commit-messages.md`), subject < 72 chars.

---

## Task 1: Add a pure `resolveCreatedBy` helper + table-driven test (TDD)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/google_handlers.go` (add helper at the bottom of the file, after `fetchGoogleEmail`)
- Test: `apps-microservices/mcp-gateway-service/internal/api/google_handlers_test.go`

Rationale: the full Google sheet import is hard to unit-test (live Google client). Isolate the new policy into one pure function and cover it exhaustively. The two handlers then become trivial one-liners that call this function — no behavior diverges between them.

- [ ] **Step 1: Write the failing test**

Append to `apps-microservices/mcp-gateway-service/internal/api/google_handlers_test.go`:

```go
// TestResolveCreatedBy verifies the row-level created_by resolution rule
// shared between handleSheetImport and handleImportInstancesFromSheet.
//
// Contract:
//   - column header empty               -> fallback (connected user)
//   - column header set, header missing -> fallback (handler responsibility
//                                          to pre-flight when desired; the
//                                          resolver itself does not error)
//   - column header set, cell empty     -> fallback
//   - column header set, cell non-empty -> trimmed cell
func TestResolveCreatedBy(t *testing.T) {
	headers := []string{"Name", "Credentials", "Owner"}
	colIndex := map[string]int{}
	for i, h := range headers {
		colIndex[h] = i
	}

	cases := []struct {
		name     string
		column   string
		row      []string
		fallback string
		want     string
	}{
		{
			name:     "empty column -> fallback",
			column:   "",
			row:      []string{"srv-1", "{}", "ignored@example.com"},
			fallback: "me@hellopro.fr",
			want:     "me@hellopro.fr",
		},
		{
			name:     "header missing -> fallback",
			column:   "Doesnotexist",
			row:      []string{"srv-1", "{}", "ignored@example.com"},
			fallback: "me@hellopro.fr",
			want:     "me@hellopro.fr",
		},
		{
			name:     "cell empty -> fallback",
			column:   "Owner",
			row:      []string{"srv-1", "{}", "   "},
			fallback: "me@hellopro.fr",
			want:     "me@hellopro.fr",
		},
		{
			name:     "cell non-empty -> trimmed cell",
			column:   "Owner",
			row:      []string{"srv-1", "{}", "  alice@hellopro.fr  "},
			fallback: "me@hellopro.fr",
			want:     "alice@hellopro.fr",
		},
		{
			name:     "row shorter than colIndex -> fallback",
			column:   "Owner",
			row:      []string{"srv-1", "{}"}, // missing Owner cell
			fallback: "me@hellopro.fr",
			want:     "me@hellopro.fr",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := resolveCreatedBy(tc.column, tc.row, colIndex, tc.fallback)
			if got != tc.want {
				t.Fatalf("resolveCreatedBy(%q) = %q, want %q", tc.column, got, tc.want)
			}
		})
	}
}
```

- [ ] **Step 2: Run test, verify it fails to compile**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/api/ -run TestResolveCreatedBy -v
```

Expected: compilation error — `undefined: resolveCreatedBy`.

- [ ] **Step 3: Implement the helper**

Append to `apps-microservices/mcp-gateway-service/internal/api/google_handlers.go` (after `fetchGoogleEmail`):

```go
// resolveCreatedBy returns the created_by value to stamp on a row.
// Empty column header, missing header, or empty/whitespace cell all fall back
// to fallback (the connected user's email). Non-empty cells are trimmed.
//
// Kept pure and decoupled from *http.Request so both import handlers share
// one definition of the rule (see google_handlers_test.go for the contract).
func resolveCreatedBy(column string, row []string, colIndex map[string]int, fallback string) string {
	if column == "" {
		return fallback
	}
	idx, ok := colIndex[column]
	if !ok || idx >= len(row) {
		return fallback
	}
	v := strings.TrimSpace(row[idx])
	if v == "" {
		return fallback
	}
	return v
}
```

- [ ] **Step 4: Run the test, verify it passes**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/api/ -run TestResolveCreatedBy -v
```

Expected: 5 sub-tests PASS.

- [ ] **Step 5: Run the full API test suite to catch regressions**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/api/...
```

Expected: all PASS (including the existing `TestHandleImportInstancesFromSheet_NilDeps_Returns503`).

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/google_handlers.go \
        apps-microservices/mcp-gateway-service/internal/api/google_handlers_test.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): add resolveCreatedBy helper for sheet imports

Pure row-level resolver shared between the stdio (instance) and
http_batch (server) Google Sheets import handlers. Empty column,
missing header, or empty cell all fall back to the connected user.

EN: Ajoute un résolveur pur partagé par les deux flux d'import
Google Sheets. Repli sur l'utilisateur connecté si la colonne est
absente ou la cellule vide.
EOF
)"
```

---

## Task 2: Add `CreatedBy` to the http_batch `ColumnMapping` DTO

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/google_dto.go`

- [ ] **Step 1: Add the DTO field**

In `apps-microservices/mcp-gateway-service/internal/api/google_dto.go`, inside the `ColumnMapping` struct, add the `CreatedBy` field just before the closing brace:

```go
// ColumnMapping maps spreadsheet column headers to MCP server fields.
type ColumnMapping struct {
	Name                string `json:"name"`                           // Required
	URL                 string `json:"url"`                            // Required
	AuthHeaders         string `json:"auth_headers,omitempty"`         // JSON string
	Tags                string `json:"tags,omitempty"`                 // Comma-separated
	TransportPreference string `json:"transport_preference,omitempty"`
	ConnectTimeoutMs    string `json:"connect_timeout_ms,omitempty"`
	ToolPrefix          string `json:"tool_prefix,omitempty"`
	Icon                string `json:"icon,omitempty"`
	MCPTransport        string `json:"mcp_transport,omitempty"`
	MCPCommand          string `json:"mcp_command,omitempty"`
	MCPArgs             string `json:"mcp_args,omitempty"`    // JSON array string
	MCPEnv              string `json:"mcp_env,omitempty"`     // JSON object string
	DocSlug             string `json:"doc_slug,omitempty"`
	DocDescription      string `json:"doc_description,omitempty"`
	CreatedBy           string `json:"created_by,omitempty"` // Optional — sheet column whose cell value sets mcp_servers.created_by; empty/missing falls back to connected user
}
```

- [ ] **Step 2: Verify the build**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go build ./...
```

Expected: no output (success).

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/google_dto.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): add ColumnMapping.CreatedBy to sheet import DTO

Optional column-header field on /api/v1/google/sheets/import. When set,
the cell value at that column populates mcp_servers.created_by; empty
or unmapped falls back to the connected user.

EN: Champ optionnel de mappage de colonne pour created_by sur l'import
Google Sheets côté serveurs.
EOF
)"
```

---

## Task 3: Wire the resolver into `importSheetRow` (http_batch flow)

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/google_handlers.go` (function `importSheetRow`, around lines 656–710)

- [ ] **Step 1: Update `importSheetRow` to resolve `CreatedBy` per row**

In `apps-microservices/mcp-gateway-service/internal/api/google_handlers.go`, locate the `srv := db.MCPServer{...}` literal inside `importSheetRow`. Replace the `CreatedBy: userEmail,` line with a resolved value computed just above the struct literal.

Find:

```go
	id := uuid.New().String()
	srv := db.MCPServer{
		ID:                  id,
		Name:                name,
		URL:                 strings.TrimRight(serverURL, "/"),
		TransportPreference: "auto",
		ConnectTimeoutMs:    10000,
		IsActive:            true,
		HealthStatus:        "unknown",
		MCPTransport:        "http",
		DocSlug:             generateDocSlug(name, id),
		CreatedBy:           userEmail,
```

Replace with:

```go
	id := uuid.New().String()
	createdBy := resolveCreatedBy(mapping.CreatedBy, row, colIndex, userEmail)
	srv := db.MCPServer{
		ID:                  id,
		Name:                name,
		URL:                 strings.TrimRight(serverURL, "/"),
		TransportPreference: "auto",
		ConnectTimeoutMs:    10000,
		IsActive:            true,
		HealthStatus:        "unknown",
		MCPTransport:        "http",
		DocSlug:             generateDocSlug(name, id),
		CreatedBy:           createdBy,
```

- [ ] **Step 2: Build to verify**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go build ./...
```

Expected: success.

- [ ] **Step 3: Run all API tests**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/api/...
```

Expected: PASS (resolver test still green, existing tests still green).

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/google_handlers.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): per-row created_by in sheet server import

importSheetRow now resolves mcp_servers.created_by from the optional
mapping.CreatedBy column instead of always using the importer's email.
Empty mapping or empty cell falls back to the connected user.

EN: Résolution par ligne du champ created_by lors de l'import des
serveurs MCP depuis un Google Sheet.
EOF
)"
```

---

## Task 4: Add `CreatedByColumn` to the stdio import DTO + pre-flight + per-row resolve

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/google_dto.go` (add field on `InstanceSheetImportRequest`)
- Modify: `apps-microservices/mcp-gateway-service/internal/api/google_handlers.go` (function `handleImportInstancesFromSheet`, around lines 362–568)

- [ ] **Step 1: Add the DTO field**

In `apps-microservices/mcp-gateway-service/internal/api/google_dto.go`, inside the `InstanceSheetImportRequest` struct, add `CreatedByColumn` just before the closing brace:

```go
// InstanceSheetImportRequest is the request body for
// POST /api/v1/google/sheets/import-instances. ...
type InstanceSheetImportRequest struct {
	SpreadsheetID string `json:"spreadsheet_id"`
	SheetName     string `json:"sheet_name"`
	TemplateSlug  string `json:"template_slug"`
	// Column mapping — all required, all non-empty for the import to proceed.
	NameColumn        string `json:"name_column"`
	CredentialsColumn string `json:"credentials_column"`
	// ExtraEnvColumns maps a template's required_extra_env key to the sheet
	// column header that holds its value. One entry per schema field; the
	// handler validates that every required key has a non-empty mapping.
	ExtraEnvColumns map[string]string `json:"extra_env_columns,omitempty"`
	// Optional overrides applied to EVERY row (mirror server-import semantics).
	AutoDiscover    bool   `json:"auto_discover,omitempty"`
	FixedTags       string `json:"fixed_tags,omitempty"` // comma-separated
	FixedToolPrefix string `json:"fixed_tool_prefix,omitempty"`
	FixedIcon       string `json:"fixed_icon,omitempty"`
	NamePrefix      string `json:"name_prefix,omitempty"`
	// Optional — when set, each row's cell at this column populates
	// template_instances.created_by (and the linked mcp_servers row).
	// Empty header or empty cell falls back to the connected user.
	CreatedByColumn string `json:"created_by_column,omitempty"`
}
```

- [ ] **Step 2: Add pre-flight validation + per-row resolve in the handler**

In `apps-microservices/mcp-gateway-service/internal/api/google_handlers.go`, locate the pre-flight block in `handleImportInstancesFromSheet` (around line 444). After the existing block that validates `req.CredentialsColumn`, append a new validation for `CreatedByColumn`.

Find:

```go
	if _, ok := colIndex[req.CredentialsColumn]; !ok {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: fmt.Sprintf("credentials_column %q not found in sheet headers", req.CredentialsColumn)})
		return
	}
	for key, col := range req.ExtraEnvColumns {
```

Replace with:

```go
	if _, ok := colIndex[req.CredentialsColumn]; !ok {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: fmt.Sprintf("credentials_column %q not found in sheet headers", req.CredentialsColumn)})
		return
	}
	if req.CreatedByColumn != "" {
		if _, ok := colIndex[req.CreatedByColumn]; !ok {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: fmt.Sprintf("created_by_column %q not found in sheet headers", req.CreatedByColumn)})
			return
		}
	}
	for key, col := range req.ExtraEnvColumns {
```

Then locate the outer `createdBy` declaration (around line 474):

Find:

```go
	createdBy := auth.UserEmailFromContext(r.Context())
	resp := SheetImportResponse{
```

Rename the outer constant to `fallbackCreatedBy` so we don't accidentally pass the importer's email when a row overrides it:

```go
	fallbackCreatedBy := auth.UserEmailFromContext(r.Context())
	resp := SheetImportResponse{
```

Then inside the per-row loop, just before the `h.createInstanceFromSpec(...)` call (around line 541), add the resolve:

Find:

```go
		_, _, cerr := h.createInstanceFromSpec(
			r.Context(),
			tpl,
			instName,
			credBytes,
			extraEnv,
			fixedTags,
			req.FixedIcon,
			req.FixedToolPrefix,
			req.AutoDiscover,
			createdBy,
		)
```

Replace with:

```go
		rowCreatedBy := resolveCreatedBy(req.CreatedByColumn, row, colIndex, fallbackCreatedBy)
		_, _, cerr := h.createInstanceFromSpec(
			r.Context(),
			tpl,
			instName,
			credBytes,
			extraEnv,
			fixedTags,
			req.FixedIcon,
			req.FixedToolPrefix,
			req.AutoDiscover,
			rowCreatedBy,
		)
```

- [ ] **Step 3: Build**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go build ./...
```

Expected: success.

- [ ] **Step 4: Run all API tests**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go test ./internal/api/...
```

Expected: PASS. The existing `TestHandleImportInstancesFromSheet_NilDeps_Returns503` still 503s before reaching the new code path.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/google_dto.go \
        apps-microservices/mcp-gateway-service/internal/api/google_handlers.go
git commit -m "$(cat <<'EOF'
feat(mcp-gateway): per-row created_by in sheet instance import

handleImportInstancesFromSheet now accepts an optional
created_by_column. When set, the column must exist in the sheet
headers (400 otherwise) and each row's cell populates the linked
template_instances.created_by + mcp_servers.created_by. Empty cell
falls back to the connected user.

EN: Résolution par ligne du champ created_by lors de l'import des
instances de templates depuis un Google Sheet.
EOF
)"
```

---

## Task 5: Add `created_by` to the frontend TypeScript types

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/types/google.ts`

- [ ] **Step 1: Update `ColumnMapping`**

In `apps-microservices/mcp-gateway-frontend/src/types/google.ts`, add `created_by` after `doc_description`:

```ts
export interface ColumnMapping {
  [key: string]: string | undefined
  name: string
  url: string
  auth_headers?: string
  tags?: string
  transport_preference?: string
  connect_timeout_ms?: string
  tool_prefix?: string
  icon?: string
  mcp_transport?: string
  mcp_command?: string
  mcp_args?: string
  mcp_env?: string
  doc_slug?: string
  doc_description?: string
  // Optional — when set, each row's cell at this column header becomes the
  // created_by stamped on the imported mcp_servers row. Empty falls back to
  // the connected user.
  created_by?: string
}
```

- [ ] **Step 2: Update `InstanceSheetImportRequest`**

Add `created_by_column` to `InstanceSheetImportRequest`:

```ts
export interface InstanceSheetImportRequest {
  spreadsheet_id: string
  sheet_name: string
  template_slug: string
  name_column: string
  credentials_column: string
  // Template required_extra_env key -> sheet column header.
  extra_env_columns?: Record<string, string>
  auto_discover?: boolean
  fixed_tags?: string
  fixed_tool_prefix?: string
  fixed_icon?: string
  name_prefix?: string
  // Optional — sheet column whose cell value sets the template instance's
  // created_by. Empty/unmapped falls back to the connected user.
  created_by_column?: string
}
```

- [ ] **Step 3: Run typecheck + build**

Run:
```bash
cd apps-microservices/mcp-gateway-frontend && npm run typecheck && npm run build
```

Expected: both succeed (no type errors anywhere — these are additive optional fields).

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/types/google.ts
git commit -m "$(cat <<'EOF'
feat(mcp-gateway-frontend): add created_by mapping fields to TS types

ColumnMapping.created_by and InstanceSheetImportRequest.created_by_column
mirror the new backend DTO fields, enabling per-row created_by override
when importing servers or template instances from a Google Sheet.

EN: Ajoute les champs de type TypeScript pour le mappage created_by
des deux flux d'import Google Sheets.
EOF
)"
```

---

## Task 6: Wire the `created_by` row into `ColumnMappingTable` (http_batch flow)

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/components/google/ColumnMappingTable.vue` (the `fields` array around lines 114–129)

- [ ] **Step 1: Add the field entry**

In `apps-microservices/mcp-gateway-frontend/src/components/google/ColumnMappingTable.vue`, append a `created_by` entry to the `fields` array:

```ts
const fields: FieldDef[] = [
  { key: 'name', label: 'Nom du serveur', required: true },
  { key: 'url', label: 'URL du serveur', required: true },
  { key: 'auth_headers', label: 'En-têtes auth (JSON)', required: false },
  { key: 'tags', label: 'Tags', required: false, dualMode: true, manualPlaceholder: 'tag1, tag2, tag3' },
  { key: 'transport_preference', label: 'Préférence transport', required: false },
  { key: 'connect_timeout_ms', label: 'Timeout (ms)', required: false },
  { key: 'tool_prefix', label: 'Préfixe outil', required: false, dualMode: true, manualPlaceholder: 'myprefix' },
  { key: 'icon', label: 'Icône (URL)', required: false },
  { key: 'mcp_transport', label: 'Transport MCP', required: false },
  { key: 'mcp_command', label: 'Commande MCP', required: false },
  { key: 'mcp_args', label: 'Arguments MCP (JSON)', required: false },
  { key: 'mcp_env', label: 'Env MCP (JSON)', required: false },
  { key: 'doc_slug', label: 'Slug documentation', required: false },
  { key: 'doc_description', label: 'Description documentation', required: false },
  { key: 'created_by', label: 'Créateur (défaut : utilisateur connecté)', required: false },
]
```

- [ ] **Step 2: Add auto-detect aliases to `GoogleSheetsImportView`**

In `apps-microservices/mcp-gateway-frontend/src/views/GoogleSheetsImportView.vue`, locate the `fieldMap` inside `autoDetectMapping` (around lines 386–402) and append a `created_by` entry:

```ts
  const fieldMap: Record<string, string[]> = {
    name: ['name', 'servername', 'nom', 'nomserveur'],
    url: ['url', 'serverurl', 'adresse', 'endpoint'],
    auth_headers: ['authheaders', 'headers', 'auth'],
    tags: ['tags', 'tag', 'etiquettes'],
    transport_preference: ['transportpreference', 'transport'],
    connect_timeout_ms: ['connecttimeoutms', 'timeout'],
    tool_prefix: ['toolprefix', 'prefix'],
    icon: ['icon', 'icone'],
    mcp_transport: ['mcptransport'],
    mcp_command: ['mcpcommand', 'command', 'commande'],
    mcp_args: ['mcpargs', 'args', 'arguments'],
    mcp_env: ['mcpenv', 'env', 'environnement'],
    doc_slug: ['docslug', 'slug'],
    doc_description: ['docdescription', 'description'],
    created_by: ['createdby', 'created_by', 'owner', 'email', 'createur', 'createur', 'auteur'],
  }
```

(The `column_mapping` is already passed verbatim to the backend in `handleImport` — the new key flows through without further changes.)

- [ ] **Step 3: Typecheck + build**

Run:
```bash
cd apps-microservices/mcp-gateway-frontend && npm run typecheck && npm run build
```

Expected: success.

- [ ] **Step 4: Manual smoke test**

Start the dev server (or `docker compose up mcp-gateway-frontend mcp-gateway-service`), navigate to `/templates`, click an `http_batch` template card, walk through the wizard, confirm:

1. The Mapping step shows a "Créateur (défaut : utilisateur connecté)" row at the bottom.
2. With no column selected, the import proceeds and stamps `mcp_servers.created_by` with the connected user.
3. With a `created_by` column selected and a per-row cell, the imported row carries that cell value (verify with `SELECT id, name, created_by FROM mcp_servers ORDER BY created_at DESC LIMIT 5;`).
4. With a `created_by` column selected and an empty cell, the row falls back to the connected user.

Document any observed behavior in the commit body if unexpected.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/components/google/ColumnMappingTable.vue \
        apps-microservices/mcp-gateway-frontend/src/views/GoogleSheetsImportView.vue
git commit -m "$(cat <<'EOF'
feat(mcp-gateway-frontend): created_by column picker in server import

ColumnMappingTable exposes an optional 'Créateur' row and the import
view auto-detects common header aliases (created_by, owner, email,
createur, auteur). Empty column falls back to the connected user.

EN: Sélecteur de colonne 'Créateur' dans l'import des serveurs depuis
Google Sheets, avec auto-détection des entêtes courants.
EOF
)"
```

---

## Task 7: Add the `<select>` to the stdio Mapping step

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/views/TemplateInstanceSheetImportView.vue`

- [ ] **Step 1: Add the ref**

In `apps-microservices/mcp-gateway-frontend/src/views/TemplateInstanceSheetImportView.vue`, locate the Step 1 state block (around lines 386–393). Append `createdByColumn`:

```ts
// Step 1: mapping
const nameColumn = ref('')
const credentialsColumn = ref('')
const extraEnvColumns = reactive<Record<string, string>>({})
const createdByColumn = ref('')
const namePrefix = ref('')
const fixedTags = ref('')
const fixedToolPrefix = ref('')
const fixedIcon = ref('')
const autoDiscover = ref(true)
```

- [ ] **Step 2: Add the `<select>` in the template**

In the same file, locate the Credentials column `<div>` inside Step 1 (around lines 155–170). Insert a new `<div>` right after it, before the `<!-- Dynamic per-field mappings -->` comment block:

```vue
                <div>
                  <label for="map-creds" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Colonne Credentials JSON <span class="text-red-500">*</span>
                  </label>
                  <select
                    id="map-creds"
                    v-model="credentialsColumn"
                    class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                  >
                    <option value="">—</option>
                    <option v-for="h in preview.headers" :key="h" :value="h">{{ h }}</option>
                  </select>
                  <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    Cellule contenant la clé de service complète (JSON) en texte brut.
                  </p>
                </div>

                <!-- Optional: column whose cell value becomes the row's created_by.
                     Empty cell or no column selected falls back to the connected user. -->
                <div>
                  <label for="map-created-by" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Colonne Créateur (optionnel)
                  </label>
                  <select
                    id="map-created-by"
                    v-model="createdByColumn"
                    class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                  >
                    <option value="">Utilisateur connecté (défaut)</option>
                    <option v-for="h in preview.headers" :key="h" :value="h">{{ h }}</option>
                  </select>
                  <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    Par défaut, l'utilisateur connecté est utilisé. Si vous sélectionnez une colonne, sa valeur (par ligne) remplacera ce défaut quand la cellule est non vide.
                  </p>
                </div>
```

- [ ] **Step 3: Auto-detect on header match**

In the same file, locate `autoDetectMapping` (around lines 486–512). At the very end of the function (before the closing `}`), add:

```ts
  if (!createdByColumn.value) {
    const match = headers.find(h => {
      const n = normalize(h)
      return ['createdby', 'created_by', 'owner', 'email', 'createur', 'auteur'].includes(n)
    })
    if (match) createdByColumn.value = match
  }
```

- [ ] **Step 4: Send the field in `handleImport`**

In the same file, locate `handleImport` (around lines 520–548). Update the `googleApi.importInstancesFromSheet({...})` call to include `created_by_column`:

```ts
    importResult.value = await googleApi.importInstancesFromSheet({
      spreadsheet_id: sheetInfo.value.spreadsheet_id,
      sheet_name: selectedSheet.value,
      template_slug: props.slug,
      name_column: nameColumn.value,
      credentials_column: credentialsColumn.value,
      extra_env_columns: Object.keys(envCleaned).length ? envCleaned : undefined,
      name_prefix: namePrefix.value || undefined,
      fixed_tags: fixedTags.value || undefined,
      fixed_tool_prefix: fixedToolPrefix.value || undefined,
      fixed_icon: fixedIcon.value || undefined,
      auto_discover: autoDiscover.value || undefined,
      created_by_column: createdByColumn.value || undefined,
    })
```

- [ ] **Step 5: Typecheck + build**

Run:
```bash
cd apps-microservices/mcp-gateway-frontend && npm run typecheck && npm run build
```

Expected: success.

- [ ] **Step 6: Manual smoke test**

Walk through the stdio import flow from a `stdio` template card on `/templates`:

1. Mapping step shows the new "Colonne Créateur (optionnel)" `<select>` after Credentials.
2. Default option label reads `Utilisateur connecté (défaut)`.
3. With no column selected → linked `template_instances.created_by` = connected user email. Verify with `SELECT id, name, created_by FROM template_instances ORDER BY created_at DESC LIMIT 5;`.
4. With a `created_by` column selected and per-row cell values → each row carries the cell value.
5. Empty cell in a selected `created_by` column → row falls back to the connected user.
6. Mapping a non-existent header (by hand-crafting a request via DevTools, since the UI only lists real headers) → backend returns 400 with `created_by_column "X" not found in sheet headers`.

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/views/TemplateInstanceSheetImportView.vue
git commit -m "$(cat <<'EOF'
feat(mcp-gateway-frontend): created_by column picker in instance import

TemplateInstanceSheetImportView adds an optional 'Colonne Créateur'
select after the credentials mapping, with header auto-detection
(created_by, owner, email, createur, auteur) and a default option that
labels the connected-user fallback explicitly.

EN: Sélecteur de colonne 'Créateur' dans l'import des instances de
templates depuis Google Sheets.
EOF
)"
```

---

## Task 8: Final verification

- [ ] **Step 1: Full backend build + tests**

Run:
```bash
cd apps-microservices/mcp-gateway-service && go build ./... && go test ./...
```

Expected: success across all packages.

- [ ] **Step 2: Full frontend typecheck + build + unit tests**

Run:
```bash
cd apps-microservices/mcp-gateway-frontend && npm run typecheck && npm run build && npm run test --silent
```

Expected: success.

- [ ] **Step 3: End-to-end smoke (both flows)**

Bring up the stack:
```bash
docker compose up -d mcp-gateway-service mcp-gateway-frontend
```

In a browser, repeat the two flows described in Tasks 6.Step 4 and 7.Step 6, this time on the live stack. Confirm:

- Both DBs columns receive the expected values.
- The connected-user fallback still works when the picker is left empty in both flows.

- [ ] **Step 4: Confirm spec coverage**

Re-read `docs/superpowers/specs/2026-05-12-template-import-created-by-override-design.md`. Every "Validation rules" row, every "Tests" item, and every "Affected flows" row should map to behavior verified above. Note any gaps in the PR description.

- [ ] **Step 5: Push + open PR**

```bash
git push -u origin features/poc
gh pr create --title "feat(mcp-gateway): created_by override for sheet imports" --body "$(cat <<'EOF'
## Summary
- Backend: shared `resolveCreatedBy` helper + per-row resolution in `handleSheetImport` (http_batch) and `handleImportInstancesFromSheet` (stdio).
- Backend: optional `column_mapping.created_by` (server flow) and `created_by_column` (instance flow) DTO fields; stdio handler pre-flights the header, http_batch handler silently falls back per row.
- Frontend: column picker exposed in both wizards (Mapping step), with auto-detect on common header aliases. Empty selection → connected-user fallback (existing behavior preserved).

Spec: `docs/superpowers/specs/2026-05-12-template-import-created-by-override-design.md`
Plan: `docs/superpowers/plans/2026-05-12-template-import-created-by-override.md`

## Test plan
- [x] `go test ./...` in `mcp-gateway-service` (new `TestResolveCreatedBy` table-driven)
- [x] `npm run typecheck && npm run build` in `mcp-gateway-frontend`
- [x] Manual: stdio flow — column selected, cell non-empty → DB shows cell value
- [x] Manual: stdio flow — column selected, cell empty → DB shows connected user
- [x] Manual: stdio flow — column not selected → DB shows connected user (regression)
- [x] Manual: http_batch flow — same three cases
- [x] Manual: stdio handler returns 400 with explicit message on header missing
EOF
)"
```

---

## Self-review (run before declaring complete)

1. **Spec coverage**
   - Both flows wired? ✔ Tasks 3 (http_batch) + 4 (stdio).
   - Resolver shared? ✔ Task 1.
   - Frontend picker in Mapping step? ✔ Tasks 6 + 7.
   - Auto-detect aliases? ✔ Tasks 6.Step 2 + 7.Step 3.
   - stdio pre-flight 400 on missing header? ✔ Task 4.Step 2.
   - http_batch silent fallback? ✔ Task 3.Step 1 uses `resolveCreatedBy` which returns fallback when header missing.
   - Free string (no email regex, no users-table lookup)? ✔ resolver is type-blind.
   - Default = connected user? ✔ `fallbackCreatedBy` / `userEmail` is always the JWT user email.
   - Tests cover the four cases in the spec? ✔ Task 1.Step 1 (5 sub-cases including row-shorter-than-colIndex).

2. **Placeholder scan**
   - No "TODO", "TBD", "fill in details", "similar to Task N" with elided code, "appropriate error handling". ✔

3. **Type consistency**
   - Backend: `ColumnMapping.CreatedBy` (json `created_by`) ↔ frontend `ColumnMapping.created_by`. ✔
   - Backend: `InstanceSheetImportRequest.CreatedByColumn` (json `created_by_column`) ↔ frontend `InstanceSheetImportRequest.created_by_column`. ✔
   - Resolver signature `resolveCreatedBy(column string, row []string, colIndex map[string]int, fallback string) string` consistent across Tasks 1, 3, 4. ✔

No gaps found.
