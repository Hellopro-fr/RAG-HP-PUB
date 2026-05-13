package api

import (
	"encoding/json"
	"testing"
)

// TestZohoAdminCreateRequest_JSON verifies that the wire shape round-trips
// correctly: snake_case keys, auth_headers omitted when empty.
func TestZohoAdminCreateRequest_JSON(t *testing.T) {
	raw := []byte(`{"name":"Zoho CRM","url":"https://mcp.zoho.eu","auth_headers":{"Authorization":"Bearer tok"}}`)
	var req ZohoAdminCreateRequest
	if err := json.Unmarshal(raw, &req); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if req.Name != "Zoho CRM" {
		t.Errorf("name mismatch: got %q", req.Name)
	}
	if req.URL != "https://mcp.zoho.eu" {
		t.Errorf("url mismatch: got %q", req.URL)
	}
	if req.AuthHeaders["Authorization"] != "Bearer tok" {
		t.Errorf("auth_headers mismatch: got %v", req.AuthHeaders)
	}
}

// TestZohoAdminCreateRequest_OmitEmptyAuthHeaders ensures auth_headers is
// omitted from the serialised payload when nil/empty.
func TestZohoAdminCreateRequest_OmitEmptyAuthHeaders(t *testing.T) {
	req := ZohoAdminCreateRequest{Name: "Z", URL: "https://zoho"}
	b, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var decoded map[string]interface{}
	if err := json.Unmarshal(b, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if _, present := decoded["auth_headers"]; present {
		t.Errorf("auth_headers should be omitted when empty, payload=%s", string(b))
	}
}

// TestZohoAdminResponse_JSON verifies the response wire shape.
func TestZohoAdminResponse_JSON(t *testing.T) {
	resp := ZohoAdminResponse{
		ID:             "abc-123",
		Name:           "Zoho CRM",
		URL:            "https://mcp.zoho.eu",
		IsActive:       true,
		AuthHeaderKeys: []string{"Authorization"},
		CreatedAt:      "2026-05-13T00:00:00Z",
		UpdatedAt:      "2026-05-13T00:00:00Z",
	}
	b, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var decoded map[string]interface{}
	if err := json.Unmarshal(b, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if decoded["id"] != "abc-123" {
		t.Errorf("id mismatch: got %v", decoded["id"])
	}
	if decoded["url"] != "https://mcp.zoho.eu" {
		t.Errorf("url mismatch: got %v", decoded["url"])
	}
	if decoded["is_active"] != true {
		t.Errorf("is_active mismatch: got %v", decoded["is_active"])
	}
	keys, _ := decoded["auth_header_keys"].([]interface{})
	if len(keys) != 1 || keys[0] != "Authorization" {
		t.Errorf("auth_header_keys mismatch: got %v", decoded["auth_header_keys"])
	}
}
