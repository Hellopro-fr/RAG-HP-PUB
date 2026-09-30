package tools

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mcp-hellodata/internal/acces"
	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/mcp"
)

func handler(t *testing.T, g http.HandlerFunc) *Handler {
	t.Helper()
	s := httptest.NewServer(g)
	t.Cleanup(s.Close)
	return Nouveau(hellodata.Nouveau(s.URL, "jeton"),
		acces.Nouveau("alice@example.test"), "https://mcp.example.test")
}

func req(methode string, params string) mcp.Requete {
	return mcp.Requete{JSONRPC: "2.0", ID: json.RawMessage(`1`),
		Methode: methode, Params: json.RawMessage(params)}
}

func outils(t *testing.T, r mcp.Reponse) []interface{} {
	t.Helper()
	b, _ := json.Marshal(r.Result)
	var out struct {
		Tools []interface{} `json:"tools"`
	}
	json.Unmarshal(b, &out)
	return out.Tools
}

func TestToolsList_VariableSelonLAppelant(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {})
	cas := []struct {
		nom    string
		id     Identite
		attend int
	}{
		{"admin voit les trois outils", Identite{"dave@example.test", "admin"}, 3},
		{"autorise par liste voit les trois", Identite{"alice@example.test", "readonly"}, 3},
		{"non autorise ne voit rien", Identite{"dave@example.test", "readonly"}, 0},
		{"sans identite ne voit rien", Identite{"", ""}, 0},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			got := outils(t, h.Traiter(context.Background(), c.id, req("tools/list", `{}`)))
			if len(got) != c.attend {
				t.Errorf("%d outils, attendu %d", len(got), c.attend)
			}
		})
	}
}

// Le masquage est du confort. La barriere, c'est le refus a l'appel :
// un outil non liste reste appelable directement.
func TestToolsCall_RefuseUnNonAutorise(t *testing.T) {
	appele := false
	h := handler(t, func(w http.ResponseWriter, r *http.Request) { appele = true })
	r := h.Traiter(context.Background(), Identite{"dave@example.test", "readonly"},
		req("tools/call", `{"name":"compter","arguments":{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]}}}`))
	if r.Error == nil {
		t.Fatal("attendu une erreur pour un appelant non autorise")
	}
	if appele {
		t.Error("le moteur ne doit pas etre appele pour un non autorise")
	}
}

func TestCompter_CheminNominal(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"code":200,"response":{"count":42,"exact":false,"plafonne":false,"depuis_cache":false}}`)
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly"},
		req("tools/call", `{"name":"compter","arguments":{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]}}}`))
	if r.Error != nil {
		t.Fatalf("erreur inattendue: %+v", r.Error)
	}
	b, _ := json.Marshal(r.Result)
	if !strings.Contains(string(b), "42") {
		t.Errorf("resultat = %s", string(b))
	}
}

// Les bornes structurelles doivent refuser AVANT tout appel reseau.
func TestEchantillon_ArbreTropProfondRefuseAvantAppel(t *testing.T) {
	appele := false
	h := handler(t, func(w http.ResponseWriter, r *http.Request) { appele = true })
	profond := `{"critere":"region","comparateur":"dans","valeur":[6]}`
	for i := 0; i < 6; i++ {
		profond = `{"operateur":"ET","conditions":[` + profond + `]}`
	}
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly"},
		req("tools/call", `{"name":"echantillon","arguments":{"filtre":`+profond+`}}`))
	if r.Error == nil || !strings.Contains(r.Error.Message, "arbre_trop_complexe") {
		t.Fatalf("attendu arbre_trop_complexe, obtenu %+v", r.Error)
	}
	if appele {
		t.Error("le moteur ne doit pas etre appele pour un arbre hors bornes")
	}
}

func TestEchantillon_PlafondDeTaille(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"code":200,"response":{"rows":[],"next_cursor":null,"has_more":false}}`)
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly"},
		req("tools/call", `{"name":"echantillon","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"taille":5000}}`))
	if r.Error == nil || !strings.Contains(r.Error.Message, "2000") {
		t.Fatalf("attendu un refus citant 2000, obtenu %+v", r.Error)
	}
}

