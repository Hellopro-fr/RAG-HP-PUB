package acces

import "testing"

// Adresses fictives en .test : le depot est public, aucune adresse reelle
// ne doit apparaitre, y compris dans un test.
const liste = "alice@example.test, BOB@Example.TEST ,,carol@example.test"

func TestAutorise(t *testing.T) {
	a := Nouveau(liste)
	cas := []struct {
		nom    string
		email  string
		role   string
		attend bool
	}{
		{"admin hors liste passe", "dave@example.test", "admin", true},
		{"readonly hors liste refuse", "dave@example.test", "readonly", false},
		{"readonly dans la liste passe", "alice@example.test", "readonly", true},
		{"casse et espaces normalises des deux cotes", "  BoB@EXAMPLE.test  ", "readonly", true},
		{"email vide refuse", "", "readonly", false},
		{"email vide avec role admin refuse", "", "admin", false},
		{"role vide hors liste refuse", "dave@example.test", "", false},
		{"role Admin capitalise n est pas admin", "dave@example.test", "Admin", false},
		{"role superadmin n est pas admin", "dave@example.test", "superadmin", false},
		{"role avec espaces reste admin", "dave@example.test", " admin ", true},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			if got := a.Autorise(c.email, c.role); got != c.attend {
				t.Errorf("Autorise(%q, %q) = %v, attendu %v", c.email, c.role, got, c.attend)
			}
		})
	}
}

// Une entree vide dans la liste ne doit pas devenir une cle vide, sinon un
// email vide correspondrait.
func TestEntreeVideIgnoree(t *testing.T) {
	a := Nouveau("alice@example.test,,")
	if len(a.autorises) != 1 {
		t.Errorf("liste = %d entrees, attendu 1", len(a.autorises))
	}
}

// Controle positif de l'absence : sans lui, un bug qui refuserait tout
// ferait passer tous les tests de refus ci-dessus.
func TestListeVide_SeulsLesAdminsPassent(t *testing.T) {
	a := Nouveau("")
	if a.Autorise("alice@example.test", "readonly") {
		t.Error("liste vide: un readonly ne doit pas passer")
	}
	if !a.Autorise("alice@example.test", "admin") {
		t.Error("liste vide: un admin doit toujours passer")
	}
}

// Un receveur nil ne doit jamais autoriser : un cablage oublie au demarrage
// deviendrait sinon une porte ouverte.
func TestReceveurNil_Refuse(t *testing.T) {
	var a *Acces
	if a.Autorise("alice@example.test", "admin") {
		t.Error("un Acces nil ne doit jamais autoriser")
	}
}

func TestEstAdmin(t *testing.T) {
	a := Nouveau("")
	if !a.EstAdmin("admin") {
		t.Error("admin doit etre admin")
	}
	if a.EstAdmin("readonly") {
		t.Error("readonly ne doit pas etre admin")
	}
}
