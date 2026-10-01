# Zoho Row Icons + Per-Row Info Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace text action buttons on `ZohoAdminCard` and `ZohoUserList` with a shared icon-only `IconActionButton`, add an Info icon that opens a new per-row detail page, and expose `GET /api/v1/zoho-imports/{id}/tools` to back the tool catalog on that page.

**Architecture:** One small new Vue component (`IconActionButton.vue`) centralises the icon button style. Both Zoho row components delegate to it, with the same five emits plus a new `info` emit wired to a fresh route `/admin/templates/:slug/zoho-imports/:id` (`ZohoImportDetailView.vue`). The view reads `GET /api/v1/zoho-imports/{id}` for metadata and a new `GET /api/v1/zoho-imports/{id}/tools` for the persisted catalog from `zoho_import_tools`. Spec lives at `docs/superpowers/specs/2026-05-15-zoho-row-icons-and-info-page-design.md`.

**Tech Stack:**
- Backend: Go 1.24, `net/http`, GORM, existing `repository.ZohoImportRepo.ListTools`
- Frontend: Vue 3.5 + TypeScript 5.7, Pinia, Vue Router 4, PrimeIcons (already loaded), Tailwind
- Tests: `go test` for the gateway service, Vitest for the frontend api spec

---

## Files Touched

**Backend (mcp-gateway-service):**
- Modify: `internal/api/zoho_admin_dto.go` — add `ZohoImportToolDTO` + helper
- Modify: `internal/api/zoho_admin_handlers.go` — add `handleZohoImportTools` and route it from `handleZohoImportByID`
- Modify: `internal/api/zoho_admin_handlers_test.go` — 4 new tests
- Modify: `CLAUDE.md` — document the new endpoint

**Frontend (mcp-gateway-frontend):**
- Create: `src/components/ui/IconActionButton.vue`
- Modify: `src/components/zoho/ZohoAdminCard.vue` — swap text buttons; add `info` emit
- Modify: `src/components/zoho/ZohoUserList.vue` — swap text buttons; add `info` emit; state-aware toggle icon; shrink Actions column
- Modify: `src/components/zoho/ZohoImportsSection.vue` — wire `@info` → router push
- Modify: `src/types/zoho.ts` — `ZohoImportTool`, `ZohoImportToolsResponse`
- Modify: `src/api/zohoImports.ts` — `listTools` method
- Modify: `src/api/zohoImports.spec.ts` — one new test
- Modify: `src/router/index.ts` — register `zoho-import-detail`
- Create: `src/views/ZohoImportDetailView.vue`
- Modify: `CLAUDE.md` — document the new view, route, and shared button

---

## Task 1: Backend — `ZohoImportToolDTO` + helper

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_dto.go`

- [ ] **Step 1: Append the DTO to the bottom of the file**

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

// ZohoImportToolsResponse is the wire shape of GET /{id}/tools.
type ZohoImportToolsResponse struct {
	Tools []ZohoImportToolDTO `json:"tools"`
	Total int                 `json:"total"`
}
```

- [ ] **Step 2: Append the helper** (in the same file, after the DTO block)

```go
func zohoImportToolToDTO(t *db.ZohoImportTool) ZohoImportToolDTO {
	return ZohoImportToolDTO{
		Name:        t.Name,
		Description: t.Description,
		InputSchema: string(t.InputSchema),
		UpdatedAt:   t.UpdatedAt.UTC().Format(time.RFC3339),
	}
}
```

Note: `zoho_admin_dto.go` currently has no imports — adding the helper requires importing `mcp-gateway/internal/db` and `time`. Add the import block at the top of the file if not present:

```go
import (
	"time"

	"mcp-gateway/internal/db"
)
```

- [ ] **Step 3: Verify build**

Run: `docker exec gateway-go go build -buildvcs=false ./...`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/zoho_admin_dto.go
git commit -m "feat(mcp-gateway-service): add ZohoImportToolDTO + helper"
```

---

## Task 2: Backend — failing happy-path test for `GET /{id}/tools`

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go`

- [ ] **Step 1: Append the test**

