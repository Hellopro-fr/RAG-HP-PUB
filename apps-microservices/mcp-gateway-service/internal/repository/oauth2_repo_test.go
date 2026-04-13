package repository

import "testing"

func TestNewOAuth2Repo(t *testing.T) {
	repo := NewOAuth2Repo(nil, nil)
	if repo == nil {
		t.Fatal("expected non-nil repo")
	}
}
