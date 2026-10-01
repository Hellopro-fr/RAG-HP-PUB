package tools

import (
	"encoding/json"
	"testing"
)

func TestExtractEmpowerCallUserID(t *testing.T) {
	// Empower GET /public/empower/call/{uuid} response includes user_id.
	body := json.RawMessage(`{"call_uuid":"550e8400","user_id":42,"transcription":"..."}`)
	if got := extractEmpowerCallUserID(body); got != 42 {
		t.Errorf("extractEmpowerCallUserID = %d, want 42", got)
	}

	// Missing → 0.
	body = json.RawMessage(`{"call_uuid":"550e8400"}`)
	if got := extractEmpowerCallUserID(body); got != 0 {
		t.Errorf("missing user_id should yield 0, got %d", got)
	}
}
