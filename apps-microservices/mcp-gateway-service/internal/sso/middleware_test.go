package sso

import "testing"

// Compile-only smoke test for the middleware constructor wiring.
// Full integration coverage lives in cmd/server end-to-end tests.
func TestNewMiddleware(t *testing.T) {
	mw := NewMiddleware(nil, nil, nil, false)
	if mw == nil {
		t.Fatal("expected non-nil middleware")
	}
}
