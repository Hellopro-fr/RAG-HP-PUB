# Zoho Template — "Add" Button + Tabbed Form — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "+ Ajouter" button to the Zoho template detail page that opens a 3-step StepTabs wizard for creating a single Zoho import row (admin singleton or per-user, scope inferred from the active tab), backed by a new `POST /api/v1/zoho-imports` endpoint.

**Architecture:** Backend gains one route on the existing `/api/v1/zoho-imports` collection handler that creates a non-admin row via the already-present `repository.CreateUserImport`. Frontend gains one new view `ZohoImportFormView.vue` (mirrors the `ServerFormView` 3-step pattern) and one new route, plus a button + tab-pre-selection wired into the existing `ZohoImportsSection`. Spec lives at `docs/superpowers/specs/2026-05-15-zoho-template-add-button-design.md`.

**Tech Stack:**
- Backend: Go 1.24, `net/http`, GORM, `mcp-gateway/internal/repository`, `mcp-gateway/internal/crypto`
- Frontend: Vue 3.5 + TypeScript 5.7, Pinia, Vue Router 4, PrimeVue / Tailwind, Radix Vue
- Tests: `go test` for the gateway service, Vitest for the frontend store + api spec

---

## Files Touched

**Backend (mcp-gateway-service):**
- Modify: `internal/api/zoho_admin_dto.go` — add `ZohoUserCreateRequest`
- Modify: `internal/api/zoho_admin_handlers.go` — extend `handleZohoImports` method switch, add `handleZohoUserCreate`
- Modify: `internal/api/zoho_admin_handlers_test.go` — 5 new test cases
- Modify: `CLAUDE.md` — document new route

**Frontend (mcp-gateway-frontend):**
- Create: `src/views/ZohoImportFormView.vue`
- Modify: `src/types/zoho.ts` — add `ZohoUserCreateRequest`
- Modify: `src/api/zohoImports.ts` — add `create()`
- Modify: `src/api/zohoImports.spec.ts` — test `create()`
- Modify: `src/stores/zohoImports.ts` — add `createUserImport()` action
- Modify: `src/stores/zohoImports.spec.ts` — test `createUserImport()`
- Modify: `src/components/zoho/ZohoImportsSection.vue` — `+ Ajouter` button + tab pre-selection
- Modify: `src/router/index.ts` — new route `zoho-import-new`
- Modify: `CLAUDE.md` — document new view + route

---

## Task 1: Backend — add `ZohoUserCreateRequest` DTO

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_dto.go`

- [ ] **Step 1: Append the new struct to the DTO file**

Open `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_dto.go` and append (after the existing `ZohoImportTestResponse` block):

```go
// ZohoUserCreateRequest is the body of POST /api/v1/zoho-imports. It
// inserts a per-user row (IsAdmin=false). CreatedBy is required. The admin
// singleton is created via POST /api/v1/zoho-imports/admin instead.
type ZohoUserCreateRequest struct {
	Name         string            `json:"name"`
	URL          string            `json:"url"`
	CreatedBy    string            `json:"created_by"`
	AuthHeaders  map[string]string `json:"auth_headers,omitempty"`
	IsActive     *bool             `json:"is_active,omitempty"`
	TemplateSlug string            `json:"template_slug,omitempty"`
}
```

- [ ] **Step 2: Verify it compiles**

Run: `docker compose -f docker-compose.yml run --rm gateway-go go build ./...` (or, if the persistent `gateway-go` container is available at `/work`, `docker exec gateway-go go build ./...`).
Expected: exit 0, no output.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/zoho_admin_dto.go
git commit -m "feat(mcp-gateway-service): add ZohoUserCreateRequest DTO"
```

---

