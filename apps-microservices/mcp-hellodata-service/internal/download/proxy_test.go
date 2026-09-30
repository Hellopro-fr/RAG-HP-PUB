package download

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mcp-hellodata/internal/acces"
)

// tableFake tient lieu de table de jetons pour ces tests : le proxy ne
// connait la vraie table (internal/tools/jetons.go) qu'au travers de
// l'interface Resolveur, donc un faux minimal suffit a l'isoler.
type tableFake struct {
	contenu map[string][]byte
	appelee bool
}

func (t *tableFake) Lire(jeton string) ([]byte, bool) {
	t.appelee = true
	c, ok := t.contenu[jeton]
	return c, ok
}

func monter(t *testing.T, table *tableFake, emailsAutorises string) http.Handler {
	t.Helper()
	return Nouveau(table, acces.Nouveau(emailsAutorises))
}

func appel(h http.Handler, chemin, email, role string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(http.MethodGet, chemin, nil)
	r.Header.Set("X-End-User-Email", email)
	r.Header.Set("X-End-User-Role", role)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	return w
}

func TestTelechargement_JetonValide_RendExactementLesOctetsMemorises(t *testing.T) {
	attendu := []byte("id;ville\n1;Rennes\n")
	table := &tableFake{contenu: map[string][]byte{
		"deadbeefdeadbeefdeadbeefdeadbeef": attendu,
	}}
	h := monter(t, table, "alice@example.test")

	w := appel(h, "/download/deadbeefdeadbeefdeadbeefdeadbeef", "alice@example.test", "readonly")
	if w.Code != http.StatusOK {
		t.Fatalf("code = %d", w.Code)
	}
	if w.Body.String() != string(attendu) {
		t.Errorf("corps = %q, attendu %q", w.Body.String(), string(attendu))
	}
	if ct := w.Header().Get("Content-Type"); !strings.Contains(ct, "text/csv") {
		t.Errorf("Content-Type = %q", ct)
	}
}

func TestTelechargement_Refus(t *testing.T) {
	table := &tableFake{contenu: map[string][]byte{
		"deadbeefdeadbeefdeadbeefdeadbeef": []byte("id;ville\n1;Rennes\n"),
	}}
	h := monter(t, table, "alice@example.test")

	cas := []struct{ nom, email, role string }{
		{"non autorise", "dave@example.test", "readonly"},
		{"sans identite", "", ""},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			table.appelee = false
			w := appel(h, "/download/deadbeefdeadbeefdeadbeefdeadbeef", c.email, c.role)
			if w.Code != http.StatusForbidden {
				t.Errorf("code = %d, attendu 403", w.Code)
			}
			if table.appelee {
				t.Error("la table de jetons ne doit pas etre consultee pour un appelant non autorise")
			}
		})
	}
}

// Le jeton vient du reseau : une traversee de chemin ou un format hors
// liste blanche ne doit jamais atteindre la table de jetons.
func TestTelechargement_FormatDeJetonInvalide(t *testing.T) {
	table := &tableFake{contenu: map[string][]byte{}}
	h := monter(t, table, "alice@example.test")

	for _, mauvais := range []string{"../../etc/passwd", "pas-hexa", "", "DEADBEEFDEADBEEFDEADBEEFDEADBEEF"} {
		table.appelee = false
		w := appel(h, "/download/"+mauvais, "alice@example.test", "readonly")
		if w.Code != http.StatusBadRequest && w.Code != http.StatusNotFound {
			t.Errorf("jeton %q: code = %d, attendu 400 ou 404", mauvais, w.Code)
		}
		if table.appelee {
			t.Errorf("jeton %q: la table de jetons ne doit jamais etre consultee pour un format invalide", mauvais)
		}
	}
}

// Un jeton bien forme mais absent de la table (inconnu ou expire) rend
// 404 : le moteur n'est plus appele au telechargement, donc il n'y a plus
// d'erreur moteur a relayer, seulement une table qui ne le connait pas.
func TestTelechargement_JetonExpireOuInconnu(t *testing.T) {
	table := &tableFake{contenu: map[string][]byte{}}
	h := monter(t, table, "alice@example.test")

	w := appel(h, "/download/deadbeefdeadbeefdeadbeefdeadbeef", "alice@example.test", "readonly")
	if w.Code != http.StatusNotFound {
		t.Errorf("code = %d, attendu 404", w.Code)
	}
}
