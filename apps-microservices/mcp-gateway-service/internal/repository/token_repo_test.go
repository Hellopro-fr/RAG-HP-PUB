package repository

import "testing"

// TestNewTokenRepoNilInputs ensures the constructor doesn't panic when called
// with nil dependencies — e.g. at boot when encryption isn't configured.
func TestNewTokenRepoNilInputs(t *testing.T) {
	repo := NewTokenRepo(nil, nil)
	if repo == nil {
		t.Error("expected non-nil repo")
	}
}
