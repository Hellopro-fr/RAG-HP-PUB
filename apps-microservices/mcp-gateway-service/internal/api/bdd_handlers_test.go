package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	oauth2pkg "github.com/hellopro/mcp-gateway/internal/oauth2"
	"github.com/hellopro/mcp-gateway/internal/repository"
)

// stubTokenCache implements api.TokenCache and records InvalidateAll calls
// so tests can assert the BDD delete handler triggers cache invalidation.
type stubTokenCache struct {
	calls int
}

func (s *stubTokenCache) InvalidateAll() { s.calls++ }

// setupBDDTestRepo wires an in-memory SQLite-backed BDDUsedRepo. Mirrors
// the DDL used by repository/bdd_used_repo_test.go because GORM's
// AutoMigrate trips on the MySQL-only datetime(3) tags.
func setupBDDTestRepo(t *testing.T) *repository.BDDUsedRepo {
	t.Helper()
	dsn := "file:" + t.Name() + "?mode=memory&cache=private&_foreign_keys=on"
	g, err := gorm.Open(sqlite.Open(dsn), &gorm.Config{
		Logger:               logger.Default.LogMode(logger.Silent),
		DisableAutomaticPing: true,
	})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := g.Exec("PRAGMA foreign_keys = ON").Error; err != nil {
		t.Fatalf("enable foreign keys: %v", err)
	}
	stmts := []string{
		`CREATE TABLE bdd_used_tables (
            id TEXT PRIMARY KEY,
            database_id INTEGER NOT NULL,
            table_name TEXT NOT NULL,
            upstream_table_id INTEGER,
            description TEXT,
            created_by TEXT NOT NULL DEFAULT '',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (database_id, table_name)
        )`,
		`CREATE TABLE bdd_used_fields (
            id TEXT PRIMARY KEY,
            used_table_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            upstream_field_id INTEGER,
            description TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (used_table_id, field_name),
            FOREIGN KEY (used_table_id) REFERENCES bdd_used_tables(id) ON DELETE CASCADE
        )`,
		// DeleteTable now clears the scope-token / OAuth2-client join tables
		// in the same transaction (no GORM-level FK cascade is declared on the
		// models). These tables must exist for the delete path to succeed.
		`CREATE TABLE scope_token_bdd_tables (
            token_id TEXT NOT NULL,
            used_table_id TEXT NOT NULL,
            PRIMARY KEY (token_id, used_table_id)
        )`,
		`CREATE TABLE oauth2_client_bdd_tables (
            client_id TEXT NOT NULL,
            used_table_id TEXT NOT NULL,
            PRIMARY KEY (client_id, used_table_id)
        )`,
	}
	for _, s := range stmts {
		if err := g.Exec(s).Error; err != nil {
			t.Fatalf("ddl: %v", err)
		}
	}
	t.Cleanup(func() {
		sqlDB, err := g.DB()
		if err == nil {
			_ = sqlDB.Close()
		}
	})
	return repository.NewBDDUsedRepo(g)
}

// newBDDTestHandler returns a Handler with the BDD repo wired and nothing else.
func newBDDTestHandler(t *testing.T) *Handler {
	t.Helper()
	repo := setupBDDTestRepo(t)
	h := &Handler{}
	h.SetBDDUsedRepo(repo)
	return h
}

// jsonBody marshals v into a buffered reader for use as request body.
func jsonBody(t *testing.T, v interface{}) *bytes.Buffer {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return bytes.NewBuffer(b)
}

// ── 503 paths ─────────────────────────────────────────────────────────────

func TestBDDUsedTables_503WhenRepoUnconfigured(t *testing.T) {
	h := &Handler{}
	for _, m := range []string{http.MethodGet, http.MethodPost} {
		req := httptest.NewRequest(m, "/api/v1/bdd/used/tables", nil)
		rr := httptest.NewRecorder()
		h.handleBDDUsedTables(rr, req)
		if rr.Code != http.StatusServiceUnavailable {
			t.Errorf("%s status=%d want=503", m, rr.Code)
		}
	}
}

func TestBDDUsedTableByID_503WhenRepoUnconfigured(t *testing.T) {
	h := &Handler{}
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables/abc", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusServiceUnavailable {
		t.Errorf("status=%d want=503", rr.Code)
	}
}

