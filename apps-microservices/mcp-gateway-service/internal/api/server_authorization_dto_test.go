package api

import (
	"encoding/json"
	"testing"
)

// TestCreateServerAuthorizationRequest_JSON verifies that the wire shape is
// stable: snake_case keys, both fields required by the handler.
func TestCreateServerAuthorizationRequest_JSON(t *testing.T) {
	raw := []byte(`{"server_id":"srv-1","email":"alice@example.com"}`)
	var req CreateServerAuthorizationRequest
	if err := json.Unmarshal(raw, &req); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if req.ServerID != "srv-1" {
		t.Errorf("server_id mismatch: got %q", req.ServerID)
	}
	if req.Email != "alice@example.com" {
		t.Errorf("email mismatch: got %q", req.Email)
	}
}

// TestServerAuthorizationResponse_OmitEmptyCreatedBy ensures the optional
// created_by field is omitted from the wire payload when empty (legacy rows
// pre-dating the column tracking).
func TestServerAuthorizationResponse_OmitEmptyCreatedBy(t *testing.T) {
	resp := ServerAuthorizationResponse{
		ServerID:  "srv-1",
		Email:     "alice@example.com",
		CreatedAt: "2026-05-07T12:00:00Z",
	}
	b, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var decoded map[string]interface{}
	if err := json.Unmarshal(b, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if _, present := decoded["created_by"]; present {
		t.Errorf("created_by should be omitted when empty, payload=%s", string(b))
	}
	if decoded["created_at"] != "2026-05-07T12:00:00Z" {
		t.Errorf("created_at should round-trip, got %v", decoded["created_at"])
	}
}

// TestServerAuthorizationResponse_IncludesCreatedBy verifies created_by is
// emitted when set.
func TestServerAuthorizationResponse_IncludesCreatedBy(t *testing.T) {
	resp := ServerAuthorizationResponse{
		ServerID:  "srv-1",
		Email:     "alice@example.com",
		CreatedBy: "admin@example.com",
		CreatedAt: "2026-05-07T12:00:00Z",
	}
	b, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var decoded map[string]interface{}
	if err := json.Unmarshal(b, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if decoded["created_by"] != "admin@example.com" {
		t.Errorf("created_by mismatch, got %v", decoded["created_by"])
	}
}