```go
func TestHandleZohoImportTools_Happy(t *testing.T) {
	h := newTestZohoAdminHandler(t)

	// Create a user row to attach tools to.
	body, _ := json.Marshal(map[string]any{
		"name":       "alice",
		"url":        "https://alice.example.com",
		"created_by": "alice@hellopro.fr",
	})
	createReq := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports", bytes.NewReader(body))
	createRec := httptest.NewRecorder()
	h.handleZohoImports(createRec, createReq)
	if createRec.Code != http.StatusCreated {
		t.Fatalf("setup row status = %d, want 201; body=%s", createRec.Code, createRec.Body.String())
	}
	var created ZohoImportRowDTO
	if err := json.Unmarshal(createRec.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode created row: %v", err)
	}

	// Seed two tools via the repo directly.
	if _, err := h.zohoImportRepo.ReplaceTools(created.ID, []db.ZohoImportTool{
		{Name: "leads_list", Description: "List leads", InputSchema: json.RawMessage(`{"type":"object"}`)},
		{Name: "leads_get", Description: "Get one lead", InputSchema: json.RawMessage(`{"type":"object"}`)},
	}); err != nil {
		t.Fatalf("seed tools: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/api/v1/zoho-imports/"+created.ID+"/tools", nil)
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200; body=%s", rec.Code, rec.Body.String())
	}
	var resp ZohoImportToolsResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Total != 2 {
		t.Fatalf("total = %d, want 2", resp.Total)
	}
	names := []string{resp.Tools[0].Name, resp.Tools[1].Name}
	if !(contains(names, "leads_list") && contains(names, "leads_get")) {
		t.Fatalf("names = %v, want both leads_list and leads_get", names)
	}
}

func contains(s []string, v string) bool {
	for _, x := range s {
		if x == v {
			return true
		}
	}
	return false
}
```

- [ ] **Step 2: Verify the test fails**

Run: `docker exec gateway-go go test -buildvcs=false ./internal/api/ -run TestHandleZohoImportTools_Happy -v`
Expected: FAIL — `handleZohoImportByID` does not recognise the `/tools` subroute, so it returns 404 with `unknown subroute`. The assertion `rec.Code != http.StatusOK` should be the failing line.

Note: do not commit yet. The implementation lands in Task 3.

---

## Task 3: Backend — implement `handleZohoImportTools` and route it

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go`

- [ ] **Step 1: Add the subroute dispatch**

Find `handleZohoImportByID` (around line 158-204 in the current file). Inside the function, after the existing branches:

```go
	if rest == "test" {
		h.handleZohoImportTest(w, r, id)
		return
	}
	if rest == "discover" {
		h.handleZohoImportDiscover(w, r, id)
		return
	}
```

Insert:

```go
	if rest == "tools" {
		h.handleZohoImportTools(w, r, id)
		return
	}
```

- [ ] **Step 2: Add the handler**

Append `handleZohoImportTools` next to `handleZohoImportDiscover`:

```go
// handleZohoImportTools returns the persisted tool catalog for one import row.
// Read-only — refresh via POST /api/v1/zoho-imports/{id}/discover.
func (h *Handler) handleZohoImportTools(w http.ResponseWriter, r *http.Request, id string) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}
	row, err := h.zohoImportRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if row == nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
		return
	}
	tools, err := h.zohoImportRepo.ListTools(id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	out := ZohoImportToolsResponse{
		Tools: make([]ZohoImportToolDTO, 0, len(tools)),
		Total: len(tools),
	}
	for i := range tools {
		out.Tools = append(out.Tools, zohoImportToolToDTO(&tools[i]))
	}
	writeJSON(w, http.StatusOK, out)
}
```

- [ ] **Step 3: Run the happy-path test**

Run: `docker exec gateway-go go test -buildvcs=false ./internal/api/ -run TestHandleZohoImportTools_Happy -v`
Expected: PASS.

- [ ] **Step 4: Run the full api package as regression**

Run: `docker exec gateway-go go test -buildvcs=false ./internal/api/ -v`
Expected: every test PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go
git commit -m "feat(mcp-gateway-service): add GET /api/v1/zoho-imports/{id}/tools"
```

---

## Task 4: Backend — three more `handleZohoImportTools` tests

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go`

- [ ] **Step 1: Append the three tests**

```go
func TestHandleZohoImportTools_RowNotFound(t *testing.T) {
	h := newTestZohoAdminHandler(t)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/zoho-imports/missing/tools", nil)
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404; body=%s", rec.Code, rec.Body.String())
	}
}

