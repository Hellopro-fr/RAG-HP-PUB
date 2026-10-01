package zohodiscover

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"mcp-gateway/internal/db"
)

func TestParseToolsListResponse_HappyPath(t *testing.T) {
	body := []byte(`{"result":{"tools":[{"name":"a","description":"d","inputSchema":{"type":"object"}}]}}`)
	tools, err := ParseToolsListResponse(body)
	if err != nil {
		t.Fatalf("ParseToolsListResponse: %v", err)
	}
	if len(tools) != 1 || tools[0].Name != "a" || tools[0].Description != "d" {
		t.Fatalf("unexpected tools: %+v", tools)
	}
	if string(tools[0].InputSchema) == "" || string(tools[0].InputSchema) == "null" {
		t.Fatalf("inputSchema empty/null: %s", string(tools[0].InputSchema))
	}
}

func TestParseToolsListResponse_EmptySchemaDefault(t *testing.T) {
	body := []byte(`{"result":{"tools":[{"name":"a"}]}}`)
	tools, err := ParseToolsListResponse(body)
	if err != nil {
		t.Fatalf("ParseToolsListResponse: %v", err)
	}
	if string(tools[0].InputSchema) != "{}" {
		t.Fatalf("want default '{}', got %q", string(tools[0].InputSchema))
	}
}

func TestParseToolsListResponse_InvalidJSON(t *testing.T) {
	_, err := ParseToolsListResponse([]byte(`not-json`))
	if err == nil {
		t.Fatal("want error on invalid JSON")
	}
}

func TestDecryptAuthHeaders_NoEncryptor_PlaintextJSON(t *testing.T) {
	raw, _ := json.Marshal(map[string]string{"Authorization": "Bearer x"})
	got := DecryptAuthHeaders(nil, raw)
	if got["Authorization"] != "Bearer x" {
		t.Fatalf("want Bearer x, got %+v", got)
	}
}

func TestDecryptAuthHeaders_Empty(t *testing.T) {
	got := DecryptAuthHeaders(nil, nil)
	if len(got) != 0 {
		t.Fatalf("want empty map, got %+v", got)
	}
}

func TestFetchTools_HappyPath(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Custom") != "yes" {
			t.Errorf("missing forwarded header")
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"result":{"tools":[{"name":"tool-1","description":"d","inputSchema":{"type":"object"}}]}}`))
	}))
	defer srv.Close()

	hdrs, _ := json.Marshal(map[string]string{"X-Custom": "yes"})
	row := &db.ZohoImport{URL: srv.URL, AuthHeaders: hdrs}

	tools, err := FetchTools(context.Background(), nil, row)
	if err != nil {
		t.Fatalf("FetchTools: %v", err)
	}
	if len(tools) != 1 || tools[0].Name != "tool-1" {
		t.Fatalf("unexpected tools: %+v", tools)
	}
}

func TestFetchTools_Non2xx(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	defer srv.Close()

	row := &db.ZohoImport{URL: srv.URL}
	if _, err := FetchTools(context.Background(), nil, row); err == nil {
		t.Fatal("want error on 500")
	}
}