// ── List ──────────────────────────────────────────────────────────────────

func TestBDDUsedTables_GET_EmptyList(t *testing.T) {
	h := newBDDTestHandler(t)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables", nil)
	rr := httptest.NewRecorder()

	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), `"tables":[]`) {
		t.Errorf("expected empty tables array, got %s", rr.Body.String())
	}
}

func TestBDDUsedTables_GET_BadDatabaseIDQuery(t *testing.T) {
	h := newBDDTestHandler(t)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables?database_id=foo", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d want=400", rr.Code)
	}
}

// ── Create ────────────────────────────────────────────────────────────────

func TestBDDUsedTables_POST_HappyPath(t *testing.T) {
	h := newBDDTestHandler(t)
	body := jsonBody(t, map[string]interface{}{
		"database_id": 1,
		"table_name":  "products",
		"description": "main",
		"fields": []map[string]interface{}{
			{"field_name": "id", "description": "pk"},
			{"field_name": "name"},
		},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables", body)
	rr := httptest.NewRecorder()

	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusCreated {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	var got BDDUsedTableDTO
	if err := json.Unmarshal(rr.Body.Bytes(), &got); err != nil {
		t.Fatalf("unmarshal: %v body=%s", err, rr.Body.String())
	}
	if got.TableName != "products" {
		t.Errorf("TableName=%q want=products", got.TableName)
	}
	if got.DatabaseID != 1 {
		t.Errorf("DatabaseID=%d want=1", got.DatabaseID)
	}
	if len(got.Fields) != 2 {
		t.Errorf("len(Fields)=%d want=2", len(got.Fields))
	}
	if got.ID == "" {
		t.Errorf("ID is empty")
	}
}

func TestBDDUsedTables_POST_RejectsBadDatabaseID(t *testing.T) {
	h := newBDDTestHandler(t)
	body := jsonBody(t, map[string]interface{}{
		"database_id": 99,
		"table_name":  "products",
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables", body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}

func TestBDDUsedTables_POST_RejectsBadTableName(t *testing.T) {
	h := newBDDTestHandler(t)
	body := jsonBody(t, map[string]interface{}{
		"database_id": 1,
		"table_name":  "with space",
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables", body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}

func TestBDDUsedTables_POST_RejectsBadFieldName(t *testing.T) {
	h := newBDDTestHandler(t)
	body := jsonBody(t, map[string]interface{}{
		"database_id": 1,
		"table_name":  "products",
		"fields": []map[string]interface{}{
			{"field_name": "bad name"},
		},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables", body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}

func TestBDDUsedTables_POST_BadJSON(t *testing.T) {
	h := newBDDTestHandler(t)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables", strings.NewReader("not-json"))
	rr := httptest.NewRecorder()
	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d want=400", rr.Code)
	}
}

func TestBDDUsedTables_POST_DuplicateTableConflict(t *testing.T) {
	h := newBDDTestHandler(t)
	makeReq := func() *httptest.ResponseRecorder {
		body := jsonBody(t, map[string]interface{}{
			"database_id": 1,
			"table_name":  "products",
		})
		req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables", body)
		rr := httptest.NewRecorder()
		h.handleBDDUsedTables(rr, req)
		return rr
	}
	if rr := makeReq(); rr.Code != http.StatusCreated {
		t.Fatalf("first create: status=%d body=%s", rr.Code, rr.Body.String())
	}
	rr := makeReq()
	if rr.Code != http.StatusConflict {
		t.Fatalf("duplicate create: status=%d want=409 body=%s", rr.Code, rr.Body.String())
	}
}

func TestBDDUsedTables_405OnPut(t *testing.T) {
	h := newBDDTestHandler(t)
	req := httptest.NewRequest(http.MethodPut, "/api/v1/bdd/used/tables", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status=%d want=405", rr.Code)
	}
}

// ── Get / Patch / Delete by id ────────────────────────────────────────────

// createSampleTable seeds a single table+field via the public handler chain so
// follow-up tests can target a real ID.
func createSampleTable(t *testing.T, h *Handler) BDDUsedTableDTO {
	t.Helper()
	body := jsonBody(t, map[string]interface{}{
		"database_id": 1,
		"table_name":  "products",
		"description": "main",
		"fields":      []map[string]interface{}{{"field_name": "id"}},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables", body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusCreated {
		t.Fatalf("seed: status=%d body=%s", rr.Code, rr.Body.String())
	}
	var got BDDUsedTableDTO
	if err := json.Unmarshal(rr.Body.Bytes(), &got); err != nil {
		t.Fatalf("seed unmarshal: %v", err)
	}
	return got
}

func TestBDDUsedTableByID_GET_HappyPath(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables/"+seed.ID, nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	var got BDDUsedTableDTO
	if err := json.Unmarshal(rr.Body.Bytes(), &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if got.ID != seed.ID || got.TableName != "products" {
		t.Errorf("got=%+v", got)
	}
}

func TestBDDUsedTableByID_GET_NotFound(t *testing.T) {
	h := newBDDTestHandler(t)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables/missing", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusNotFound {
		t.Fatalf("status=%d want=404", rr.Code)
	}
}

func TestBDDUsedTableByID_PATCH_UpdatesDescription(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)

	body := jsonBody(t, map[string]string{"description": "updated"})
	req := httptest.NewRequest(http.MethodPatch, "/api/v1/bdd/used/tables/"+seed.ID, body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	var got BDDUsedTableDTO
	_ = json.Unmarshal(rr.Body.Bytes(), &got)
	if got.Description != "updated" {
		t.Errorf("Description=%q want=updated", got.Description)
	}
}

func TestBDDUsedTableByID_PATCH_NotFound(t *testing.T) {
	h := newBDDTestHandler(t)
	body := jsonBody(t, map[string]string{"description": "x"})
	req := httptest.NewRequest(http.MethodPatch, "/api/v1/bdd/used/tables/missing", body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusNotFound {
		t.Fatalf("status=%d want=404", rr.Code)
	}
}

func TestBDDUsedTableByID_DELETE_HappyPath(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/bdd/used/tables/"+seed.ID, nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusNoContent {
		t.Fatalf("status=%d want=204 body=%s", rr.Code, rr.Body.String())
	}

	// follow-up GET must 404 — confirms the row was actually removed.
	req = httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables/"+seed.ID, nil)
	rr = httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusNotFound {
		t.Fatalf("post-delete GET status=%d want=404", rr.Code)
	}
}

func TestBDDUsedTableByID_DELETE_NotFound(t *testing.T) {
	h := newBDDTestHandler(t)
	req := httptest.NewRequest(http.MethodDelete, "/api/v1/bdd/used/tables/missing", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusNotFound {
		t.Fatalf("status=%d want=404", rr.Code)
	}
}

func TestBDDUsedTableByID_405UnsupportedMethod(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables/"+seed.ID, nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status=%d want=405", rr.Code)
	}
}

// ── Field add / patch / delete ────────────────────────────────────────────

func TestBDDUsedTableFields_POST_HappyPath(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)

	body := jsonBody(t, map[string]interface{}{
		"field_name":  "price",
		"description": "unit price",
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables/"+seed.ID+"/fields", body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusCreated {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	var got BDDFieldDTO
	if err := json.Unmarshal(rr.Body.Bytes(), &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if got.FieldName != "price" || got.UsedTableID != seed.ID {
		t.Errorf("got=%+v", got)
	}
}

func TestBDDUsedTableFields_POST_BadFieldName(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)
	body := jsonBody(t, map[string]string{"field_name": "bad name"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables/"+seed.ID+"/fields", body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d want=400", rr.Code)
	}
}

func TestBDDUsedTableFields_POST_DuplicateConflict(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h) // already has field "id"

	body := jsonBody(t, map[string]string{"field_name": "id"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables/"+seed.ID+"/fields", body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusConflict {
		t.Fatalf("status=%d want=409 body=%s", rr.Code, rr.Body.String())
	}
}

func TestBDDUsedTableFields_POST_ParentMissing(t *testing.T) {
	h := newBDDTestHandler(t)
	body := jsonBody(t, map[string]string{"field_name": "price"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables/missing/fields", body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusNotFound {
		t.Fatalf("status=%d want=404", rr.Code)
	}
}

func TestBDDUsedTableFields_405OnGet(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables/"+seed.ID+"/fields", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status=%d want=405", rr.Code)
	}
}

func TestBDDUsedTableFieldByID_PATCH_HappyPath(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)
	fieldID := seed.Fields[0].ID

	body := jsonBody(t, map[string]string{"description": "new desc"})
	req := httptest.NewRequest(http.MethodPatch, "/api/v1/bdd/used/tables/"+seed.ID+"/fields/"+fieldID, body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	var got BDDFieldDTO
	if err := json.Unmarshal(rr.Body.Bytes(), &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if got.ID != fieldID || got.FieldName != "id" || got.Description != "new desc" {
		t.Errorf("got=%+v", got)
	}
}

func TestBDDUsedTableFieldByID_PATCH_NotFound(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)

	body := jsonBody(t, map[string]string{"description": "x"})
	req := httptest.NewRequest(http.MethodPatch, "/api/v1/bdd/used/tables/"+seed.ID+"/fields/missing", body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusNotFound {
		t.Fatalf("status=%d want=404", rr.Code)
	}
}

func TestBDDUsedTableFieldByID_DELETE_HappyPath(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)
	fieldID := seed.Fields[0].ID

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/bdd/used/tables/"+seed.ID+"/fields/"+fieldID, nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusNoContent {
		t.Fatalf("status=%d want=204 body=%s", rr.Code, rr.Body.String())
	}

	// re-fetch the parent — the field must be gone.
	req = httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables/"+seed.ID, nil)
	rr = httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	var got BDDUsedTableDTO
	_ = json.Unmarshal(rr.Body.Bytes(), &got)
	if len(got.Fields) != 0 {
		t.Errorf("expected zero fields after delete, got %d", len(got.Fields))
	}
}

func TestBDDUsedTableFieldByID_DELETE_NotFound(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/bdd/used/tables/"+seed.ID+"/fields/missing", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusNotFound {
		t.Fatalf("status=%d want=404", rr.Code)
	}
}

func TestBDDUsedTableFieldByID_405OnGet(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)
	fieldID := seed.Fields[0].ID
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables/"+seed.ID+"/fields/"+fieldID, nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status=%d want=405", rr.Code)
	}
}

// ── List filters ──────────────────────────────────────────────────────────

func TestBDDUsedTables_GET_FiltersByDatabaseID(t *testing.T) {
	h := newBDDTestHandler(t)
	for _, dbID := range []int{1, 5} {
		body := jsonBody(t, map[string]interface{}{
			"database_id": dbID,
			"table_name":  "tbl_" + strings.Repeat("x", dbID),
		})
		req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables", body)
		rr := httptest.NewRecorder()
		h.handleBDDUsedTables(rr, req)
		if rr.Code != http.StatusCreated {
			t.Fatalf("seed db=%d: %d %s", dbID, rr.Code, rr.Body.String())
		}
	}

	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables?database_id=1", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	var resp struct {
		Tables []BDDUsedTableDTO `json:"tables"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if len(resp.Tables) != 1 {
		t.Fatalf("len(tables)=%d want=1", len(resp.Tables))
	}
	if resp.Tables[0].DatabaseID != 1 {
		t.Errorf("DatabaseID=%d want=1", resp.Tables[0].DatabaseID)
	}
}

// ── Cache invalidation on delete ──────────────────────────────────────────

// TestBDDUsedTableByID_DELETE_InvalidatesCaches asserts that deleting a
// BDD used-table flushes both the scope-token cache and the OAuth2 client
// cache. Without that, a cached entry referencing the deleted ID could
// keep emitting it until its TTL expires.
func TestBDDUsedTableByID_DELETE_InvalidatesCaches(t *testing.T) {
	h := newBDDTestHandler(t)
	tokCache := &stubTokenCache{}
	oauthCache := oauth2pkg.NewCache(time.Minute)
	h.tokenCache = tokCache
	h.oauth2Cache = oauthCache

	// Pre-populate the OAuth2 cache so we can observe a flush via Get.
	oauthCache.Set("client-x", &oauth2pkg.CachedClient{ID: "client-x"})
	if _, ok := oauthCache.Get("client-x"); !ok {
		t.Fatalf("seed cache miss")
	}

	seed := createSampleTable(t, h)

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/bdd/used/tables/"+seed.ID, nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusNoContent {
		t.Fatalf("status=%d want=204 body=%s", rr.Code, rr.Body.String())
	}

	if tokCache.calls != 1 {
		t.Errorf("tokenCache.InvalidateAll calls=%d want=1", tokCache.calls)
	}
	if _, ok := oauthCache.Get("client-x"); ok {
		t.Errorf("expected oauth2 cache to be cleared after delete")
	}
}

// TestBDDUsedTableByID_DELETE_NoCacheWired makes sure the delete path
// still works when the handler was wired without caches (e.g. minimal
// test rigs and the unconfigured-deps scenarios).
func TestBDDUsedTableByID_DELETE_NoCacheWired(t *testing.T) {
	h := newBDDTestHandler(t)
	seed := createSampleTable(t, h)

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/bdd/used/tables/"+seed.ID, nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)
	if rr.Code != http.StatusNoContent {
		t.Fatalf("status=%d want=204 body=%s", rr.Code, rr.Body.String())
	}
}

// ── Pagination envelope ──────────────────────────────────────────────────

// TestBDDUsedTablesGET_Paginated asserts the new envelope shape carries
// {tables, total, page, limit} and that defaults (page=1, limit=20)
// apply when no query params are passed.
func TestBDDUsedTablesGET_Paginated(t *testing.T) {
	h := newBDDTestHandler(t)
	for i := 0; i < 3; i++ {
		body := jsonBody(t, map[string]interface{}{
			"database_id": 1,
			"table_name":  "tbl_" + strings.Repeat("a", i+1),
		})
		req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables", body)
		rr := httptest.NewRecorder()
		h.handleBDDUsedTables(rr, req)
		if rr.Code != http.StatusCreated {
			t.Fatalf("seed %d: %d %s", i, rr.Code, rr.Body.String())
		}
	}

	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	var resp BDDUsedListResponse
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal: %v body=%s", err, rr.Body.String())
	}
	if resp.Total != 3 {
		t.Errorf("total=%d want=3", resp.Total)
	}
	if resp.Page != 1 || resp.Limit != 20 {
		t.Errorf("page/limit=%d/%d want=1/20", resp.Page, resp.Limit)
	}
	if len(resp.Tables) != 3 {
		t.Errorf("len(tables)=%d want=3", len(resp.Tables))
	}
}

// TestBDDUsedTablesGET_DefaultDatabaseIDMissing asserts that omitting
// ?database_id returns rows from every database (i.e. the filter is
// inactive when not passed).
func TestBDDUsedTablesGET_DefaultDatabaseIDMissing(t *testing.T) {
	h := newBDDTestHandler(t)
	for _, dbID := range []int{1, 5} {
		body := jsonBody(t, map[string]interface{}{
			"database_id": dbID,
			"table_name":  "tbl_" + strings.Repeat("x", dbID),
		})
		req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables", body)
		rr := httptest.NewRecorder()
		h.handleBDDUsedTables(rr, req)
		if rr.Code != http.StatusCreated {
			t.Fatalf("seed %d: %d %s", dbID, rr.Code, rr.Body.String())
		}
	}

	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	var resp BDDUsedListResponse
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if resp.Total != 2 || len(resp.Tables) != 2 {
		t.Errorf("total=%d len=%d want 2/2", resp.Total, len(resp.Tables))
	}
}

// TestBDDUsedTablesGET_BadPage asserts page=0 is rejected with 400.
func TestBDDUsedTablesGET_BadPage(t *testing.T) {
	h := newBDDTestHandler(t)
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables?page=0", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTables(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d want=400", rr.Code)
	}
}

// ── Bulk create ───────────────────────────────────────────────────────────

// TestBDDUsedBulkCreate_Success: every item is valid and unique →
// 201 Created with the full Created slice and no errors.
func TestBDDUsedBulkCreate_Success(t *testing.T) {
	h := newBDDTestHandler(t)
	body := jsonBody(t, map[string]interface{}{
		"database_id": 1,
		"items": []map[string]interface{}{
			{"table_name": "products"},
			{"table_name": "orders"},
		},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables/bulk", body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedBulkCreate(rr, req)
	if rr.Code != http.StatusCreated {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	var resp BulkCreateBDDUsedTablesResponse
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if len(resp.Created) != 2 || len(resp.Errors) != 0 {
		t.Errorf("created=%d errors=%d want 2/0", len(resp.Created), len(resp.Errors))
	}
}

// TestBDDUsedBulkCreate_PartialErrors mixes a bad name and a duplicate
// against a pre-seeded row. Expected outcome: 200 OK with one created
// row and two error entries (one for the validation failure, one for
// the duplicate).
func TestBDDUsedBulkCreate_PartialErrors(t *testing.T) {
	h := newBDDTestHandler(t)
	// Pre-seed a row so we can trigger ErrBDDDuplicateTable.
	createSampleTable(t, h)

	body := jsonBody(t, map[string]interface{}{
		"database_id": 1,
		"items": []map[string]interface{}{
			{"table_name": "fresh_one"},     // valid + unique → created
			{"table_name": "with space"},    // bad name → error
			{"table_name": "products"},      // duplicate of seed → error
		},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables/bulk", body)
	rr := httptest.NewRecorder()
	h.handleBDDUsedBulkCreate(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	var resp BulkCreateBDDUsedTablesResponse
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if len(resp.Created) != 1 || resp.Created[0].TableName != "fresh_one" {
		t.Errorf("created=%+v want [fresh_one]", resp.Created)
	}
	if len(resp.Errors) != 2 {
		t.Errorf("errors=%d want=2 errs=%+v", len(resp.Errors), resp.Errors)
	}
}

// ── Export ────────────────────────────────────────────────────────────────

// TestBDDUsedExport_AttachmentHeader asserts the Content-Disposition
// header is set for the download flow and the payload carries the
// expected envelope shape.
func TestBDDUsedExport_AttachmentHeader(t *testing.T) {
	h := newBDDTestHandler(t)
	createSampleTable(t, h)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables/export", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedExport(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	if cd := rr.Header().Get("Content-Disposition"); !strings.Contains(cd, "bdd-tables-export.json") {
		t.Errorf("Content-Disposition=%q want includes bdd-tables-export.json", cd)
	}
	if ct := rr.Header().Get("Content-Type"); !strings.Contains(ct, "application/json") {
		t.Errorf("Content-Type=%q want application/json", ct)
	}
	var payload BDDExportPayload
	if err := json.Unmarshal(rr.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal: %v body=%s", err, rr.Body.String())
	}
	if payload.Version != 1 {
		t.Errorf("version=%d want=1", payload.Version)
	}
	if len(payload.Tables) != 1 {
		t.Errorf("len(tables)=%d want=1", len(payload.Tables))
	}
}

// ── Import ────────────────────────────────────────────────────────────────

// TestBDDUsedImport_Upsert exercises the round-trip: export the seeded
// row, re-post the export verbatim, and assert the result is 0 inserted
// and N updated (because the (database_id, table_name) keys already
// exist in the DB).
func TestBDDUsedImport_Upsert(t *testing.T) {
	h := newBDDTestHandler(t)
	createSampleTable(t, h)

	// 1) Export.
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/used/tables/export", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedExport(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("export status=%d body=%s", rr.Code, rr.Body.String())
	}
	exportBody := rr.Body.Bytes()

	// 2) Import the same payload back.
	req = httptest.NewRequest(http.MethodPost, "/api/v1/bdd/used/tables/import", bytes.NewReader(exportBody))
	rr = httptest.NewRecorder()
	h.handleBDDUsedImport(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("import status=%d body=%s", rr.Code, rr.Body.String())
	}
	var resp BDDImportResponse
	if err := json.Unmarshal(rr.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if resp.Inserted != 0 {
		t.Errorf("inserted=%d want=0", resp.Inserted)
	}
	if resp.Updated != 1 {
		t.Errorf("updated=%d want=1", resp.Updated)
	}
	if len(resp.Errors) != 0 {
		t.Errorf("errors=%+v want=[]", resp.Errors)
	}
}
