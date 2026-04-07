package repository

import "testing"

func TestNewAuthCodeRepo(t *testing.T) {
	repo := NewAuthCodeRepo(nil)
	if repo == nil {
		t.Fatal("expected non-nil repo")
	}
}
