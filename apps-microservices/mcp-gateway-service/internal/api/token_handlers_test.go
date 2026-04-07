package api

import "testing"

func TestBuildServerToolsResponseEmpty(t *testing.T) {
	result := buildServerToolsResponse(nil)
	if result != nil {
		t.Error("expected nil for empty tools")
	}
}
