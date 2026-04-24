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
