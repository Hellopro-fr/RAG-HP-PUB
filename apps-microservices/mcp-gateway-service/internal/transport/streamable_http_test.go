package transport

import (
	"context"
	"testing"
)

// TestAllowedServersFromContext_Empty confirms the default (no key set) path.
func TestAllowedServersFromContext_Empty(t *testing.T) {
	_, ok := AllowedServersFromContext(context.Background())
	if ok {
		t.Error("expected no allowed servers for empty context")
	}
}
