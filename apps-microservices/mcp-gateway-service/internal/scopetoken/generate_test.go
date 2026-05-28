package scopetoken

import (
	"strings"
	"testing"
)

func TestTokenPrefix(t *testing.T) {
	if TokenPrefix != "mcp_" {
		t.Fatalf("expected TokenPrefix to be 'mcp_', got %q", TokenPrefix)
	}
}

func TestGenerate(t *testing.T) {
	raw, hash, prefix, err := Generate()
	if err != nil {
		t.Fatalf("Generate failed: %v", err)
	}

	// Validate token format: "mcp_" + 48 hex chars = 52 total
	if len(raw) != 52 {
		t.Fatalf("expected raw token length 52, got %d", len(raw))
	}

	// Validate prefix
	if !strings.HasPrefix(raw, TokenPrefix) {
		t.Fatalf("expected raw token to start with %q, got %q", TokenPrefix, raw[:len(TokenPrefix)])
	}

	// Validate hash is 64 hex chars (SHA-256)
	if len(hash) != 64 {
		t.Fatalf("expected hash length 64, got %d", len(hash))
	}

	// Validate display prefix is first 12 chars of raw
	if prefix != raw[:12] {
		t.Fatalf("expected prefix %q, got %q", raw[:12], prefix)
	}
}

func TestHash(t *testing.T) {
	raw := "mcp_0123456789abcdef0123456789abcdef01234567"
	hash := Hash(raw)

	// SHA-256 produces 64 hex chars
	if len(hash) != 64 {
		t.Fatalf("expected hash length 64, got %d", len(hash))
	}

	// Hashing same input should produce same output (deterministic)
	hash2 := Hash(raw)
	if hash != hash2 {
		t.Fatalf("Hash is non-deterministic: %q vs %q", hash, hash2)
	}
}
