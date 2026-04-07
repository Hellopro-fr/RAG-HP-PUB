package repository

import "testing"

func TestNewConsentRepo(t *testing.T) {
	repo := NewConsentRepo(nil)
	if repo == nil {
		t.Fatal("expected non-nil repo")
	}
}
