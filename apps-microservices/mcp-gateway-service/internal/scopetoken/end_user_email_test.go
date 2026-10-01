package scopetoken

import (
	"context"
	"testing"
)

func TestEndUserEmailFromContext(t *testing.T) {
	ctx := context.Background()
	if got, ok := EndUserEmailFromContext(ctx); ok || got != "" {
		t.Fatalf("expected empty/false, got (%q,%v)", got, ok)
	}

	ctx = context.WithValue(ctx, EndUserEmailContextKey, "alice@example.com")
	got, ok := EndUserEmailFromContext(ctx)
	if !ok {
		t.Fatal("expected ok=true when key is set")
	}
	if got != "alice@example.com" {
		t.Fatalf("expected alice@example.com, got %q", got)
	}
}

func TestEndUserEmailFromContext_WrongType(t *testing.T) {
	// Non-string value under the key must be reported as missing rather
	// than interpreted via reflection.
	ctx := context.WithValue(context.Background(), EndUserEmailContextKey, 42)
	if got, ok := EndUserEmailFromContext(ctx); ok || got != "" {
		t.Fatalf("expected empty/false for wrong type, got (%q,%v)", got, ok)
	}
}
