package repository

import "testing"

func TestNewRefreshRepo(t *testing.T) {
	repo := NewRefreshRepo(nil)
	if repo == nil {
		t.Fatal("expected non-nil repo")
	}
}