func TestHandleZohoImportTools_EmptyCatalog(t *testing.T) {
	h := newTestZohoAdminHandler(t)

	body, _ := json.Marshal(map[string]any{
		"name":       "no-tools",
		"url":        "https://no-tools.example.com",
		"created_by": "empty@hellopro.fr",
	})
	createReq := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports", bytes.NewReader(body))
	createRec := httptest.NewRecorder()
	h.handleZohoImports(createRec, createReq)
	if createRec.Code != http.StatusCreated {
		t.Fatalf("setup status = %d, want 201", createRec.Code)
	}
	var created ZohoImportRowDTO
	_ = json.Unmarshal(createRec.Body.Bytes(), &created)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/zoho-imports/"+created.ID+"/tools", nil)
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200; body=%s", rec.Code, rec.Body.String())
	}
	var resp ZohoImportToolsResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &resp)
	if resp.Total != 0 || len(resp.Tools) != 0 {
		t.Fatalf("expected empty tools, got total=%d tools=%v", resp.Total, resp.Tools)
	}
}

func TestHandleZohoImportTools_MethodNotAllowed(t *testing.T) {
	h := newTestZohoAdminHandler(t)

	body, _ := json.Marshal(map[string]any{
		"name":       "x",
		"url":        "https://x.example.com",
		"created_by": "x@hellopro.fr",
	})
	createReq := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports", bytes.NewReader(body))
	createRec := httptest.NewRecorder()
	h.handleZohoImports(createRec, createReq)
	var created ZohoImportRowDTO
	_ = json.Unmarshal(createRec.Body.Bytes(), &created)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports/"+created.ID+"/tools", nil)
	rec := httptest.NewRecorder()
	h.handleZohoImportByID(rec, req)
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status = %d, want 405", rec.Code)
	}
}
```

- [ ] **Step 2: Run all four tools tests**

Run: `docker exec gateway-go go test -buildvcs=false ./internal/api/ -run TestHandleZohoImportTools -v`
Expected: 4 PASS.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go
git commit -m "test(mcp-gateway-service): cover GET /zoho-imports/{id}/tools edge cases"
```

---

## Task 5: Backend — update `mcp-gateway-service/CLAUDE.md`

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`

- [ ] **Step 1: Add the new endpoint bullet**

In the "Zoho Imports Admin" subsection, after the `POST /api/v1/zoho-imports/{id}/test` bullet (around line 204), append:

```
- `GET /api/v1/zoho-imports/{id}/tools` — list the persisted tool catalog for one row. Body: `{tools: [{name, description, input_schema, updated_at}], total}`. Returns 200 (empty list when catalog empty), 404 when the row is missing. Read-only — refresh the catalog via `POST /api/v1/zoho-imports/{id}/discover`.
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/mcp-gateway-service/CLAUDE.md
git commit -m "docs(mcp-gateway-service): document GET /api/v1/zoho-imports/{id}/tools"
```

---

## Task 6: Frontend — add tool types to `types/zoho.ts`

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/types/zoho.ts`

- [ ] **Step 1: Append the two interfaces**

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

- [ ] **Step 2: Typecheck**

Run from `apps-microservices/mcp-gateway-frontend/`: `npm run type-check`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/types/zoho.ts
git commit -m "feat(mcp-gateway-frontend): add ZohoImportTool types"
```

---

## Task 7: Frontend — failing API spec for `listTools`

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/api/zohoImports.spec.ts`

- [ ] **Step 1: Append the test inside the same describe-tree pattern used by the `create` test (commit `6dd649e3`)**

```ts
describe('zohoImportsApi.listTools', () => {
  it('GETs /api/v1/zoho-imports/{id}/tools', async () => {
    const resp = {
      tools: [
        {
          name: 'leads_list',
          description: 'List leads',
          input_schema: '{"type":"object"}',
          updated_at: '2026-05-15T00:00:00Z',
        },
      ],
      total: 1,
    }
    const getSpy = vi.spyOn(api, 'get').mockResolvedValueOnce(resp)

    const result = await zohoImportsApi.listTools('row-id')

    expect(getSpy).toHaveBeenCalledWith('/api/v1/zoho-imports/row-id/tools')
    expect(result).toEqual(resp)
  })
})
```

- [ ] **Step 2: Run and verify failure**

Run from `apps-microservices/mcp-gateway-frontend/`: `npx vitest run src/api/zohoImports.spec.ts`
Expected: FAIL — `zohoImportsApi.listTools is not a function`.

Do not commit yet.

---

## Task 8: Frontend — implement `zohoImportsApi.listTools`

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/api/zohoImports.ts`

- [ ] **Step 1: Extend the type import**

Replace the top-of-file type import block with:

```ts
import type {
  ZohoImportRow,
  ZohoImportListResponse,
  ZohoImportUpdateRequest,
  ZohoImportTestResponse,
  ZohoAdminUpsertRequest,
  ZohoUserCreateRequest,
  ZohoImportToolsResponse,
} from '@/types/zoho'
```

- [ ] **Step 2: Add the method inside the `zohoImportsApi` object, directly above `getAdmin`**

```ts
  listTools(id: string): Promise<ZohoImportToolsResponse> {
    return api.get<ZohoImportToolsResponse>(`${BASE}/${encodeURIComponent(id)}/tools`)
  },