## Task 2: Backend — write the failing test for POST happy path

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go`

- [ ] **Step 1: Inspect existing helpers**

Read `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go` lines 1-90 to see how a handler test fixture (`newTestHandler`, `seedAdmin`, etc.) is built. Re-use the same fixture in every new test below.

- [ ] **Step 2: Add the happy-path test**

Append to `zoho_admin_handlers_test.go`:

```go
func TestHandleZohoUserCreate_Happy(t *testing.T) {
	h, _ := newTestHandler(t)

	body, _ := json.Marshal(map[string]any{
		"name":          "Alice Zoho",
		"url":           "https://alice.zoho.example.com",
		"created_by":    "alice@hellopro.fr",
		"auth_headers":  map[string]string{"Authorization": "Bearer alice-token"},
		"template_slug": "zoho",
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports", bytes.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleZohoImports(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("status = %d, want 201; body=%s", rec.Code, rec.Body.String())
	}

	listReq := httptest.NewRequest(http.MethodGet, "/api/v1/zoho-imports?is_admin=false", nil)
	listRec := httptest.NewRecorder()
	h.handleZohoImports(listRec, listReq)
	if listRec.Code != http.StatusOK {
		t.Fatalf("list status = %d, want 200", listRec.Code)
	}
	if !strings.Contains(listRec.Body.String(), "alice@hellopro.fr") {
		t.Fatalf("created row missing from list: %s", listRec.Body.String())
	}
}
```

- [ ] **Step 3: Run the test and verify it fails**

Run: `docker exec gateway-go go test ./internal/api/ -run TestHandleZohoUserCreate_Happy -v`
Expected: FAIL — either the handler returns 405 (current behaviour rejects POST) or the `handleZohoUserCreate` symbol is undefined depending on whether the dispatch case is in place. Confirm the assertion line that fails — must be `rec.Code != http.StatusCreated`.

---

## Task 3: Backend — implement `handleZohoUserCreate` and route POST through `handleZohoImports`

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go`

- [ ] **Step 1: Add the POST branch to `handleZohoImports`**

In `internal/api/zoho_admin_handlers.go`, replace the existing method check inside `handleZohoImports` (lines 124-127 in the current file):

```go
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}
```

with:

```go
	switch r.Method {
	case http.MethodGet:
		h.handleZohoUserList(w, r)
		return
	case http.MethodPost:
		h.handleZohoUserCreate(w, r)
		return
	default:
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}
```

Then move the existing list body (the block starting `filter := repository.ZohoListFilter{...}` down to `writeJSON(w, http.StatusOK, out)`) into a new private method:

```go
func (h *Handler) handleZohoUserList(w http.ResponseWriter, r *http.Request) {
	filter := repository.ZohoListFilter{
		Search:    r.URL.Query().Get("search"),
		CreatedBy: effectiveCreatorFilter(r.Context()),
	}
	if isAdminParam := r.URL.Query().Get("is_admin"); isAdminParam != "" {
		val := isAdminParam == "true" || isAdminParam == "1"
		filter.IsAdmin = &val
	}
	page := parsePositiveInt(r.URL.Query().Get("page"), 1)
	limit := parsePositiveInt(r.URL.Query().Get("limit"), 20)

	rows, total, err := h.zohoImportRepo.List(filter, page, limit)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}

	out := ZohoImportListResponse{
		Rows:  make([]ZohoImportRowDTO, 0, len(rows)),
		Total: total,
		Page:  page,
		Limit: limit,
	}
	for i := range rows {
		out.Rows = append(out.Rows, zohoImportToRowDTO(&rows[i], h))
	}
	writeJSON(w, http.StatusOK, out)
}
```

After this refactor, `handleZohoImports` body is only the nil-repo guard + the method switch.

- [ ] **Step 2: Add the create handler**

Append to the same file (above `handleZohoImportByID`):

```go
// handleZohoUserCreate inserts a per-user row. CreatedBy must be non-empty
// and unique. Use POST /api/v1/zoho-imports/admin for the singleton admin row.
func (h *Handler) handleZohoUserCreate(w http.ResponseWriter, r *http.Request) {
	var req ZohoUserCreateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}

	req.Name = strings.TrimSpace(req.Name)
	req.URL = strings.TrimSpace(req.URL)
	req.CreatedBy = strings.TrimSpace(req.CreatedBy)
	req.TemplateSlug = strings.TrimSpace(req.TemplateSlug)

	if req.Name == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "name is required"})
		return
	}
	if req.URL == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "url is required"})
		return
	}
	if req.CreatedBy == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "created_by is required"})
		return
	}
	if !strings.Contains(req.CreatedBy, "@") || strings.HasPrefix(req.CreatedBy, "@") || strings.HasSuffix(req.CreatedBy, "@") {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "created_by must look like an email"})
		return
	}
	if req.TemplateSlug == "" {
		req.TemplateSlug = "zoho"
	}

	existing, err := h.zohoImportRepo.FindUserImportByEmail(req.CreatedBy)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if existing != nil {
		writeJSON(w, http.StatusConflict, ErrorResponse{Error: "a zoho import already exists for this created_by"})
		return
	}

	var encrypted []byte
	if len(req.AuthHeaders) > 0 {
		raw, mErr := json.Marshal(req.AuthHeaders)
		if mErr != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "encode auth_headers: " + mErr.Error()})
			return
		}
		if h.encryptor != nil {
			encrypted, mErr = h.encryptor.Encrypt(raw)
			if mErr != nil {
				writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "encrypt auth_headers: " + mErr.Error()})
				return
			}
		} else {
			encrypted = raw
		}
	}

	isActive := true
	if req.IsActive != nil {
		isActive = *req.IsActive
	}

	row := &db.ZohoImport{
		Name:         req.Name,
		URL:          req.URL,
		CreatedBy:    req.CreatedBy,
		TemplateSlug: req.TemplateSlug,
		IsActive:     isActive,
		AuthHeaders:  encrypted,
	}
	if err := h.zohoImportRepo.CreateUserImport(row); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}

	discoverZohoToolsForImport(r.Context(), h.zohoImportRepo, h.encryptor, row)

	writeJSON(w, http.StatusCreated, zohoImportToRowDTO(row, h))
}
```

- [ ] **Step 3: Run the happy-path test and verify it passes**

Run: `docker exec gateway-go go test ./internal/api/ -run TestHandleZohoUserCreate_Happy -v`
Expected: PASS.

- [ ] **Step 4: Run the entire api test package as a regression check**

Run: `docker exec gateway-go go test ./internal/api/ -v`
Expected: all tests PASS (the refactored `handleZohoUserList` must not have broken existing list tests).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go
git commit -m "feat(mcp-gateway-service): add POST /api/v1/zoho-imports for user rows"
```

---

## Task 4: Backend — validation failure tests

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go`

- [ ] **Step 1: Add the four failure-case tests**

Append the four tests below to `zoho_admin_handlers_test.go`:

```go
func TestHandleZohoUserCreate_MissingCreatedBy(t *testing.T) {
	h, _ := newTestHandler(t)
	body, _ := json.Marshal(map[string]any{
		"name": "x", "url": "https://x.example.com",
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports", bytes.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleZohoImports(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400; body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "created_by") {
		t.Fatalf("error should mention created_by, got %s", rec.Body.String())
	}
}

func TestHandleZohoUserCreate_BadEmailShape(t *testing.T) {
	h, _ := newTestHandler(t)
	body, _ := json.Marshal(map[string]any{
		"name":       "x",
		"url":        "https://x.example.com",
		"created_by": "no-at-sign",
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports", bytes.NewReader(body))
	rec := httptest.NewRecorder()
	h.handleZohoImports(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400; body=%s", rec.Code, rec.Body.String())
	}
}

func TestHandleZohoUserCreate_DuplicateCreatedBy(t *testing.T) {
	h, _ := newTestHandler(t)
	body, _ := json.Marshal(map[string]any{
		"name":       "first",
		"url":        "https://first.example.com",
		"created_by": "dup@hellopro.fr",
	})
	first := httptest.NewRecorder()
	h.handleZohoImports(first, httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports", bytes.NewReader(body)))
	if first.Code != http.StatusCreated {
		t.Fatalf("setup row status = %d, want 201", first.Code)
	}

	body, _ = json.Marshal(map[string]any{
		"name":       "second",
		"url":        "https://second.example.com",
		"created_by": "dup@hellopro.fr",
	})
	rec := httptest.NewRecorder()
	h.handleZohoImports(rec, httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports", bytes.NewReader(body)))
	if rec.Code != http.StatusConflict {
		t.Fatalf("status = %d, want 409; body=%s", rec.Code, rec.Body.String())
	}
}

func TestHandleZohoUserCreate_InvalidJSON(t *testing.T) {
	h, _ := newTestHandler(t)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/zoho-imports", bytes.NewReader([]byte("not json")))
	rec := httptest.NewRecorder()
	h.handleZohoImports(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", rec.Code)
	}
}
```

- [ ] **Step 2: Run all four tests**

Run: `docker exec gateway-go go test ./internal/api/ -run TestHandleZohoUserCreate -v`
Expected: all five `TestHandleZohoUserCreate_*` tests PASS (including the happy-path one from Task 2).

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers_test.go
git commit -m "test(mcp-gateway-service): cover POST /zoho-imports validation failures"
```

---

## Task 5: Backend — update `mcp-gateway-service/CLAUDE.md`

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/CLAUDE.md`

- [ ] **Step 1: Insert the new bullet under the Zoho Imports Admin section**

In `apps-microservices/mcp-gateway-service/CLAUDE.md`, find the line that begins with `- \`GET/POST/DELETE /api/v1/zoho-imports/admin\` —` (around line 199 in the current file). After the existing `GET /api/v1/zoho-imports` bullet (around line 200), insert:

```markdown
- `POST /api/v1/zoho-imports` — create a per-user import row. Body: `{name, url, created_by, auth_headers?, is_active?, template_slug?}`. Returns 201 + row DTO on success, 400 on missing/malformed fields, 409 when `created_by` already has a row. Singleton admin rows still use `POST /api/v1/zoho-imports/admin`.
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/mcp-gateway-service/CLAUDE.md
git commit -m "docs(mcp-gateway-service): document POST /api/v1/zoho-imports"
```

---

## Task 6: Frontend — add `ZohoUserCreateRequest` type

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/types/zoho.ts`

- [ ] **Step 1: Append the new interface**

In `apps-microservices/mcp-gateway-frontend/src/types/zoho.ts`, append after the existing `ZohoAdminUpsertRequest` block:

```ts
/** Body of POST /api/v1/zoho-imports — create a per-user import row. */
export interface ZohoUserCreateRequest {
  name: string
  url: string
  created_by: string
  auth_headers?: Record<string, string>
  is_active?: boolean
  template_slug?: string
}
```

- [ ] **Step 2: Verify typecheck**

Run: `cd apps-microservices/mcp-gateway-frontend && npm run typecheck` (or `npx vue-tsc --noEmit` if the project script differs — inspect `package.json` first).
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/types/zoho.ts
git commit -m "feat(mcp-gateway-frontend): add ZohoUserCreateRequest type"
```

---

## Task 7: Frontend — add the failing API spec for `create()`

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/api/zohoImports.spec.ts`

- [ ] **Step 1: Inspect existing tests**

Read `apps-microservices/mcp-gateway-frontend/src/api/zohoImports.spec.ts` start-to-finish so you can see the fetch-mock pattern and the import of `api`. Re-use exactly the same setup style.

- [ ] **Step 2: Add the test**

Append:

```ts
describe('zohoImportsApi.create', () => {
  it('POSTs the payload to /api/v1/zoho-imports', async () => {
    const row = {
      id: 'new-id',
      name: 'Alice',
      url: 'https://alice.example.com',
      is_admin: false,
      is_active: true,
      created_by: 'alice@hp.fr',
      template_slug: 'zoho',
      auth_header_keys: [],
      created_at: '2026-05-15T00:00:00Z',
      updated_at: '2026-05-15T00:00:00Z',
    }
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce(row)

    const result = await zohoImportsApi.create({
      name: 'Alice',
      url: 'https://alice.example.com',
      created_by: 'alice@hp.fr',
    })

    expect(postSpy).toHaveBeenCalledWith('/api/v1/zoho-imports', {
      name: 'Alice',
      url: 'https://alice.example.com',
      created_by: 'alice@hp.fr',
    })
    expect(result).toEqual(row)
  })
})
```

(Adjust `import { api } from './client'` and `import { zohoImportsApi } from './zohoImports'` at the top of the file if not already present.)

- [ ] **Step 3: Run the spec and verify it fails**

Run: `cd apps-microservices/mcp-gateway-frontend && npx vitest run src/api/zohoImports.spec.ts`
Expected: FAIL — `zohoImportsApi.create is not a function`.

---

## Task 8: Frontend — implement `zohoImportsApi.create`

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/api/zohoImports.ts`

- [ ] **Step 1: Add the method**

Update `apps-microservices/mcp-gateway-frontend/src/api/zohoImports.ts`:

1. Extend the type import at the top:
   ```ts
   import type {
     ZohoImportRow,
     ZohoImportListResponse,
     ZohoImportUpdateRequest,
     ZohoImportTestResponse,
     ZohoAdminUpsertRequest,
     ZohoUserCreateRequest,
   } from '@/types/zoho'
   ```

2. Inside the `zohoImportsApi` object, insert this method directly above `getAdmin`:
   ```ts
     create(payload: ZohoUserCreateRequest): Promise<ZohoImportRow> {
       return api.post<ZohoImportRow>(BASE, payload)
     },
   ```

- [ ] **Step 2: Re-run the spec and verify it passes**

Run: `cd apps-microservices/mcp-gateway-frontend && npx vitest run src/api/zohoImports.spec.ts`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/api/zohoImports.ts apps-microservices/mcp-gateway-frontend/src/api/zohoImports.spec.ts
git commit -m "feat(mcp-gateway-frontend): add zohoImportsApi.create"
```

---

## Task 9: Frontend — add the failing store spec for `createUserImport`

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/stores/zohoImports.spec.ts`

- [ ] **Step 1: Inspect existing tests**

Read the existing spec — note how it mocks `zohoImportsApi.list`, `upsertAdmin`, etc. Use the same approach.

- [ ] **Step 2: Add the test**

Append:

```ts
describe('zohoImportsStore.createUserImport', () => {
  it('prepends the new row and increments usersTotal', async () => {
    setActivePinia(createPinia())
    const store = useZohoImportsStore()
    store.$patch({ users: [], usersTotal: 0 })

    const row = {
      id: 'r-1',
      name: 'Alice',
      url: 'https://alice.example.com',
      is_admin: false,
      is_active: true,
      created_by: 'alice@hp.fr',
      template_slug: 'zoho',
      auth_header_keys: [],
      created_at: '2026-05-15T00:00:00Z',
      updated_at: '2026-05-15T00:00:00Z',
    }
    vi.spyOn(zohoImportsApi, 'create').mockResolvedValueOnce(row)

    const result = await store.createUserImport({
      name: 'Alice',
      url: 'https://alice.example.com',
      created_by: 'alice@hp.fr',
    })

    expect(result).toEqual(row)
    expect(store.users).toEqual([row])
    expect(store.usersTotal).toBe(1)
  })
})
```

- [ ] **Step 3: Run the spec and verify it fails**

Run: `cd apps-microservices/mcp-gateway-frontend && npx vitest run src/stores/zohoImports.spec.ts`
Expected: FAIL — `store.createUserImport is not a function`.

---

## Task 10: Frontend — implement `createUserImport` store action

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/stores/zohoImports.ts`

- [ ] **Step 1: Extend the type import**

In `apps-microservices/mcp-gateway-frontend/src/stores/zohoImports.ts`, replace the type import block at the top with:

```ts
import type {
  ZohoImportRow,
  ZohoImportUpdateRequest,
  ZohoImportTestResponse,
  ZohoAdminUpsertRequest,
  ZohoUserCreateRequest,
} from '@/types/zoho'
```

- [ ] **Step 2: Add the action**

Inside the `actions` block, insert (just below `upsertAdmin`):

```ts
    async createUserImport(payload: ZohoUserCreateRequest): Promise<ZohoImportRow> {
      const row = await zohoImportsApi.create(payload)
      this.users = [row, ...this.users]
      this.usersTotal += 1
      return row
    },
```

- [ ] **Step 3: Re-run the spec and verify it passes**

Run: `cd apps-microservices/mcp-gateway-frontend && npx vitest run src/stores/zohoImports.spec.ts`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/stores/zohoImports.ts apps-microservices/mcp-gateway-frontend/src/stores/zohoImports.spec.ts
git commit -m "feat(mcp-gateway-frontend): add zohoImports store createUserImport action"
```

---

## Task 11: Frontend — register the new route

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/router/index.ts`

- [ ] **Step 1: Add the route entry**

In `apps-microservices/mcp-gateway-frontend/src/router/index.ts`, insert this route immediately **above** the `template-detail` route (currently at the `path: '/admin/templates/:slug'` entry near line 170):

```ts
    {
      path: '/admin/templates/:slug/zoho-imports/new',
      name: 'zoho-import-new',
      component: () => import('@/views/ZohoImportFormView.vue'),
      meta: { requiresAuth: true, title: 'Nouvel import Zoho', minRole: 'admin' },
      props: true,
    },
```

(Place it before `template-detail` so the more specific path is matched first.)

- [ ] **Step 2: Verify the route file compiles**

Run: `cd apps-microservices/mcp-gateway-frontend && npx vue-tsc --noEmit`
Expected: exit 0. (`ZohoImportFormView.vue` does not yet exist — Vue Router's lazy `() => import(...)` only resolves at navigation time, so TypeScript will not flag the missing file. If you get a TS error here, fix it before continuing.)

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/router/index.ts
git commit -m "feat(mcp-gateway-frontend): add zoho-import-new route"
```

---

## Task 12: Frontend — create `ZohoImportFormView.vue`

**Files:**
- Create: `apps-microservices/mcp-gateway-frontend/src/views/ZohoImportFormView.vue`

- [ ] **Step 1: Create the file**

Create `apps-microservices/mcp-gateway-frontend/src/views/ZohoImportFormView.vue` with the following content:

```vue
<template>
  <div>
    <div class="mb-6 flex items-center gap-4">
      <BaseButton variant="ghost" size="sm" @click="goBack">
        <i class="pi pi-arrow-left text-xs mr-1" />
        Retour
      </BaseButton>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ pageTitle }}
      </h1>
    </div>

    <div class="max-w-3xl mx-auto">
      <StepTabs
        :steps="stepLabels"
        :current-step="currentStep"
        :completed-steps="completedSteps"
        @update:current-step="goToStep"
      />

      <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-6">
        <!-- Step 0: Identité -->
        <div v-show="currentStep === 0" class="space-y-4">
          <div
            v-if="scope === 'admin' && hasExistingAdmin"
            class="rounded-md bg-warning-50 dark:bg-warning-500/15 px-3 py-2 text-xs text-warning-700 dark:text-warning-400"
          >
            Un compte admin existe déjà — la création remplacera la configuration actuelle.
          </div>

          <FormField label="Nom" required>
            <template #default="{ id }">
              <BaseInput :id="id" v-model="form.name" placeholder="ex: Compte admin Zoho" />
            </template>
          </FormField>

          <FormField v-if="scope === 'users'" label="Créé par (email)" required>
            <template #default="{ id }">
              <BaseInput :id="id" v-model="form.created_by" type="email" placeholder="user@hellopro.fr" />
            </template>
          </FormField>
        </div>

        <!-- Step 1: Endpoint -->
        <div v-show="currentStep === 1" class="space-y-4">
          <FormField label="URL upstream" required>
            <template #default="{ id }">
              <BaseInput :id="id" v-model="form.url" type="url" placeholder="https://mcp-zoho.example.com" />
            </template>
          </FormField>

          <FormField label="Auth headers (JSON)" :error="authHeadersError">
            <template #default="{ id }">
              <BaseTextarea
                :id="id"
                v-model="form.authHeadersJson"
                :rows="4"
                monospace
                placeholder='{"Authorization": "Bearer xxx"}'
              />
            </template>
          </FormField>

          <div v-if="scope === 'users'" class="flex items-center gap-2">
            <input
              id="zoho-form-active"
              v-model="form.is_active"
              type="checkbox"
              class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
            />
            <label for="zoho-form-active" class="text-sm text-gray-700 dark:text-gray-300">
              Import actif
            </label>
          </div>
        </div>

        <!-- Step 2: Récapitulatif -->
        <div v-show="currentStep === 2" class="space-y-4">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Récapitulatif</h3>
          <dl class="divide-y divide-gray-100 dark:divide-gray-800">
            <div class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Type</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2">
                {{ scope === 'admin' ? 'Compte admin (singleton)' : 'Import utilisateur' }}
              </dd>
            </div>
            <div class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Nom</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.name }}</dd>
            </div>
            <div v-if="scope === 'users'" class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Créé par</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.created_by }}</dd>
            </div>
            <div class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">URL</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2 break-all">{{ form.url }}</dd>
            </div>
            <div v-if="authHeaderKeys.length" class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">En-têtes auth</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2 font-mono text-xs">
                <span v-for="k in authHeaderKeys" :key="k" class="mr-2">{{ k }}</span>
              </dd>
            </div>
            <div v-if="scope === 'users'" class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Actif</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.is_active ? 'Oui' : 'Non' }}</dd>
            </div>
          </dl>
        </div>
      </div>

      <div class="flex justify-between mt-6">
        <BaseButton v-if="currentStep > 0" variant="secondary" @click="currentStep--">Précédent</BaseButton>
        <div v-else />
        <div class="flex gap-3">
          <BaseButton variant="secondary" @click="goBack">Annuler</BaseButton>
          <BaseButton v-if="currentStep < 2" :disabled="!canGoNext" @click="goNext">Suivant</BaseButton>
          <BaseButton v-if="currentStep === 2" :loading="submitting" @click="handleSubmit">Créer</BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useZohoImportsStore } from '@/stores/zohoImports'
import { useToast } from '@/composables/useToast'
import StepTabs from '@/components/shared/StepTabs.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import BaseTextarea from '@/components/ui/BaseTextarea.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import FormField from '@/components/ui/FormField.vue'
import { toErrorMessage } from '@/utils/error'

const props = defineProps<{ slug: string }>()

const route = useRoute()
const router = useRouter()
const store = useZohoImportsStore()
const toast = useToast()

const stepLabels = ['Identité', 'Endpoint', 'Récapitulatif']
const currentStep = ref(0)
const submitting = ref(false)
const authHeadersError = ref('')

const scope = computed<'admin' | 'users'>(() => {
  const q = route.query.scope
  return q === 'admin' ? 'admin' : 'users'
})

const pageTitle = computed(() =>
  scope.value === 'admin' ? 'Nouveau compte admin Zoho' : 'Nouvel import Zoho'
)

const hasExistingAdmin = computed(() => store.admin !== null)

const form = reactive({
  name: '',
  url: '',
  authHeadersJson: '',
  created_by: '',
  is_active: true,
})

const authHeaderKeys = computed<string[]>(() => {
  if (!form.authHeadersJson.trim()) return []
  try {
    const parsed = JSON.parse(form.authHeadersJson)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return Object.keys(parsed)
    }
  } catch {
    return []
  }
  return []
})

const isStep0Valid = computed(() => {
  if (!form.name.trim()) return false
  if (scope.value === 'users') {
    if (!form.created_by.trim() || !form.created_by.includes('@')) return false
  }
  return true
})

const isStep1Valid = computed(() => {
  if (!form.url.trim()) return false
  if (form.authHeadersJson.trim()) {
    try {
      const parsed = JSON.parse(form.authHeadersJson)
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        authHeadersError.value = 'Doit être un objet JSON {"clé":"valeur"}.'
        return false
      }
    } catch {
      authHeadersError.value = 'JSON invalide.'
      return false
    }
  }
  authHeadersError.value = ''
  return true
})

const canGoNext = computed(() => {
  if (currentStep.value === 0) return isStep0Valid.value
  if (currentStep.value === 1) return isStep1Valid.value
  return false
})

const completedSteps = computed(() => {
  const out: number[] = []
  if (isStep0Valid.value) out.push(0)
  if (isStep0Valid.value && isStep1Valid.value) out.push(1)
  return out
})

onMounted(() => {
  if (scope.value === 'admin' && !store.admin) {
    store.fetchAdmin()
  }
})

function goToStep(step: number) {
  if (step < currentStep.value || completedSteps.value.includes(step)) {
    currentStep.value = step
  }
}

function goNext() {
  if (canGoNext.value && currentStep.value < 2) currentStep.value++
}

function goBack() {
  router.push({ name: 'template-detail', params: { slug: props.slug } })
}

function parseAuthHeaders(): Record<string, string> | undefined {
  const raw = form.authHeadersJson.trim()
  if (!raw) return undefined
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, string>
    }
    authHeadersError.value = 'Doit être un objet JSON {"clé":"valeur"}.'
    return undefined
  } catch {
    authHeadersError.value = 'JSON invalide.'
    return undefined
  }
}

async function handleSubmit() {
  submitting.value = true
  try {
    const authHeaders = parseAuthHeaders()
    if (authHeadersError.value) return

    if (scope.value === 'admin') {
      await store.upsertAdmin({
        name: form.name.trim(),
        url: form.url.trim(),
        auth_headers: authHeaders,
      })
    } else {
      await store.createUserImport({
        name: form.name.trim(),
        url: form.url.trim(),
        created_by: form.created_by.trim(),
        auth_headers: authHeaders,
        is_active: form.is_active,
        template_slug: props.slug,
      })
    }
    toast.success(scope.value === 'admin' ? 'Compte admin créé' : 'Import créé')
    router.push({
      name: 'template-detail',
      params: { slug: props.slug },
      query: { zoho_tab: scope.value },
    })
  } catch (err) {
    toast.error(toErrorMessage(err, "Erreur lors de la création"))
  } finally {
    submitting.value = false
  }
}
</script>
```

- [ ] **Step 2: Typecheck + lint**

Run: `cd apps-microservices/mcp-gateway-frontend && npx vue-tsc --noEmit && npx eslint src/views/ZohoImportFormView.vue`
Expected: exit 0 on both.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/views/ZohoImportFormView.vue
git commit -m "feat(mcp-gateway-frontend): add ZohoImportFormView"
```

---

## Task 13: Frontend — wire the `+ Ajouter` button + tab pre-selection in `ZohoImportsSection`

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoImportsSection.vue`

- [ ] **Step 1: Add the imports + route**

In `apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoImportsSection.vue`, add the `useRoute` import at the top of the `<script setup>` block (alongside `useRouter`):

```ts
import { useRouter, useRoute } from 'vue-router'
```

Then add inside the `setup` body:

```ts
const route = useRoute()
```

- [ ] **Step 2: Replace the header `<template #actions>` slot**

Replace the existing `<template #actions>` block in the file with:

```vue
      <template #actions>
        <button
          class="px-3 py-1.5 text-sm rounded-md text-white bg-brand-500 hover:bg-brand-600"
          @click="goToAdd"
        >
          + Ajouter
        </button>
        <button
          class="px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5"
          @click="goToImport"
        >
          Importer depuis Sheets
        </button>
      </template>
```

- [ ] **Step 3: Add the `goToAdd` function**

In the same `<script setup>`, add directly below `goToImport`:

```ts
function goToAdd() {
  router.push({
    name: 'zoho-import-new',
    params: { slug: props.templateSlug },
    query: { scope: activeTab.value },
  })
}
```

- [ ] **Step 4: Pre-select the tab from the route query**

Replace the existing `onMounted` block with:

```ts
onMounted(() => {
  const wanted = route.query.zoho_tab
  if (wanted === 'admin' || wanted === 'users') {
    activeTab.value = wanted
  }
  store.fetchAdmin()
  store.fetchUsers()
})
```

- [ ] **Step 5: Typecheck**

Run: `cd apps-microservices/mcp-gateway-frontend && npx vue-tsc --noEmit`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/src/components/zoho/ZohoImportsSection.vue
git commit -m "feat(mcp-gateway-frontend): add + Ajouter button and tab pre-selection to ZohoImportsSection"
```

---

## Task 14: Frontend — update `mcp-gateway-frontend/CLAUDE.md`

**Files:**
- Modify: `apps-microservices/mcp-gateway-frontend/CLAUDE.md`

- [ ] **Step 1: Add the view + route documentation**

In `apps-microservices/mcp-gateway-frontend/CLAUDE.md`, inside the `src/views/` block of the File Inventory, add a line for `ZohoImportFormView.vue` (next to `TemplateInstanceFormView.vue`).

Then append a new subsection just before "What This Provides to Other Services":

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/mcp-gateway-frontend/CLAUDE.md
git commit -m "docs(mcp-gateway-frontend): document Zoho import Add button + form view"
```

---

## Task 15: Manual smoke + final regression check

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `docker exec gateway-go go test ./...`
Expected: PASS across all packages.

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd apps-microservices/mcp-gateway-frontend && npx vitest run`
Expected: PASS.

- [ ] **Step 3: Start the stack and exercise the UI**

Run: `docker compose up -d mcp-gateway-service mcp-gateway-frontend` (or whatever the project's preferred startup command is).
Then in a browser open `http://localhost:8581/admin/templates/zoho` (or the equivalent dev URL).

Verify each path:
1. Click `+ Ajouter` on the **Admin** tab → form titled "Nouveau compte admin Zoho", no `created_by` field, no `is_active` checkbox, warning banner if an admin row already exists. Fill, submit. Expect toast + Admin tab visible with the updated row.
2. Click `+ Ajouter` on the **Utilisateurs** tab → form titled "Nouvel import Zoho", `created_by` field visible, `is_active` checkbox visible. Fill, submit. Expect toast + new row at the top of the user list.
3. Try the 409 path: submit a second user row with the same `created_by` → toast should show the backend error text.

- [ ] **Step 4: Final commit if any docs were touched**

If a doc tweak surfaced during smoke (typo, missing detail), commit it on its own.

---

## Self-Review (filled in)

**Spec coverage:**
- Goals (button + scope-aware form + mirror fields): Tasks 12, 13.
- New `POST /api/v1/zoho-imports` endpoint: Tasks 1-4.
- DTO `ZohoUserCreateRequest`: Tasks 1, 6.
- Store + api client extensions: Tasks 7-10.
- New route: Task 11.
- CLAUDE.md updates: Tasks 5, 14.
- Tests (5 backend + 1 store + 1 api): Tasks 2, 4, 7, 9.
- Manual smoke: Task 15.
- Out-of-scope items (no drag-reorder, no auto-test post-create, no CLI) are not implemented — matches the spec.

**Placeholder scan:** no TBD/TODO, no "add validation" without code, every code step ships the full block.

**Type consistency:**
- `ZohoUserCreateRequest` shape identical in Go DTO (Task 1) and TS type (Task 6).
- Store action name `createUserImport` consistent in Tasks 9, 10, and the view in Task 12.
- API client method name `create` consistent across Tasks 7, 8, 12.
- Route name `zoho-import-new` consistent across Tasks 11, 13.
- Query param `scope` consistent across Tasks 11, 12, 13.
- Query param `zoho_tab` consistent across Tasks 12, 13.

No gaps found.