// Sans le droit, une colonne restreinte ne doit meme pas etre demandee au
// moteur : le refus se prend ici.
func TestEchantillon_ColonneRestreinteSansDroit(t *testing.T) {
	appele := false
	h := handler(t, func(w http.ResponseWriter, r *http.Request) { appele = true })
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly"},
		req("tools/call", `{"name":"echantillon","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"colonnes":["email"]}}`))
	if r.Error == nil || !strings.Contains(r.Error.Message, "colonne_restreinte") {
		t.Fatalf("attendu colonne_restreinte, obtenu %+v", r.Error)
	}
	if appele {
		t.Error("le moteur ne doit pas etre appele")
	}
}

// LE test du proxy : l'URL rendue au LLM pointe le wrapper, jamais le
// moteur, et le jeton qui y figure est bien celui qu'on peut relire.
func TestExportCSV_LUrlPointeLeWrapper(t *testing.T) {
	var urlMoteur string
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		urlMoteur = "http://" + r.Host
		io.WriteString(w, "siren,region\n123456789,6\n# fin-export;1;\n")
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly"},
		req("tools/call", `{"name":"export_csv","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true}}}`))
	if r.Error != nil {
		t.Fatalf("erreur inattendue: %+v", r.Error)
	}
	b, _ := json.Marshal(r.Result)
	if !strings.Contains(string(b), "https://mcp.example.test/download/") {
		t.Errorf("l URL rendue doit pointer le wrapper, obtenu %s", string(b))
	}
	if urlMoteur != "" && strings.Contains(string(b), urlMoteur) {
		t.Errorf("l URL du moteur a fuite dans la reponse: %s", string(b))
	}
	if !strings.Contains(string(b), `\"lignes\": 1`) {
		t.Errorf("lignes absentes ou incorrectes: %s", string(b))
	}
}

// export_csv doit refuser une colonne restreinte AVANT tout appel reseau,
// tout comme echantillon.
func TestExportCSV_ColonneRestreinteSansDroit(t *testing.T) {
	appele := false
	h := handler(t, func(w http.ResponseWriter, r *http.Request) { appele = true })
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly"},
		req("tools/call", `{"name":"export_csv","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"colonnes":["mobile"]}}`))
	if r.Error == nil || !strings.Contains(r.Error.Message, "colonne_restreinte") {
		t.Fatalf("attendu colonne_restreinte, obtenu %+v", r.Error)
	}
	if appele {
		t.Error("le moteur ne doit pas etre appele")
	}
}

func TestMethodeInconnue(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {})
	r := h.Traiter(context.Background(), Identite{"dave@example.test", "admin"}, req("resources/list", `{}`))
	if r.Error == nil || r.Error.Code != mcp.CodeMethodeInconnue {
		t.Fatalf("attendu CodeMethodeInconnue, obtenu %+v", r.Error)
	}
}

func TestInitialize_RepondSansIdentite(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {})
	r := h.Traiter(context.Background(), Identite{}, req("initialize", `{}`))
	if r.Error != nil {
		t.Fatalf("initialize doit repondre meme sans identite: %+v", r.Error)
	}
}

// Les noms sont SANS prefixe : le gateway ajoute 'hellodata_'. Les
// prefixer ici aussi donnerait hellodata_hellodata_compter au LLM.
func TestDefinitions_NomsSansPrefixe(t *testing.T) {
	attendus := []string{"compter", "echantillon", "export_csv"}
	defs := Definitions()
	if len(defs) != len(attendus) {
		t.Fatalf("%d outils, attendu %d", len(defs), len(attendus))
	}
	for i, nom := range attendus {
		if defs[i].Nom != nom {
			t.Errorf("outil %d = %q, attendu %q", i, defs[i].Nom, nom)
		}
		if strings.HasPrefix(defs[i].Nom, "hellodata_") {
			t.Errorf("%q porte deja le prefixe que le gateway ajoute", defs[i].Nom)
		}
	}
}