```

- [ ] **Step 3: Re-run the spec**

Run from `apps-microservices/mcp-gateway-frontend/`: `npx vitest run src/api/zohoImports.spec.ts`
Expected: PASS.

- [ ] **Step 4: Typecheck**

`npm run type-check` → exit 0.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/api/zohoImports.ts apps-microservices/mcp-gateway-frontend/src/api/zohoImports.spec.ts
git commit -m "feat(mcp-gateway-frontend): add zohoImportsApi.listTools"
```

---

## Task 9: Frontend — create `IconActionButton`

**Files:**
- Create: `apps-microservices/mcp-gateway-frontend/src/components/ui/IconActionButton.vue`

- [ ] **Step 1: Create the file with this exact content**

```vue
<template>
  <button
    type="button"
    :disabled="disabled"
    :title="label"
    :aria-label="label"
    :class="['inline-flex items-center justify-center w-8 h-8 rounded-md border text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed', toneClasses]"
    @click="$emit('click', $event)"
  >
    <i :class="['pi', icon, 'text-xs']" />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  icon: string
  label: string
  tone?: 'neutral' | 'brand' | 'danger'
  disabled?: boolean
}>()

defineEmits<{ click: [e: MouseEvent] }>()

const toneClasses = computed(() => {
  switch (props.tone) {
    case 'brand':
      return 'border-brand-300 dark:border-brand-700 text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-500/10'
    case 'danger':
      return 'border-error-300 dark:border-error-700 text-error-600 hover:bg-error-50 dark:hover:bg-error-500/10'
    default:
      return 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5'
  }
})
</script>
```

- [ ] **Step 2: Typecheck + lint**

Run from `apps-microservices/mcp-gateway-frontend/`:
- `npm run type-check` → exit 0
- `npx eslint src/components/ui/IconActionButton.vue` → exit 0

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/components/ui/IconActionButton.vue
git commit -m "feat(mcp-gateway-frontend): add IconActionButton component"
```

---

## Task 10: Frontend — swap `ZohoAdminCard` buttons to `IconActionButton`

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoAdminCard.vue`

- [ ] **Step 1: Replace the four-button block**

Replace lines 16-41 (the entire `<div class="flex gap-2 shrink-0">…</div>` block) with:

```vue
      <div class="flex gap-2 shrink-0">
        <IconActionButton
          icon="pi-info-circle"
          label="Détails"
          @click="$emit('info')"
        />
        <IconActionButton
          icon="pi-bolt"
          label="Tester"
          @click="$emit('test')"
        />
        <IconActionButton
          icon="pi-sync"
          label="Découvrir"
          tone="brand"
          @click="$emit('discover')"
        />
        <IconActionButton
          icon="pi-pencil"
          label="Modifier"
          @click="$emit('edit')"
        />
        <IconActionButton
          icon="pi-trash"
          label="Supprimer"
          tone="danger"
          @click="$emit('delete')"
        />
      </div>
```

- [ ] **Step 2: Add the import** (inside `<script setup lang="ts">`)

Insert next to the existing imports:

```ts
import IconActionButton from '@/components/ui/IconActionButton.vue'
```

- [ ] **Step 3: Extend `defineEmits`**

Change:

```ts
defineEmits<{
  edit: []
  test: []
  discover: []
  delete: []
  create: []
}>()
```

to:

```ts
defineEmits<{
  edit: []
  test: []
  discover: []
  delete: []
  create: []
  info: []
}>()
```

- [ ] **Step 4: Typecheck + lint**

- `npm run type-check` → exit 0
- `npx eslint src/components/zoho/ZohoAdminCard.vue` → exit 0

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoAdminCard.vue
git commit -m "feat(mcp-gateway-frontend): iconify ZohoAdminCard actions and add Info"
```

---

## Task 11: Frontend — swap `ZohoUserList` buttons to `IconActionButton`

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoUserList.vue`

- [ ] **Step 1: Replace the six-button block inside the Actions column**

Find the `<Column header="Actions" header-style="width: 22rem; text-align: right">` block (line 64). Replace its `<template #body="{ data }">` content (lines 65-109) — keep the `ZohoTestResultBadge` and discover badge spans, replace just the six `<button>` elements — with the following six `IconActionButton` instances. The full replacement template body is:

