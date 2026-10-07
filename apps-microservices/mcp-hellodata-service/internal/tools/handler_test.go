package tools

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/mcp"
)

func handler(t *testing.T, g http.HandlerFunc) *Handler {
	t.Helper()
	s := httptest.NewServer(g)
	t.Cleanup(s.Close)
	return Nouveau(hellodata.Nouveau(s.URL, "jeton"), hellodata.Nouveau("http://webhook.invalid", "jeton-webhook"), "https://mcp.example.test")
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
		{"admin voit les six outils", Identite{"dave@example.test", "admin", false}, 6},
		{"titulaire d un grant voit les six", Identite{"alice@example.test", "readonly", true}, 6},
		{"grant sans email ne voit rien", Identite{"", "", true}, 0},
		{"non autorise ne voit rien", Identite{"dave@example.test", "readonly", false}, 0},
		{"sans identite ne voit rien", Identite{"", "", false}, 0},
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
	r := h.Traiter(context.Background(), Identite{"dave@example.test", "readonly", false},
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
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly", true},
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
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly", true},
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
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly", true},
		req("tools/call", `{"name":"echantillon","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"taille":5000}}`))
	if r.Error == nil || !strings.Contains(r.Error.Message, "2000") {
		t.Fatalf("attendu un refus citant 2000, obtenu %+v", r.Error)
	}
}

// Un detenteur de grant obtient les colonnes restreintes : la demande part au
// moteur avec colonnes_restreintes_autorisees, comme pour un admin.
func TestEchantillon_ColonneRestreinteAvecGrant(t *testing.T) {
	var corps []byte
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		corps, _ = io.ReadAll(r.Body)
		io.WriteString(w, `{"code":200,"response":{"rows":[],"next_cursor":null,"has_more":false}}`)
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "config-only", true},
		req("tools/call", `{"name":"echantillon","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"colonnes":["email","mobile"]}}`))
	if r.Error != nil {
		t.Fatalf("un grant doit ouvrir email et mobile, obtenu %+v", r.Error)
	}
	if !strings.Contains(string(corps), `"colonnes_restreintes_autorisees":true`) {
		t.Errorf("le moteur doit recevoir l'autorisation des colonnes restreintes: %s", corps)
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
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly", true},
		req("tools/call", `{"name":"export_csv","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"colonnes":["raison_sociale","ville"]}}`))
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

// export_csv : meme regle, un grant ouvre mobile.
func TestExportCSV_ColonneRestreinteAvecGrant(t *testing.T) {
	appele := false
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		appele = true
		io.WriteString(w, "id_acheteur;mobile\n1;0600000000\n# fin-export;1;\n")
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "config-only", true},
		req("tools/call", `{"name":"export_csv","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"colonnes":["mobile"]}}`))
	if r.Error != nil {
		t.Fatalf("un grant doit ouvrir mobile, obtenu %+v", r.Error)
	}
	if !appele {
		t.Error("le moteur doit etre appele")
	}
}

// droitContacts : admin ou grant, et rien d'autre.
func TestDroitContacts(t *testing.T) {
	cas := []struct {
		id   Identite
		want bool
	}{
		{Identite{"a@example.test", "admin", false}, true},
		{Identite{"g@example.test", "config-only", true}, true},
		{Identite{"c@example.test", "config-only", false}, false},
		{Identite{"r@example.test", "read-only", false}, false},
		{Identite{"", "", false}, false},
	}
	for _, c := range cas {
		if got := droitContacts(c.id); got != c.want {
			t.Errorf("droitContacts(%+v) = %t, attendu %t", c.id, got, c.want)
		}
	}
}

func TestMethodeInconnue(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {})
	r := h.Traiter(context.Background(), Identite{"dave@example.test", "admin", false}, req("resources/list", `{}`))
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
	attendus := []string{"compter", "echantillon", "export_csv", "recup_acheteur", "bilan_campagnes", "enregistrer_reponses"}
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
