package filtre

import (
	"encoding/json"
	"strings"
	"testing"
)

func feuille() Noeud {
	return Noeud{Critere: "region", Comparateur: "dans", Valeur: json.RawMessage(`[6]`)}
}

func groupe(op string, enfants ...Noeud) Noeud {
	return Noeud{Operateur: op, Conditions: enfants}
}

func TestValider_CasAcceptes(t *testing.T) {
	cas := []struct {
		nom      string
		noeud    Noeud
		feuilles int
	}{
		{"feuille seule", feuille(), 1},
		{"ET de deux feuilles", groupe("ET", feuille(), feuille()), 2},
		{"OU imbrique", groupe("ET", feuille(), groupe("OU", feuille(), feuille())), 3},
		{"NON unaire", groupe("NON", feuille()), 1},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			n, err := Valider(c.noeud)
			if err != nil {
				t.Fatalf("erreur inattendue: %v", err)
			}
			if n != c.feuilles {
				t.Errorf("feuilles = %d, attendu %d", n, c.feuilles)
			}
		})
	}
}

// Controle positif de la borne : exactement 5 doit passer, 6 doit echouer.
// Sans le cas acceptant, un bug refusant tout ferait passer le cas refusant.
func TestValider_ProfondeurLimite(t *testing.T) {
	n := feuille()
	for i := 0; i < 4; i++ {
		n = groupe("ET", n)
	}
	if _, err := Valider(n); err != nil {
		t.Fatalf("profondeur 5 doit passer, obtenu: %v", err)
	}
	if _, err := Valider(groupe("ET", n)); err == nil {
		t.Fatal("profondeur 6 doit echouer")
	}
}

func TestValider_CasRefuses(t *testing.T) {
	large := Noeud{Operateur: "ET"}
	for i := 0; i < 20; i++ {
		large.Conditions = append(large.Conditions, feuille())
	}
	vingtEtUn := Noeud{Operateur: "OU"}
	for i := 0; i < 21; i++ {
		vingtEtUn.Conditions = append(vingtEtUn.Conditions, feuille())
	}

	cas := []struct {
		nom      string
		noeud    Noeud
		fragment string
	}{
		{"groupe vide", groupe("ET"), "groupe_vide"},
		{"NON binaire", groupe("NON", feuille(), feuille()), "non_unaire"},
		{"21 enfants", vingtEtUn, "arbre_trop_complexe"},
		{"60 feuilles", groupe("ET", large, large, large), "arbre_trop_complexe"},
		{"operateur inconnu", groupe("XOR", feuille()), "operateur_inconnu"},
		{"ni feuille ni groupe", Noeud{}, "noeud_invalide"},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			_, err := Valider(c.noeud)
			if err == nil {
				t.Fatal("attendu une erreur, obtenu nil")
			}
			if !strings.Contains(err.Error(), c.fragment) {
				t.Errorf("message = %q, attendu contenant %q", err.Error(), c.fragment)
			}
		})
	}
}

// Le message doit apprendre au LLM ce qui etait attendu, pas seulement
// refuser : sans cela il reformule au hasard.
func TestValider_MessageEnonceLaLimite(t *testing.T) {
	vingtEtUn := Noeud{Operateur: "OU"}
	for i := 0; i < 21; i++ {
		vingtEtUn.Conditions = append(vingtEtUn.Conditions, feuille())
	}
	_, err := Valider(vingtEtUn)
	if err == nil || !strings.Contains(err.Error(), "20") {
		t.Errorf("le message doit citer la limite 20, obtenu: %v", err)
	}
}

// Un arbre decode depuis du JSON doit se valider comme un arbre construit
// en Go : c'est la forme qui arrivera reellement.
func TestValider_DepuisJSON(t *testing.T) {
	brut := `{"operateur":"ET","conditions":[
		{"critere":"region","comparateur":"dans","valeur":[6]},
		{"operateur":"OU","conditions":[
			{"critere":"effectif","comparateur":"dans","valeur":["10"]},
			{"critere":"a_siret","comparateur":"=","valeur":true}]}]}`
	var n Noeud
	if err := json.Unmarshal([]byte(brut), &n); err != nil {
		t.Fatalf("decodage: %v", err)
	}
	f, err := Valider(n)
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if f != 3 {
		t.Errorf("feuilles = %d, attendu 3", f)
	}
}
