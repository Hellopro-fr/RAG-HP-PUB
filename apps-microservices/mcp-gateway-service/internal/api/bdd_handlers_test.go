package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"github.com/hellopro/mcp-gateway/internal/repository"
)

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
