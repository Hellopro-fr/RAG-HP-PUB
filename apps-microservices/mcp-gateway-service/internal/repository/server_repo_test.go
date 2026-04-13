package repository

import "testing"

func TestNewServerRepoNilEncryptor(t *testing.T) {
	// Verifies that creating a repo with nil encryptor doesn't panic
	repo := NewServerRepo(nil, nil)
	if repo == nil {
		t.Error("expected non-nil repo")
	}
}
