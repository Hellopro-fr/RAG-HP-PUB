package routing

import "testing"

func TestMatchesUserEmail(t *testing.T) {
	cases := []struct {
		name            string
		serverCreatedBy string
		endUserEmail    string
		endUserLogin    string
		want            bool
	}{
		{"exact email", "alice@hp.fr", "alice@hp.fr", "alice", true},
		{"exact email case-insensitive", "ALICE@HP.FR", "alice@hp.fr", "alice", true},
		{"login portion across domains", "alice@hp.fr", "alice@hellopro.fr", "alice", true},
		{"login portion only", "alice@hp.fr", "", "alice", true},
		{"different login no match", "alice@hp.fr", "bob@hp.fr", "bob", false},
		{"empty created_by always false", "", "alice@hp.fr", "alice", false},
		{"empty inputs always false", "alice@hp.fr", "", "", false},
		{"malformed created_by (no local-part) never matches", "@hp.fr", "alice@hp.fr", "alice", false},
		{"login-only fallback when email empty and logins match", "alice@hp.fr", "", "alice", true},
		{"email match wins over login fallback", "alice@hp.fr", "alice@hp.fr", "irrelevant", true},
		{"bare-login created_by matches login", "alice", "alice@hp.fr", "alice", true},
		{"bare-login created_by matches email local-part", "alice", "alice@hp.fr", "", true},
		{"bare-login created_by mismatch", "bob", "alice@hp.fr", "alice", false},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := matchesUserEmail(tc.serverCreatedBy, tc.endUserEmail, tc.endUserLogin)
			if got != tc.want {
				t.Fatalf("matchesUserEmail(%q, %q, %q) = %v, want %v",
					tc.serverCreatedBy, tc.endUserEmail, tc.endUserLogin, got, tc.want)
			}
		})
	}
}
