package transport

import (
	"net/http/httptest"
	"testing"
)

// Seule la valeur exacte "true" vaut grant : une valeur approchante posee
// par erreur ou par un tiers ne doit jamais devenir un droit.
func TestIdentiteDepuis_GrantedExactementTrue(t *testing.T) {
	cas := []struct {
		valeur string
		poser  bool
		attend bool
	}{
		{"true", true, true},
		{"TRUE", true, false},
		{"True", true, false},
		{"1", true, false},
		{"yes", true, false},
		{" true", true, false},
		{"", true, false},
		{"", false, false},
	}
	for _, c := range cas {
		r := httptest.NewRequest("POST", "/mcp", nil)
		r.Header.Set("X-End-User-Email", "alice@example.test")
		if c.poser {
			r.Header.Set("X-End-User-Granted", c.valeur)
		}
		if got := IdentiteDepuis(r).Granted; got != c.attend {
			t.Errorf("X-End-User-Granted %q (pose=%v) : Granted = %v, attendu %v", c.valeur, c.poser, got, c.attend)
		}
	}
}

func TestIdentiteDepuis_LitEmailEtRole(t *testing.T) {
	r := httptest.NewRequest("POST", "/mcp", nil)
	r.Header.Set("X-End-User-Email", "alice@example.test")
	r.Header.Set("X-End-User-Role", "readonly")
	id := IdentiteDepuis(r)
	if id.Email != "alice@example.test" || id.Role != "readonly" || id.Granted {
		t.Errorf("identite = %+v", id)
	}
}
