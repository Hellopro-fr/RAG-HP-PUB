package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mcp-gateway/internal/bddcatalog"
)

// newCatalogHandler returns a Handler with the bddCatalog wired to the
// given upstream test server. Pass an empty url+token to leave it nil
// for the 503 path.
func newCatalogHandler(t *testing.T, upstreamURL, token string) *Handler {
	t.Helper()
	h := &Handler{}
	if upstreamURL != "" || token != "" {
		h.bddCatalog = bddcatalog.New(upstreamURL, token)
	}
	return h
}

// TestBDDCatalogDatabases_503WhenNotConfigured exercises the disabled path:
// no client wired -> 503 with the documented error message.
func TestBDDCatalogDatabases_503WhenNotConfigured(t *testing.T) {
	h := newCatalogHandler(t, "", "")
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/catalog/databases", nil)
	rr := httptest.NewRecorder()

	h.handleBDDCatalogDatabases(rr, req)

	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d want=503", rr.Code)
	}
	if !strings.Contains(rr.Body.String(), "BDD_CATALOG_BASE_URL") {
		t.Errorf("body missing config hint: %s", rr.Body.String())
	}
}

// TestBDDCatalogDatabases_503WhenClientUnconfigured covers the case where
// the client struct exists but baseURL/token are empty (Enabled() == false).
func TestBDDCatalogDatabases_503WhenClientUnconfigured(t *testing.T) {
	h := newCatalogHandler(t, "", "tok")
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/catalog/databases", nil)
	rr := httptest.NewRecorder()

	h.handleBDDCatalogDatabases(rr, req)
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d want=503", rr.Code)
	}
}

// TestBDDCatalogDatabases_405OnNonGET enforces the GET-only contract.
func TestBDDCatalogDatabases_405OnNonGET(t *testing.T) {
	h := newCatalogHandler(t, "", "")
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/catalog/databases", nil)
	rr := httptest.NewRecorder()

	h.handleBDDCatalogDatabases(rr, req)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status=%d want=405", rr.Code)
	}
	if rr.Header().Get("Allow") != "GET" {
		t.Errorf("Allow header=%q want=GET", rr.Header().Get("Allow"))
	}
}

// TestBDDCatalogDatabases_HappyPath proxies a real upstream payload back
// in the documented `{"databases":[...]}` envelope.
func TestBDDCatalogDatabases_HappyPath(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/databases" {
			t.Errorf("upstream path=%q", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"databases":[{"id":1,"name":"hellopro"}]}`))
	}))
	defer upstream.Close()

	h := newCatalogHandler(t, upstream.URL, "tok")
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/catalog/databases", nil)
	rr := httptest.NewRecorder()

	h.handleBDDCatalogDatabases(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), `"hellopro"`) {
		t.Errorf("response missing upstream payload: %s", rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), `"databases"`) {
		t.Errorf("response missing envelope key: %s", rr.Body.String())
	}
}

// TestBDDCatalogDatabases_502OnUpstreamError verifies upstream 5xx
// surfaces as 502 with an error message body.
func TestBDDCatalogDatabases_502OnUpstreamError(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer upstream.Close()

	h := newCatalogHandler(t, upstream.URL, "tok")
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/catalog/databases", nil)
	rr := httptest.NewRecorder()

	h.handleBDDCatalogDatabases(rr, req)
	if rr.Code != http.StatusBadGateway {
		t.Fatalf("status=%d want=502", rr.Code)
	}
}

// TestBDDCatalogTables_HappyPath exercises path parsing + search forwarding.
func TestBDDCatalogTables_HappyPath(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/databases/42/tables" {
			t.Errorf("upstream path=%q want=/databases/42/tables", r.URL.Path)
		}
		if got := r.URL.Query().Get("search"); got != "produit" {
			t.Errorf("search=%q want=produit", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tables":[{"id":7,"database_id":42,"table_name":"products"}]}`))
	}))
	defer upstream.Close()

	h := newCatalogHandler(t, upstream.URL, "tok")
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/catalog/databases/42/tables?search=produit", nil)
	rr := httptest.NewRecorder()

	h.handleBDDCatalogTablesAndFields(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), `"products"`) {
		t.Errorf("response missing upstream payload: %s", rr.Body.String())
	}
}

// TestBDDCatalogTables_BadDBID — non-integer db id -> 400.
func TestBDDCatalogTables_BadDBID(t *testing.T) {
	h := newCatalogHandler(t, "http://upstream", "tok")
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/catalog/databases/abc/tables", nil)
	rr := httptest.NewRecorder()

	h.handleBDDCatalogTablesAndFields(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d want=400", rr.Code)
	}
}

// TestBDDCatalogFields_HappyPath exercises the deeper /tables/{tid}/fields path.
func TestBDDCatalogFields_HappyPath(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/databases/1/tables/2/fields" {
			t.Errorf("upstream path=%q", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"fields":[{"id":11,"table_id":2,"field_name":"id"}]}`))
	}))
	defer upstream.Close()

	h := newCatalogHandler(t, upstream.URL, "tok")
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/catalog/databases/1/tables/2/fields", nil)
	rr := httptest.NewRecorder()

	h.handleBDDCatalogTablesAndFields(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	if !strings.Contains(rr.Body.String(), `"fields"`) {
		t.Errorf("response missing fields envelope: %s", rr.Body.String())
	}
}

// TestBDDCatalogFields_BadTableID — non-integer table id -> 400.
func TestBDDCatalogFields_BadTableID(t *testing.T) {
	h := newCatalogHandler(t, "http://upstream", "tok")
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/catalog/databases/1/tables/xyz/fields", nil)
	rr := httptest.NewRecorder()

	h.handleBDDCatalogTablesAndFields(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d want=400", rr.Code)
	}
}

// TestBDDCatalogTables_405OnNonGET — POST to /tables -> 405.
func TestBDDCatalogTables_405OnNonGET(t *testing.T) {
	h := newCatalogHandler(t, "http://upstream", "tok")
	req := httptest.NewRequest(http.MethodPost, "/api/v1/bdd/catalog/databases/1/tables", nil)
	rr := httptest.NewRecorder()

	h.handleBDDCatalogTablesAndFields(rr, req)
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status=%d want=405", rr.Code)
	}
}

// TestBDDCatalogTablesAndFields_503WhenNotConfigured — disabled path on the
// nested handler.
func TestBDDCatalogTablesAndFields_503WhenNotConfigured(t *testing.T) {
	h := newCatalogHandler(t, "", "")
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/catalog/databases/1/tables", nil)
	rr := httptest.NewRecorder()

	h.handleBDDCatalogTablesAndFields(rr, req)
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d want=503", rr.Code)
	}
}

// TestBDDCatalogTablesAndFields_NotFoundShape — malformed sub-path -> 404.
func TestBDDCatalogTablesAndFields_NotFoundShape(t *testing.T) {
	h := newCatalogHandler(t, "http://upstream", "tok")
	req := httptest.NewRequest(http.MethodGet, "/api/v1/bdd/catalog/databases/1/columns", nil)
	rr := httptest.NewRecorder()

	h.handleBDDCatalogTablesAndFields(rr, req)
	if rr.Code != http.StatusNotFound {
		t.Fatalf("status=%d want=404", rr.Code)
	}
}
