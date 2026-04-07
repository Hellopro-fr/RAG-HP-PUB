package api

import "testing"

func TestHandlerStructCreation(t *testing.T) {
	h := &Handler{}
	if h.repo != nil {
		t.Error("expected nil repo on zero-value Handler")
	}
}
