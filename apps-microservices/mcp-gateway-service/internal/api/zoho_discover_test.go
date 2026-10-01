package api

import (
	"encoding/json"
	"testing"
)

func TestParseToolsListResponse_DecodesEnvelope(t *testing.T) {
	body := []byte(`{
		"jsonrpc": "2.0",
		"id": 1,
		"result": {
			"tools": [
				{"name":"crm-search-leads","description":"search","inputSchema":{"type":"object"}},
				{"name":"crm-create-account"}
			]
		}
	}`)
	tools, err := parseToolsListResponse(body)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if len(tools) != 2 {
		t.Fatalf("expected 2 tools, got %d", len(tools))
	}
	if tools[0].Name != "crm-search-leads" {
		t.Fatalf("name = %q", tools[0].Name)
	}
	if tools[0].Description != "search" {
		t.Fatalf("desc = %q", tools[0].Description)
	}
	if string(tools[0].InputSchema) != `{"type":"object"}` {
		t.Fatalf("schema = %q", tools[0].InputSchema)
	}
	if string(tools[1].InputSchema) != `{}` {
		t.Fatalf("missing inputSchema should default to {}, got %q", tools[1].InputSchema)
	}
}

func TestParseToolsListResponse_EmptyTools(t *testing.T) {
	body := []byte(`{"result":{"tools":[]}}`)
	tools, err := parseToolsListResponse(body)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if len(tools) != 0 {
		t.Fatalf("expected 0 tools, got %d", len(tools))
	}
}

func TestParseToolsListResponse_NoResult(t *testing.T) {
	body := []byte(`{"jsonrpc":"2.0","id":1,"error":{"code":-1,"message":"boom"}}`)
	tools, err := parseToolsListResponse(body)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if len(tools) != 0 {
		t.Fatalf("missing result should yield 0 tools, got %d", len(tools))
	}
}

func TestParseToolsListResponse_InvalidJSON(t *testing.T) {
	tools, err := parseToolsListResponse([]byte(`not json`))
	if err == nil {
		t.Fatalf("expected error, got tools=%v", tools)
	}
}

func TestDecryptZohoAuthHeaders_PlaintextFallback(t *testing.T) {
	raw, _ := json.Marshal(map[string]string{"Authorization": "Bearer abc"})
	got := decryptZohoAuthHeaders(nil, raw)
	if got["Authorization"] != "Bearer abc" {
		t.Fatalf("plaintext fallback failed: %v", got)
	}
}

func TestDecryptZohoAuthHeaders_EmptyInput(t *testing.T) {
	got := decryptZohoAuthHeaders(nil, nil)
	if got == nil {
		t.Fatalf("expected non-nil empty map")
	}
	if len(got) != 0 {
		t.Fatalf("expected empty map, got %v", got)
	}
}
