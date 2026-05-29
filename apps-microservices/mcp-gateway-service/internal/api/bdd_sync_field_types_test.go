package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"mcp-gateway/internal/bddcatalog"
	"mcp-gateway/internal/db"
)

// seedSyncTable inserts one registered table (with an upstream link) plus
// the given fields, returning the persisted table ID.
func seedSyncTable(t *testing.T, h *Handler, fields []db.BDDUsedField) string {
	t.Helper()
	tbl := &db.BDDUsedTable{
		DatabaseID:      1,
		Name:            "products",
		UpstreamTableID: 2,
		CreatedBy:       "tester@hellopro.fr",
	}
	created, err := h.bddUsedRepo.CreateTable(context.Background(), tbl, fields)
	if err != nil {
		t.Fatalf("seed CreateTable: %v", err)
	}
	return created.ID
}

// fieldsUpstream returns a test server replying with the documented
// `{"fields":[...]}` envelope for the catalog ListFields call.
func fieldsUpstream(t *testing.T, body string) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/databases/1/tables/2/fields" {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		_, _ = w.Write([]byte(body))
	}))
}

func TestBDDSyncFieldTypes_PerTable_HappyPath(t *testing.T) {
	repo := setupBDDTestRepo(t)
	h := &Handler{}
	h.SetBDDUsedRepo(repo)

	id := seedSyncTable(t, h, []db.BDDUsedField{
		{FieldName: "id", FieldType: ""},
		{FieldName: "name", FieldType: "old"},
	})

	upstream := fieldsUpstream(t,
		`{"fields":[{"field_name":"id","field_type":"int"},{"field_name":"name","field_type":"text"}],"primary":"id"}`)
	defer upstream.Close()
	h.bddCatalog = bddcatalog.New(upstream.URL, "tok")

	req := httptest.NewRequest(http.MethodPost,
		"/api/v1/bdd/used/tables/"+id+"/sync-field-types", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d want=200 body=%s", rr.Code, rr.Body.String())
	}
	var out struct {
		Updated int `json:"updated"`
		Total   int `json:"total"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if out.Updated != 2 || out.Total != 2 {
		t.Fatalf("updated=%d total=%d want updated=2 total=2", out.Updated, out.Total)
	}

	got, _ := repo.GetTable(context.Background(), id)
	for _, f := range got.Fields {
		want := map[string]string{"id": "int", "name": "text"}[f.FieldName]
		if f.FieldType != want {
			t.Errorf("field %q type=%q want=%q", f.FieldName, f.FieldType, want)
		}
	}
}

func TestBDDSyncFieldTypes_PerTable_EnumCollapsedToKeyword(t *testing.T) {
	repo := setupBDDTestRepo(t)
	h := &Handler{}
	h.SetBDDUsedRepo(repo)

	id := seedSyncTable(t, h, []db.BDDUsedField{
		{FieldName: "event_type", FieldType: "", Description: ""},
	})

	// A long enum(...) definition that would overflow field_type varchar(128).
	enumDef := "enum('entered','initial_started','initial_succeeded','initial_failed'," +
		"'became_maj_eligible','maj_triggered','maj_succeeded','maj_failed'," +
		"'domain_deactivated','domain_redirected','webhook_received')"
	upstream := fieldsUpstream(t,
		`{"fields":[{"field_name":"event_type","field_type":"`+enumDef+`"}],"primary":"event_type"}`)
	defer upstream.Close()
	h.bddCatalog = bddcatalog.New(upstream.URL, "tok")

	req := httptest.NewRequest(http.MethodPost,
		"/api/v1/bdd/used/tables/"+id+"/sync-field-types", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d want=200 body=%s", rr.Code, rr.Body.String())
	}

	got, _ := repo.GetTable(context.Background(), id)
	f := got.Fields[0]
	if f.FieldType != "enum" {
		t.Errorf("field_type=%q want=enum", f.FieldType)
	}
	if len(f.FieldType) > 128 {
		t.Errorf("field_type len=%d exceeds column width", len(f.FieldType))
	}
	if f.Description != enumDef {
		t.Errorf("description=%q want full enum def", f.Description)
	}
}

func TestBDDSyncFieldTypes_PerTable_422WhenNoUpstreamLink(t *testing.T) {
	repo := setupBDDTestRepo(t)
	h := &Handler{}
	h.SetBDDUsedRepo(repo)

	tbl := &db.BDDUsedTable{DatabaseID: 1, Name: "orphan", CreatedBy: "t@hellopro.fr"}
	created, err := repo.CreateTable(context.Background(), tbl,
		[]db.BDDUsedField{{FieldName: "id"}})
	if err != nil {
		t.Fatalf("CreateTable: %v", err)
	}
	upstream := fieldsUpstream(t, `{"fields":[]}`)
	defer upstream.Close()
	h.bddCatalog = bddcatalog.New(upstream.URL, "tok")

	req := httptest.NewRequest(http.MethodPost,
		"/api/v1/bdd/used/tables/"+created.ID+"/sync-field-types", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)

	if rr.Code != http.StatusUnprocessableEntity {
		t.Fatalf("status=%d want=422 body=%s", rr.Code, rr.Body.String())
	}
}

func TestBDDSyncFieldTypes_PerTable_503WhenCatalogUnconfigured(t *testing.T) {
	repo := setupBDDTestRepo(t)
	h := &Handler{}
	h.SetBDDUsedRepo(repo)
	id := seedSyncTable(t, h, []db.BDDUsedField{{FieldName: "id"}})

	req := httptest.NewRequest(http.MethodPost,
		"/api/v1/bdd/used/tables/"+id+"/sync-field-types", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedTableByID(rr, req)

	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d want=503 body=%s", rr.Code, rr.Body.String())
	}
}

func TestBDDSyncFieldTypes_All_HappyPath(t *testing.T) {
	repo := setupBDDTestRepo(t)
	h := &Handler{}
	h.SetBDDUsedRepo(repo)
	seedSyncTable(t, h, []db.BDDUsedField{
		{FieldName: "id", FieldType: ""},
		{FieldName: "name", FieldType: "text"}, // already correct -> not counted
	})

	upstream := fieldsUpstream(t,
		`{"fields":[{"field_name":"id","field_type":"int"},{"field_name":"name","field_type":"text"}],"primary":"id"}`)
	defer upstream.Close()
	h.bddCatalog = bddcatalog.New(upstream.URL, "tok")

	req := httptest.NewRequest(http.MethodPost,
		"/api/v1/bdd/used/tables/sync-field-types", nil)
	rr := httptest.NewRecorder()
	h.handleBDDUsedSyncAllFieldTypes(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d want=200 body=%s", rr.Code, rr.Body.String())
	}
	var out struct {
		TablesSynced  int `json:"tables_synced"`
		FieldsUpdated int `json:"fields_updated"`
		Errors        []struct {
			TableName string `json:"table_name"`
			Error     string `json:"error"`
		} `json:"errors"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if out.TablesSynced != 1 || out.FieldsUpdated != 1 || len(out.Errors) != 0 {
		t.Fatalf("tables=%d fields=%d errors=%d want 1/1/0",
			out.TablesSynced, out.FieldsUpdated, len(out.Errors))
	}
}
