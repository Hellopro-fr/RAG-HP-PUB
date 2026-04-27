package bddcatalog

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestEnabled verifies the Enabled() guard semantics: both baseURL and
// adminToken must be non-empty for the client to be considered configured.
func TestEnabled(t *testing.T) {
	cases := []struct {
		name      string
		baseURL   string
		token     string
		want      bool
	}{
		{"both empty", "", "", false},
		{"only baseURL", "https://example.com", "", false},
		{"only token", "", "secret", false},
		{"both set", "https://example.com", "secret", true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			c := New(tc.baseURL, tc.token)
			if got := c.Enabled(); got != tc.want {
				t.Fatalf("Enabled()=%v want=%v", got, tc.want)
			}
		})
	}

	// nil receiver must also be safe.
	var nilClient *Client
	if nilClient.Enabled() {
		t.Fatal("nil client should not be Enabled()")
	}
}

// TestListDatabases_Success verifies the path, header, and envelope decoding.
func TestListDatabases_Success(t *testing.T) {
	const wantToken = "fake-tok"

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/databases" {
			t.Errorf("unexpected path: %q", r.URL.Path)
		}
		if got, want := r.Header.Get("Authorization"), "Bearer "+wantToken; got != want {
			t.Errorf("Authorization=%q want=%q", got, want)
		}
		if got := r.Header.Get("Accept"); got != "application/json" {
			t.Errorf("Accept=%q want application/json", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"databases":[{"id":1,"name":"hellopro"},{"id":2,"name":"analytics"}]}`))
	}))
	defer srv.Close()

	c := New(srv.URL, wantToken)
	got, err := c.ListDatabases(context.Background())
	if err != nil {
		t.Fatalf("ListDatabases: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("len=%d want=2", len(got))
	}
	if got[0].ID != 1 || got[0].Name != "hellopro" {
		t.Errorf("got[0]=%+v", got[0])
	}
	if got[1].ID != 2 || got[1].Name != "analytics" {
		t.Errorf("got[1]=%+v", got[1])
	}
}

// TestListTables_Success verifies query string passing for the search filter
// and the tables envelope decoding.
func TestListTables_Success(t *testing.T) {
	const wantToken = "tok"
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/databases/42/tables" {
			t.Errorf("unexpected path: %q", r.URL.Path)
		}
		if got := r.URL.Query().Get("search"); got != "produit" {
			t.Errorf("search=%q want=produit", got)
		}
		if got, want := r.Header.Get("Authorization"), "Bearer "+wantToken; got != want {
			t.Errorf("Authorization=%q want=%q", got, want)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tables":[{"id":7,"database_id":42,"table_name":"products","description":"main","field_count":12}]}`))
	}))
	defer srv.Close()

	c := New(srv.URL, wantToken)
	got, err := c.ListTables(context.Background(), 42, "produit")
	if err != nil {
		t.Fatalf("ListTables: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("len=%d want=1", len(got))
	}
	tbl := got[0]
	if tbl.ID != 7 || tbl.DatabaseID != 42 || tbl.TableName != "products" {
		t.Errorf("table=%+v", tbl)
	}
	if tbl.FieldCount != 12 {
		t.Errorf("FieldCount=%d want=12", tbl.FieldCount)
	}
	if tbl.Description != "main" {
		t.Errorf("Description=%q want=main", tbl.Description)
	}
}

// TestListTables_NoSearch verifies that an empty search string omits the
// query parameter rather than sending search=.
func TestListTables_NoSearch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.RawQuery != "" {
			t.Errorf("expected no query string, got %q", r.URL.RawQuery)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tables":[]}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	got, err := c.ListTables(context.Background(), 1, "")
	if err != nil {
		t.Fatalf("ListTables: %v", err)
	}
	if len(got) != 0 {
		t.Fatalf("len=%d want=0", len(got))
	}
}

// TestListTables_UpstreamError verifies that a 5xx response is wrapped into
// an error containing the status code so callers can log usefully.
func TestListTables_UpstreamError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"error":"boom"}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	_, err := c.ListTables(context.Background(), 1, "")
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "500") {
		t.Errorf("error %q does not mention status 500", err.Error())
	}
}