```vue
        <template #body="{ data }">
          <div class="inline-flex items-center gap-2 justify-end w-full">
            <ZohoTestResultBadge :result="testResults[data.id] ?? null" />
            <span
              v-if="discoverResults?.[data.id]"
              class="text-xs px-2 py-0.5 rounded-full font-medium"
              :class="discoverResults[data.id]!.ok
                ? 'bg-success-100 text-success-700 dark:bg-success-500/20 dark:text-success-400'
                : 'bg-error-100 text-error-700 dark:bg-error-500/20 dark:text-error-400'"
              :title="`${discoverResults[data.id]!.tools} outils`"
            >
              {{ discoverResults[data.id]!.tools }} outils
            </span>
            <IconActionButton
              icon="pi-info-circle"
              label="Détails"
              @click="$emit('info', data)"
            />
            <IconActionButton
              icon="pi-bolt"
              label="Tester"
              @click="$emit('test', data)"
            />
            <IconActionButton
              icon="pi-sync"
              label="Découvrir"
              tone="brand"
              @click="$emit('discover', data)"
            />
            <IconActionButton
              :icon="data.is_active ? 'pi-pause' : 'pi-play'"
              :label="data.is_active ? 'Désactiver' : 'Activer'"
              @click="$emit('toggle', data)"
            />
            <IconActionButton
              icon="pi-pencil"
              label="Modifier"
              @click="$emit('edit', data)"
            />
            <IconActionButton
              icon="pi-trash"
              label="Supprimer"
              tone="danger"
              @click="$emit('delete', data)"
            />
          </div>
        </template>
```

- [ ] **Step 2: Shrink the Actions column header**

Change the column declaration from:

```vue
      <Column header="Actions" header-style="width: 22rem; text-align: right">
```

to:

```vue
      <Column header="Actions" header-style="width: 18rem; text-align: right">
```

- [ ] **Step 3: Add the import**

In `<script setup lang="ts">`, add alongside existing imports:

```ts
import IconActionButton from '@/components/ui/IconActionButton.vue'
```

- [ ] **Step 4: Extend `defineEmits`**

Add the `info` emit. Replace:

```ts
const emit = defineEmits<{
  search: [v: string]
  page: [n: number]
  edit: [r: ZohoImportRow]
  delete: [r: ZohoImportRow]
  toggle: [r: ZohoImportRow]
  test: [r: ZohoImportRow]
  discover: [r: ZohoImportRow]
}>()
```

with:

```ts
const emit = defineEmits<{
  search: [v: string]
  page: [n: number]
  edit: [r: ZohoImportRow]
  delete: [r: ZohoImportRow]
  toggle: [r: ZohoImportRow]
  test: [r: ZohoImportRow]
  discover: [r: ZohoImportRow]
  info: [r: ZohoImportRow]
}>()
```

- [ ] **Step 5: Typecheck + lint**

- `npm run type-check` → exit 0
- `npx eslint src/components/zoho/ZohoUserList.vue` → exit 0

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoUserList.vue
git commit -m "feat(mcp-gateway-frontend): iconify ZohoUserList actions and add Info"
```

---

## Task 12: Frontend — wire `@info` in `ZohoImportsSection`

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoImportsSection.vue`

- [ ] **Step 1: Add `@info` bindings**

Find the `<ZohoAdminCard>` element (around lines 13-23) and add the `@info` handler:

```vue
      <ZohoAdminCard
        v-if="activeTab === 'admin'"
        :admin="store.admin"
        :test-result="adminTestResult"
        :discover-result="adminDiscoverResult"
        @create="openAdminEdit(true)"
        @edit="openAdminEdit(false)"
        @test="onTestAdmin"
        @discover="onDiscoverAdmin"
        @delete="onDeleteAdmin"
        @info="onInfoAdmin"
      />
```

Find the `<ZohoUserList>` element and add `@info`:

```vue
      <ZohoUserList
        v-else
        :rows="store.users"
        :total="store.usersTotal"
        :page="store.usersPage"
        :limit="store.usersLimit"
        :search="store.usersSearch"
        :test-results="userTestResults"
        :discover-results="userDiscoverResults"
        @search="onSearchUsers"
        @page="(n) => store.fetchUsers({ page: n })"
        @edit="openUserEdit"
        @delete="onDeleteUser"
        @toggle="onToggleUser"
        @test="onTestUser"
        @discover="onDiscoverUser"
        @info="onInfoUser"
      />
```

