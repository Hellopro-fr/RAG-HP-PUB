package tools

import (
	"testing"
)

// handleGetCalls, handleListCallsByDate, handleSearchCalls and
// handleGetCallDetails touch the Ringover HTTP client, so full integration
// testing lives in scope_test.go (helpers) and in the docker compose
// integration checks. This file pins the smaller pure-logic helpers used by
// the handlers.

func TestCallTypeForPostCalls(t *testing.T) {
	if got := callTypeForPostCalls(""); got != nil {
		t.Errorf("empty should yield nil, got %v", got)
	}
	got := callTypeForPostCalls("ANSWERED")
	if len(got) != 1 || got[0] != "ANSWERED" {
		t.Errorf("unexpected: %v", got)
	}
}
