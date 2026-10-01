package tests

import (
	"strings"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/auth/password"
)

func TestPassword_HashProducesScryptFormat(t *testing.T) {
	h, err := password.Hash("correct horse battery staple")
	if err != nil {
		t.Fatal(err)
	}
	if !password.LooksLikeScryptHash(h) {
		t.Errorf("not scrypt format: %s", h)
	}
	parts := strings.Split(h, "$")
	if len(parts) != 6 {
		t.Errorf("parts = %d, want 6", len(parts))
	}
}

func TestPassword_VerifyTrueOnRightPassword(t *testing.T) {
	h, _ := password.Hash("hunter2")
	ok, _ := password.Verify("hunter2", h)
	if !ok {
		t.Error("Verify returned false on correct password")
	}
}

func TestPassword_VerifyFalseOnWrongPassword(t *testing.T) {
	h, _ := password.Hash("hunter2")
	ok, _ := password.Verify("hunter3", h)
	if ok {
		t.Error("Verify returned true on wrong password")
	}
}

func TestPassword_DifferentHashesSameInput(t *testing.T) {
	a, _ := password.Hash("same")
	b, _ := password.Hash("same")
	if a == b {
		t.Error("two hashes are equal — random salt missing?")
	}
	okA, _ := password.Verify("same", a)
	okB, _ := password.Verify("same", b)
	if !okA || !okB {
		t.Error("Verify failed on either hash")
	}
}

func TestPassword_VerifyRejectsMalformed(t *testing.T) {
	cases := []string{"", "not-a-hash", "scrypt$bad", "bcrypt$1$2$3$4$5"}
	for _, h := range cases {
		ok, _ := password.Verify("x", h)
		if ok {
			t.Errorf("Verify(x, %q) = true, want false", h)
		}
	}
}

func TestPassword_HashRejectsEmpty(t *testing.T) {
	_, err := password.Hash("")
	if err == nil || !strings.Contains(err.Error(), "non-empty") {
		t.Errorf("Hash(\"\") err = %v, want non-empty error", err)
	}
}

func TestPassword_LooksLikeScryptHash(t *testing.T) {
	cases := []struct {
		in   string
		want bool
	}{
		{"scrypt$1$2$3$4$5", true},
		{"scrypt$1$2$3$4", false},
		{"plain", false},
		{"", false},
	}
	for _, c := range cases {
		if got := password.LooksLikeScryptHash(c.in); got != c.want {
			t.Errorf("LooksLikeScryptHash(%q) = %v, want %v", c.in, got, c.want)
		}
	}
}

func TestPassword_VerifyAcceptsNodeProducedHash(t *testing.T) {
	// Hash de "hunter2" généré par : node -e "import('./src/lib/password.js').then(m => m.hashPassword('hunter2').then(console.log))"
	// REMPLACE la valeur ci-dessous par le hash réel produit par Node (Step 3).
	nodeHash := "<REMPLACE_PAR_HASH_NODE_REEL>"
	if nodeHash == "<REMPLACE_PAR_HASH_NODE_REEL>" {
		t.Skip("Node hash not generated — interop test skipped")
	}
	ok, err := password.Verify("hunter2", nodeHash)
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Error("Verify rejected Node-produced hash — interop broken")
	}
}