- [ ] **Step 2: Add the two handlers**

In `<script setup>`, after the existing `goToAdd` function, add:

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

- [ ] **Step 3: Typecheck**

`npm run type-check` → exit 0. (`ZohoImportFormView` lazy-import still works; the new `zoho-import-detail` route hasn't been registered yet, but `router.push({ name: ... })` is not statically checked.)

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoImportsSection.vue
git commit -m "feat(mcp-gateway-frontend): route ZohoImportsSection info clicks to detail view"
```

---

## Task 13: Frontend — register `zoho-import-detail` route

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/router/index.ts`

- [ ] **Step 1: Insert the route**

In `apps-microservices/mcp-gateway-frontend/src/router/index.ts`, find the existing `zoho-import-new` route entry. Insert this new entry **directly above** it (more-specific paths first):

```ts
    {
      path: '/admin/templates/:slug/zoho-imports/:id',
      name: 'zoho-import-detail',
      component: () => import('@/views/ZohoImportDetailView.vue'),
      meta: { requiresAuth: true, title: 'Détails import Zoho', minRole: 'admin' },
      props: true,
    },
```

- [ ] **Step 2: Typecheck**

`npm run type-check`.
Expected: will fail with `TS2307: Cannot find module '@/views/ZohoImportDetailView.vue'` until Task 14 lands. This is expected and matches the same flow used in commit `ae53ab2e` for `ZohoImportFormView`. Proceed to commit anyway — Task 14 immediately follows.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/router/index.ts
git commit -m "feat(mcp-gateway-frontend): add zoho-import-detail route"
```

---

## Task 14: Frontend — create `ZohoImportDetailView`

**Files:**
- Create: `apps-microservices/mcp-gateway-frontend/src/views/ZohoImportDetailView.vue`

- [ ] **Step 1: Create the file with this content**

```vue
<template>
  <div>
    <div class="mb-6 flex items-center gap-4">
      <BaseButton variant="ghost" size="sm" @click="goBack">
        <i class="pi pi-arrow-left text-xs mr-1" />
        Retour
      </BaseButton>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ row?.name || 'Import Zoho' }}
      </h1>
      <span
        v-if="row"
        class="text-xs px-2 py-0.5 rounded-full font-medium"
        :class="row.is_admin
          ? 'bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-400'
          : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'"
      >
        {{ row.is_admin ? 'Compte admin' : 'Utilisateur' }}
      </span>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <i class="pi pi-spinner pi-spin text-2xl text-gray-400 dark:text-gray-500" />
    </div>

    <div
      v-else-if="!row"
      class="text-center py-12 text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-900 rounded-lg border border-dashed border-gray-200 dark:border-gray-800"
    >
      <i class="pi pi-exclamation-circle text-4xl mb-3 block" />
      <p class="text-sm">Import introuvable.</p>
      <button
        class="mt-3 text-xs text-brand-500 hover:text-brand-600"
        @click="goBack"
      >
        Retour au template
      </button>
    </div>

    <template v-else>
      <!-- Metadata -->
      <section class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5 mb-6">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Métadonnées</h2>
        <dl class="divide-y divide-gray-100 dark:divide-gray-800 text-sm">
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Nom</dt>
            <dd class="text-gray-900 dark:text-white col-span-2">{{ row.name }}</dd>
          </div>
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">URL</dt>
            <dd class="text-gray-900 dark:text-white col-span-2 break-all">{{ row.url }}</dd>
          </div>
          <div v-if="!row.is_admin" class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Créé par</dt>
            <dd class="text-gray-900 dark:text-white col-span-2">{{ row.created_by }}</dd>
          </div>
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Actif</dt>
            <dd class="text-gray-900 dark:text-white col-span-2">{{ row.is_active ? 'oui' : 'non' }}</dd>
          </div>
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Template</dt>
            <dd class="text-gray-900 dark:text-white col-span-2 font-mono text-xs">{{ row.template_slug || '—' }}</dd>
          </div>
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Headers</dt>
            <dd class="text-gray-900 dark:text-white col-span-2 font-mono text-xs">
              {{ row.auth_header_keys.length ? row.auth_header_keys.join(', ') : '—' }}
            </dd>
          </div>
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Créé le</dt>
            <dd class="text-gray-900 dark:text-white col-span-2">{{ formatDate(row.created_at) }}</dd>
          </div>
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Modifié le</dt>
            <dd class="text-gray-900 dark:text-white col-span-2">{{ formatDate(row.updated_at) }}</dd>
          </div>
        </dl>
      </section>

      <!-- Test / Discover -->
      <section class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5 mb-6">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Test &amp; découverte</h2>
        <div class="flex items-center gap-3 flex-wrap">
          <button
            class="px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 inline-flex items-center gap-2"
            :disabled="testing"
            @click="onTest"
          >
            <i class="pi pi-bolt text-xs" />
            Tester
          </button>
          <button
            class="px-3 py-1.5 text-sm rounded-md border border-brand-300 dark:border-brand-700 text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-500/10 inline-flex items-center gap-2"
            :disabled="discovering"
            @click="onDiscover"
          >
            <i class="pi pi-sync text-xs" />
            Découvrir
          </button>
          <ZohoTestResultBadge v-if="testResult" :result="testResult" />
          <span
            v-if="discoverResult"
            class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="discoverResult.ok
              ? 'bg-success-100 text-success-700 dark:bg-success-500/20 dark:text-success-400'
              : 'bg-error-100 text-error-700 dark:bg-error-500/20 dark:text-error-400'"
          >
            Découverte : {{ discoverResult.tools }} outils
          </span>
        </div>
      </section>

      <!-- Tools -->
      <section class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">
          Outils ({{ tools.length }})
        </h2>

        <div
          v-if="tools.length === 0"
          class="text-center py-8 text-sm text-gray-500 dark:text-gray-400"
        >
          Aucun outil découvert. Lancez « Découvrir » pour peupler le catalogue.
        </div>

        <ul v-else class="space-y-2">
          <li
            v-for="tool in tools"
            :key="tool.name"
            class="border border-gray-100 dark:border-gray-800 rounded-md p-3"
          >
            <div class="text-sm font-medium text-gray-900 dark:text-white">{{ tool.name }}</div>
            <p
              v-if="tool.description"
              class="text-xs text-gray-600 dark:text-gray-400 mt-1"
            >
              {{ tool.description }}
            </p>
            <details class="mt-2">
              <summary class="text-xs text-brand-500 cursor-pointer">Voir le schéma</summary>
              <pre class="mt-2 text-xs font-mono whitespace-pre-wrap bg-gray-50 dark:bg-white/5 p-2 rounded">{{ prettySchema(tool.input_schema) }}</pre>
            </details>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { zohoImportsApi } from '@/api/zohoImports'
