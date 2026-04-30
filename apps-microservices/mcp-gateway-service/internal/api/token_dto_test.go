package api

import (
	"encoding/json"
	"testing"
)

// TestCreateTokenRequest_InstructionIDsRoundTrip ensures the new optional
// `instruction_ids` field is preserved through JSON encode/decode.
func TestCreateTokenRequest_InstructionIDsRoundTrip(t *testing.T) {
	src := CreateTokenRequest{
		Name:           "t",
		ServerIDs:      []string{"s1"},
		InstructionIDs: []string{"i1", "i2"},
		MCPCommand:     "npx",
	}
	b, err := json.Marshal(src)
	if err != nil {
		t.Fatal(err)
	}
	var got CreateTokenRequest
	if err := json.Unmarshal(b, &got); err != nil {
		t.Fatal(err)
	}
	if len(got.InstructionIDs) != 2 || got.InstructionIDs[0] != "i1" {
		t.Errorf("instruction_ids lost in round-trip: %+v", got.InstructionIDs)
	}
}

// TestUpdateTokenRequest_InstructionIDsOmittedByDefault verifies that an
// UpdateTokenRequest with no instruction_ids key serialises without the field
// (so partial updates don't accidentally clear links).
func TestUpdateTokenRequest_InstructionIDsOmittedByDefault(t *testing.T) {
	src := UpdateTokenRequest{}
	b, err := json.Marshal(src)
	if err != nil {
		t.Fatal(err)
	}
	if s := string(b); s != "{}" {
		t.Errorf("empty UpdateTokenRequest should serialise as \"{}\" got %q", s)
	}
}

func TestCreateTokenRequestDecodesBDDFilter(t *testing.T) {
	body := `{
		"name": "tok",
		"server_ids": ["srv-1"],
		"mcp_command": "npx",
		"bdd_filter": {"used_table_ids": ["a", "b"]}
	}`
	var req CreateTokenRequest
	if err := json.Unmarshal([]byte(body), &req); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if req.BDDFilter == nil {
		t.Fatalf("expected BDDFilter to be set")
	}
	if got := req.BDDFilter.UsedTableIDs; len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Errorf("unexpected ids: %+v", got)
	}
}

func TestUpdateTokenRequestDecodesBDDFilter(t *testing.T) {
	body := `{"bdd_filter": {"used_table_ids": []}}`
	var req UpdateTokenRequest
	if err := json.Unmarshal([]byte(body), &req); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if req.BDDFilter == nil {
		t.Fatalf("expected BDDFilter to be set even when empty")
	}
	if len(req.BDDFilter.UsedTableIDs) != 0 {
		t.Errorf("expected empty slice, got %+v", req.BDDFilter.UsedTableIDs)
	}
}

func TestTokenResponseEmitsBDDFilter(t *testing.T) {
	resp := TokenResponse{
		ID:        "tok-1",
		BDDFilter: &BDDFilterDTO{UsedTableIDs: []string{"x"}},
	}
	out, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var back map[string]interface{}
	if err := json.Unmarshal(out, &back); err != nil {
		t.Fatalf("unmarshal back: %v", err)
	}
	bf, ok := back["bdd_filter"].(map[string]interface{})
	if !ok {
		t.Fatalf("expected bdd_filter object, got %T", back["bdd_filter"])
	}
	ids, ok := bf["used_table_ids"].([]interface{})
	if !ok || len(ids) != 1 || ids[0] != "x" {
		t.Errorf("unexpected ids: %+v", bf["used_table_ids"])
	}
}

func TestTokenResponseOmitsNilBDDFilter(t *testing.T) {
	resp := TokenResponse{ID: "tok-1"}
	out, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var back map[string]interface{}
	if err := json.Unmarshal(out, &back); err != nil {
		t.Fatalf("unmarshal back: %v", err)
	}
	if _, present := back["bdd_filter"]; present {
		t.Errorf("expected bdd_filter to be omitted when nil")
	}
}
