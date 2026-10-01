package authserver

import (
	"strings"
	"testing"
)

func TestGenerateAuthCode_Unique(t *testing.T) {
	seen := map[string]struct{}{}
	for i := 0; i < 100; i++ {
		raw, hash, err := GenerateAuthCode()
		if err != nil {
			t.Fatalf("GenerateAuthCode: %v", err)
		}
		if len(raw) < 32 {
			t.Errorf("raw len=%d", len(raw))
		}
		if len(hash) != 64 {
			t.Errorf("hash len=%d", len(hash))
		}
		if strings.Contains(hash, raw) {
			t.Error("hash should not contain raw")
		}
		if _, dup := seen[raw]; dup {
			t.Fatal("collision in 100 iterations - broken RNG")
		}
		seen[raw] = struct{}{}
	}
}

func TestHashAuthCodeMatchesGenerator(t *testing.T) {
	raw, hash, _ := GenerateAuthCode()
	if got := HashAuthCode(raw); got != hash {
		t.Fatalf("HashAuthCode(%q)=%q want %q", raw, got, hash)
	}
}