import { useZohoImportsStore } from '@/stores/zohoImports'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import ZohoTestResultBadge from '@/components/zoho/ZohoTestResultBadge.vue'
import { toErrorMessage } from '@/utils/error'
import type { ZohoImportRow, ZohoImportTool, ZohoImportTestResponse } from '@/types/zoho'

const props = defineProps<{ slug: string; id: string }>()

const router = useRouter()
const store = useZohoImportsStore()
const toast = useToast()

const loading = ref(true)
const row = ref<ZohoImportRow | null>(null)
const tools = ref<ZohoImportTool[]>([])
const testResult = ref<ZohoImportTestResponse | null>(null)
const discoverResult = ref<{ ok: boolean; tools: number } | null>(null)
const testing = ref(false)
const discovering = ref(false)

onMounted(async () => {
  try {
    row.value = await zohoImportsApi.getByID(props.id)
  } catch (err) {
    row.value = null
    toast.error(toErrorMessage(err, 'Erreur lors du chargement de la ligne'))
  }
  if (row.value) {
    try {
      const resp = await zohoImportsApi.listTools(props.id)
      tools.value = resp.tools
    } catch (err) {
      tools.value = []
      toast.error(toErrorMessage(err, 'Erreur lors du chargement du catalogue'))
    }
  }
  loading.value = false
})

function goBack() {
  router.push({ name: 'template-detail', params: { slug: props.slug } })
}

function formatDate(iso: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('fr-FR')
  } catch {
    return iso
  }
}

function prettySchema(raw: string): string {
  if (!raw) return ''
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}

async function onTest() {
  testing.value = true
  try {
    testResult.value = await store.testRow(props.id)
  } catch (err) {
    toast.error(toErrorMessage(err, 'Échec du test'))
  } finally {
    testing.value = false
  }
}

async function onDiscover() {
  discovering.value = true
  try {
    discoverResult.value = await store.discoverRow(props.id)
    if (discoverResult.value?.ok) {
      const resp = await zohoImportsApi.listTools(props.id)
      tools.value = resp.tools
    }
  } catch (err) {
    toast.error(toErrorMessage(err, 'Échec de la découverte'))
  } finally {
    discovering.value = false
  }
}
</script>
```

- [ ] **Step 2: Typecheck + lint**

- `npm run type-check` → exit 0 (the TS2307 from Task 13 is now resolved).
- `npx eslint src/views/ZohoImportDetailView.vue` → exit 0.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/views/ZohoImportDetailView.vue
git commit -m "feat(mcp-gateway-frontend): add ZohoImportDetailView"
```

