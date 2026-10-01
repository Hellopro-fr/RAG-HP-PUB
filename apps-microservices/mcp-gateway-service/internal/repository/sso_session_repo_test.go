package repository

import "testing"

func TestNewSSOSessionRepo(t *testing.T) {
	repo := NewSSOSessionRepo(nil)
	if repo == nil {
		t.Fatal("expected non-nil repo")
	}
}
