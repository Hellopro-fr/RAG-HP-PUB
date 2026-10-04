package acces

import "testing"

// Adresses fictives en .test : le depot est public, aucune adresse reelle
// ne doit apparaitre, y compris dans un test.
func TestAutorise(t *testing.T) {
	cas := []struct {
		nom     string
		email   string
		role    string
		granted bool
		attend  bool
	}{
		{"admin sans grant passe", "dave@example.test", "admin", false, true},
		{"readonly avec grant passe", "alice@example.test", "readonly", true, true},
		{"readonly sans grant refuse", "dave@example.test", "readonly", false, false},
		{"role absent avec grant passe", "alice@example.test", "", true, true},
		{"role absent sans grant refuse", "dave@example.test", "", false, false},
		{"email vide refuse", "", "readonly", false, false},
		{"email vide avec role admin refuse", "", "admin", false, false},
		{"grant sans email refuse", "", "", true, false},
		{"email fait d espaces refuse", "   ", "admin", true, false},
		{"role Admin capitalise n est pas admin", "dave@example.test", "Admin", false, false},
		{"role superadmin n est pas admin", "dave@example.test", "superadmin", false, false},
		{"role avec espaces reste admin", "dave@example.test", " admin ", false, true},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			if got := Autorise(c.email, c.role, c.granted); got != c.attend {
				t.Errorf("Autorise(%q, %q, %v) = %v, attendu %v", c.email, c.role, c.granted, got, c.attend)
			}
		})
	}
}

// Un grant n'ouvre pas les colonnes restreintes : seul l'admin y a droit.
func TestEstAdmin(t *testing.T) {
	if !EstAdmin("admin") {
		t.Error("admin doit etre admin")
	}
	if EstAdmin("readonly") {
		t.Error("readonly ne doit pas etre admin")
	}
}

func TestSource(t *testing.T) {
	if got := Source("admin"); got != "admin" {
		t.Errorf("Source(admin) = %q", got)
	}
	if got := Source("readonly"); got != "grant" {
		t.Errorf("Source(readonly) = %q", got)
	}
}
