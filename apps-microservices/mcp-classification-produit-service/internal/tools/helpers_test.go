package tools

import (
	"regexp"
	"testing"
)

// NOTE: the crypto/rand error path in generateAutoID is not exercised here.
// It is unreachable on Linux (kernel CSPRNG is always available post-boot);
// mocking rand.Read would require DI or a build tag disproportionate to the risk.
func TestGenerateAutoID_FormatAndLength(t *testing.T) {
	got := generateAutoID()
	re := regexp.MustCompile(`^auto-[0-9a-f]{16}$`)
	if !re.MatchString(got) {
		t.Fatalf("expected generated id to match %q, got %q", re.String(), got)
	}
}

func TestGenerateAutoID_Unique(t *testing.T) {
	const n = 1000
	seen := make(map[string]struct{}, n)
	for i := 0; i < n; i++ {
		id := generateAutoID()
		if _, dup := seen[id]; dup {
			t.Fatalf("generateAutoID returned duplicate %q after %d iterations", id, i)
		}
		seen[id] = struct{}{}
	}
}