// TestListFields_Success verifies the fields endpoint path, header, and
// envelope decoding.
func TestListFields_Success(t *testing.T) {
	const wantToken = "tok"
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/databases/42/tables/7/fields" {
			t.Errorf("unexpected path: %q", r.URL.Path)
		}
		if got, want := r.Header.Get("Authorization"), "Bearer "+wantToken; got != want {
			t.Errorf("Authorization=%q want=%q", got, want)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"fields":[
            {"id":100,"table_id":7,"field_name":"id","field_type":"int","is_nullable":false},
            {"id":101,"table_id":7,"field_name":"name","field_type":"varchar(255)","is_nullable":true,"description":"label"}
        ]}`))
	}))
	defer srv.Close()

	c := New(srv.URL, wantToken)
	got, err := c.ListFields(context.Background(), 42, 7)
	if err != nil {
		t.Fatalf("ListFields: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("len=%d want=2", len(got))
	}
	if got[0].FieldName != "id" || got[0].FieldType != "int" || got[0].IsNullable {
		t.Errorf("got[0]=%+v", got[0])
	}
	if got[1].FieldName != "name" || !got[1].IsNullable || got[1].Description != "label" {
		t.Errorf("got[1]=%+v", got[1])
	}
}

// TestListFields_UpstreamError exercises the error path on the fields endpoint.
func TestListFields_UpstreamError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte("upstream gone"))
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	_, err := c.ListFields(context.Background(), 1, 1)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "502") {
		t.Errorf("error %q does not mention status 502", err.Error())
	}
}

// TestListDatabases_BaseURLTrimsTrailingSlash makes sure the constructor
// strips a trailing slash so we don't end up with double slashes in the path.
func TestListDatabases_BaseURLTrimsTrailingSlash(t *testing.T) {
	var seenPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seenPath = r.URL.Path
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"databases":[]}`))
	}))
	defer srv.Close()

	c := New(srv.URL+"/", "tok")
	if _, err := c.ListDatabases(context.Background()); err != nil {
		t.Fatalf("ListDatabases: %v", err)
	}
	if seenPath != "/databases" {
		t.Errorf("path=%q want=/databases (no double slash)", seenPath)
	}
}

// TestList_WrappedEnvelope verifies the production upstream shape
// {"code":200,"response":{"<key>":[...]}} is unwrapped correctly across all
// three list methods. Mirrors the api.hellopro.fr/api/mcp response format.
func TestList_WrappedEnvelope(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/databases":
			_, _ = w.Write([]byte(`{"code":200,"response":{"databases":[{"id":1,"name":"Hellopro BO"}]}}`))
		case "/databases/1/tables":
			_, _ = w.Write([]byte(`{"code":200,"response":{"tables":[{"id":650,"database_id":1,"table_name":"rubrique_2","field_count":72}]}}`))
		case "/databases/1/tables/650/fields":
			_, _ = w.Write([]byte(`{"code":200,"response":{"fields":[{"id":1,"table_id":650,"field_name":"id_rubrique","field_type":"int"}]}}`))
		default:
			t.Errorf("unexpected path: %q", r.URL.Path)
		}
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")

	dbs, err := c.ListDatabases(context.Background())
	if err != nil {
		t.Fatalf("ListDatabases: %v", err)
	}
	if len(dbs) != 1 || dbs[0].Name != "Hellopro BO" {
		t.Errorf("databases=%+v", dbs)
	}

	tables, err := c.ListTables(context.Background(), 1, "")
	if err != nil {
		t.Fatalf("ListTables: %v", err)
	}
	if len(tables) != 1 || tables[0].TableName != "rubrique_2" || tables[0].FieldCount != 72 {
		t.Errorf("tables=%+v", tables)
	}

	fields, err := c.ListFields(context.Background(), 1, 650)
	if err != nil {
		t.Fatalf("ListFields: %v", err)
	}
	if len(fields) != 1 || fields[0].FieldName != "id_rubrique" || fields[0].FieldType != "int" {
		t.Errorf("fields=%+v", fields)
	}
}

// TestList_NullSliceNormalised verifies that empty/null upstream payloads
// surface as empty slices rather than nil — keeps the proxy emitting
// {"tables":[]} instead of {"tables":null} to the frontend.
func TestList_NullSliceNormalised(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"code":200,"response":{"tables":null}}`))
	}))
	defer srv.Close()

	c := New(srv.URL, "tok")
	tables, err := c.ListTables(context.Background(), 1, "")
	if err != nil {
		t.Fatalf("ListTables: %v", err)
	}
	if tables == nil {
		t.Fatal("ListTables returned nil slice; want empty slice")
	}
	if len(tables) != 0 {
		t.Errorf("len=%d want=0", len(tables))
	}
}