---

## Task 15: Frontend — update `mcp-gateway-frontend/CLAUDE.md`

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/CLAUDE.md`

- [ ] **Step 1: Add file-inventory lines**

In the File Inventory section, under `src/components/`, add:

```
  ui/IconActionButton.vue           # icon-only action button (neutral/brand/danger)
```

Under `src/views/`, alongside `ZohoImportFormView.vue`, add:

```
    ZohoImportDetailView.vue        # per-row Zoho import detail (metadata + tools)
```

- [ ] **Step 2: Extend the Zoho subsection**

In the existing "Zoho imports admin onglet" subsection, append a new paragraph at the end:

```markdown
Per-row detail page: `/admin/templates/:slug/zoho-imports/:id`
(`ZohoImportDetailView.vue`). Renders row metadata, the persisted tool
catalog from `GET /api/v1/zoho-imports/{id}/tools`, plus inline Tester
/ Découvrir actions that refresh the displayed catalog on success.
Reachable via the `pi pi-info-circle` icon in `ZohoAdminCard` and
`ZohoUserList`. All row actions (Détails / Tester / Découvrir /
Activer-Désactiver / Modifier / Supprimer) use the shared
`components/ui/IconActionButton.vue` (icon-only with native tooltip,
three tones: neutral / brand / danger).
```

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/CLAUDE.md
git commit -m "docs(mcp-gateway-frontend): document IconActionButton + detail view"
```

---

## Task 16: Manual smoke + regression

**Files:** none (verification only)

- [ ] **Step 1: Backend regression**

Run: `docker exec gateway-go go test -buildvcs=false ./...`
Expected: every package PASS.

- [ ] **Step 2: Frontend regression**

Run from `apps-microservices/mcp-gateway-frontend/`:
- `npm run type-check` → exit 0
- `npx vitest run src/api/zohoImports.spec.ts src/stores/zohoImports.spec.ts` → 2 files PASS

- [ ] **Step 3: UI smoke**

Bring up the stack (e.g. `docker compose up -d mcp-gateway-service mcp-gateway-frontend`). In a browser open `http://localhost:8581/admin/templates/zoho` (or the dev URL).

Verify:
1. Admin card: 5 icon-only buttons in order Info / Tester / Découvrir / Modifier / Supprimer. Tooltips show French labels.
2. User list: 6 icon-only buttons in order Info / Tester / Découvrir / Toggle / Modifier / Supprimer. Toggle icon switches between pi-pause (active) and pi-play (inactive).
3. Click Info on the admin card → detail page renders metadata + (empty or populated) tool list.
4. Click Découvrir on the detail page → after success, tool list updates without page reload.
5. Click Tester → badge renders.
6. Open a fabricated id `/admin/templates/zoho/zoho-imports/does-not-exist` → "Import introuvable" view + back link works.

---

## Self-Review (filled in)

**Spec coverage:**
- IconActionButton (one shared component): Task 9.
- ZohoAdminCard / ZohoUserList button swap + new Info emit: Tasks 10, 11.
- Section info-route wiring: Task 12.
- New route `zoho-import-detail`: Task 13.
- ZohoImportDetailView with metadata + tools + inline actions: Task 14.
- Backend `GET /api/v1/zoho-imports/{id}/tools`: Tasks 1, 3.
- 4 backend tests + 1 frontend api spec: Tasks 2, 4, 7, 8.
- CLAUDE.md updates: Tasks 5, 15.
- Manual smoke: Task 16.

**Placeholder scan:** no TBD/TODO; every code step ships a full block; every test step ships full code; expected command output stated.

**Type consistency:**
- `ZohoImportToolDTO` Go and `ZohoImportTool` TS share the wire shape (`name`, `description`, `input_schema`, `updated_at`). ✓
- Route name `zoho-import-detail` used in Tasks 12, 13. ✓
- `info` emit + handler name `onInfoAdmin`/`onInfoUser` used consistently in Tasks 10, 11, 12. ✓
- API method `listTools` consistent across Tasks 7, 8, 14. ✓
- `IconActionButton` import path `@/components/ui/IconActionButton.vue` consistent across Tasks 9, 10, 11. ✓

No gaps found.
