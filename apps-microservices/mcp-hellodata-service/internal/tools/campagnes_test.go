package tools

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/mcp"
)

// amont enregistre chaque requete recue par un faux BO ou un faux webhook.
type amont struct {
	mu      sync.Mutex
	actions []string
	corps   []string
	auth    []string
}

func (a *amont) nb() int {
	a.mu.Lock()
	defer a.mu.Unlock()
	return len(a.actions)
}

func (a *amont) serveur(t *testing.T, reponse string, statut int) *httptest.Server {
	t.Helper()
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		a.mu.Lock()
		a.actions = append(a.actions, r.URL.Query().Get("action"))
		a.corps = append(a.corps, string(b))
		a.auth = append(a.auth, r.Header.Get("Authorization"))
		a.mu.Unlock()
		w.WriteHeader(statut)
		io.WriteString(w, reponse)
	}))
	t.Cleanup(s.Close)
	return s
}

// handlerCampagne monte un Handler dont le BO et le webhook sont deux faux
// distincts, pour verifier que chaque outil frappe le bon.
func handlerCampagne(t *testing.T, bo, webhook *httptest.Server) *Handler {
	t.Helper()
	return Nouveau(hellodata.Nouveau(bo.URL, "jeton-bo"), hellodata.Nouveau(webhook.URL, "jeton-webhook"),
		"https://mcp.example.test")
}

var alice = Identite{Email: "alice@example.test", Role: "readonly", Granted: true}

func appelOutil(t *testing.T, h *Handler, id Identite, nom, args string) mcp.Reponse {
	t.Helper()
	return h.Traiter(context.Background(), id, req("tools/call", `{"name":"`+nom+`","arguments":`+args+`}`))
}

// texte rend le JSON que contenu() a place dans content[0].text.
func texte(t *testing.T, r mcp.Reponse) string {
	t.Helper()
	if r.Error != nil {
		t.Fatalf("erreur inattendue: %+v", r.Error)
	}
	b, _ := json.Marshal(r.Result)
	var out struct {
		Content []struct {
			Text string `json:"text"`
		} `json:"content"`
	}
	if err := json.Unmarshal(b, &out); err != nil || len(out.Content) != 1 {
		t.Fatalf("resultat hors format: %s", b)
	}
	return out.Content[0].Text
}

const argsRecupValides = `{
	"campagne": {"code": "relance-btp-2026-10", "nom": "Relance BTP", "canal": "sms", "date_campagne": "2026-10-05"},
	"n": 20,
	"filtre": {"operateur": "ET", "conditions": [
		{"critere": "region", "comparateur": "dans", "valeur": [6]},
		{"critere": "hist_derniere_reponse_il_y_a_plus_de_jours", "comparateur": "=", "valeur": 60}
	]}
}`

func TestDefinitions_SixOutils(t *testing.T) {
	requis := map[string][]string{
		"recup_acheteur":       {"campagne", "n", "filtre"},
		"bilan_campagnes":      {},
		"enregistrer_reponses": {"code_campagne", "reponses"},
	}
	trouves := 0
	for _, d := range Definitions() {
		attendu, ok := requis[d.Nom]
		if !ok {
			continue
		}
		trouves++
		schema, _ := d.SchemaEntre.(map[string]interface{})
		got, _ := schema["required"].([]string)
		if strings.Join(got, ",") != strings.Join(attendu, ",") {
			t.Errorf("%s: required = %v, attendu %v", d.Nom, got, attendu)
		}
		if raw, _ := json.Marshal(d.SchemaEntre); strings.Contains(string(raw), `"required":null`) {
			t.Errorf("%s: schema porte required null", d.Nom)
		}
		if d.Description == "" {
			t.Errorf("%s: description vide", d.Nom)
		}
	}
	if trouves != 3 {
		t.Fatalf("%d outils de campagne trouves, attendu 3", trouves)
	}
}

// cree_par vient de X-End-User-Email. Un cree_par glisse dans les
// arguments, a la racine ou dans la campagne, est ignore.
func TestRecupAcheteur_CreeParDepuisLIdentite(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t,
		bo.serveur(t, `{"code":200,"response":{"id_campagne":12,"campagne_creee":true,"selectionnes":0,"exclus":{},"fiches_parcourues":10,"epuise":true}}`, 200),
		wh.serveur(t, `{}`, 200))

	args := strings.Replace(argsRecupValides, `"n": 20,`, `"n": 20, "cree_par": "pirate@example.test",`, 1)
	args = strings.Replace(args, `"canal": "sms",`, `"canal": "sms", "cree_par": "pirate@example.test",`, 1)
	texte(t, appelOutil(t, h, alice, "recup_acheteur", args))

	if bo.nb() != 1 || bo.actions[0] != "recup_acheteur" {
		t.Fatalf("BO: actions %v, attendu [recup_acheteur]", bo.actions)
	}
	if wh.nb() != 0 {
		t.Errorf("le webhook ne doit pas etre appele par recup_acheteur")
	}
	if bo.auth[0] != "Bearer jeton-bo" {
		t.Errorf("Authorization = %q", bo.auth[0])
	}
	var envoye struct {
		CreePar  string `json:"cree_par"`
		N        int    `json:"n"`
		Campagne struct {
			Code    string `json:"code"`
			CreePar string `json:"cree_par"`
		} `json:"campagne"`
	}
	if err := json.Unmarshal([]byte(bo.corps[0]), &envoye); err != nil {
		t.Fatalf("corps illisible: %v", err)
	}
	if envoye.CreePar != "alice@example.test" {
		t.Errorf("cree_par = %q, attendu l email de l appelant", envoye.CreePar)
	}
	if envoye.Campagne.CreePar != "" {
		t.Errorf("campagne.cree_par = %q, ne doit pas etre transmis", envoye.Campagne.CreePar)
	}
	if envoye.N != 20 || envoye.Campagne.Code != "relance-btp-2026-10" {
		t.Errorf("corps = %s", bo.corps[0])
	}
}

func TestRecupAcheteur_RefusAvantReseau(t *testing.T) {
	cas := []struct{ nom, de, vers, code string }{
		{"n nul", `"n": 20`, `"n": 0`, "n_hors_bornes"},
		{"n trop grand", `"n": 20`, `"n": 2001`, "n_hors_bornes"},
		{"canal email", `"canal": "sms"`, `"canal": "email"`, "campagne_invalide"},
		{"date illisible", `"date_campagne": "2026-10-05"`, `"date_campagne": "05/10/2026"`, "campagne_invalide"},
		{"code absent", `"code": "relance-btp-2026-10", `, ``, "campagne_invalide"},
		{"code trop long", `"relance-btp-2026-10"`, `"` + strings.Repeat("x", 65) + `"`, "campagne_invalide"},
		{"nom vide", `"nom": "Relance BTP"`, `"nom": " "`, "campagne_invalide"},
		{"noeud ambigu", `"operateur": "ET", "conditions"`, `"operateur": "ET", "critere": "x", "conditions"`, "noeud_ambigu"},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			bo, wh := &amont{}, &amont{}
			h := handlerCampagne(t, bo.serveur(t, `{}`, 200), wh.serveur(t, `{}`, 200))
			args := strings.Replace(argsRecupValides, c.de, c.vers, 1)
			if args == argsRecupValides {
				t.Fatalf("remplacement %q sans effet", c.de)
			}
			r := appelOutil(t, h, alice, "recup_acheteur", args)
			if r.Error == nil || !strings.HasPrefix(r.Error.Message, c.code) {
				t.Errorf("erreur = %+v, attendu le code %q", r.Error, c.code)
			}
			if bo.nb()+wh.nb() != 0 {
				t.Errorf("aucun appel reseau attendu, BO=%d webhook=%d", bo.nb(), wh.nb())
			}
		})
	}
	t.Run("filtre absent", func(t *testing.T) {
		bo, wh := &amont{}, &amont{}
		h := handlerCampagne(t, bo.serveur(t, `{}`, 200), wh.serveur(t, `{}`, 200))
		r := appelOutil(t, h, alice, "recup_acheteur",
			`{"campagne":{"code":"c","nom":"n","canal":"appel","date_campagne":"2026-10-05"},"n":5}`)
		if r.Error == nil || bo.nb() != 0 {
			t.Errorf("filtre absent: erreur = %+v, appels BO = %d", r.Error, bo.nb())
		}
	})
}

// Le CSV du BO est servi par /download et n'est JAMAIS renvoye au LLM :
// il porte des numeros de telephone.
func TestRecupAcheteur_CSVServiParDownload(t *testing.T) {
	csv := "\xEF\xBB\xBFtelephone_normalise;id_acheteur\n0612345678;42\n"
	reponse, _ := json.Marshal(map[string]interface{}{
		"code": 200,
		"response": map[string]interface{}{
			"id_campagne": 12, "campagne_creee": false, "selectionnes": 1,
			"exclus":            map[string]int{"ne_plus_contacter": 3, "telephone_invalide": 7},
			"fiches_parcourues": 11, "epuise": true, "csv": csv,
		},
	})
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t, bo.serveur(t, string(reponse), 200), wh.serveur(t, `{}`, 200))

	sortie := texte(t, appelOutil(t, h, alice, "recup_acheteur", argsRecupValides))
	if strings.Contains(sortie, "0612345678") {
		t.Fatalf("le CSV a fuite dans la reponse au LLM: %s", sortie)
	}
	var s sortieRecup
	if err := json.Unmarshal([]byte(sortie), &s); err != nil {
		t.Fatalf("sortie illisible: %v", err)
	}
	if s.IDCampagne != 12 || s.Selectionnes != 1 || s.Exclus["telephone_invalide"] != 7 || !s.Epuise {
		t.Errorf("sortie = %+v", s)
	}
	const prefixe = "https://mcp.example.test/download/"
	if !strings.HasPrefix(s.URLCSV, prefixe) {
		t.Fatalf("url_csv = %q", s.URLCSV)
	}
	contenu, ok := h.Jetons().Lire(strings.TrimPrefix(s.URLCSV, prefixe))
	if !ok || string(contenu) != csv {
		t.Errorf("contenu servi = %q, attendu le CSV du BO", contenu)
	}
}

func TestRecupAcheteur_SansSelectionPasDeLien(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t,
		bo.serveur(t, `{"code":200,"response":{"id_campagne":3,"selectionnes":0,"exclus":{},"fiches_parcourues":0,"epuise":true}}`, 200),
		wh.serveur(t, `{}`, 200))
	sortie := texte(t, appelOutil(t, h, alice, "recup_acheteur", argsRecupValides))
	if strings.Contains(sortie, "url_csv") {
		t.Errorf("aucun lien attendu sans selection: %s", sortie)
	}
}

// Des numeros annonces sans CSV : la reponse est incoherente, on ne rend
// pas un succes qui laisserait croire a une liste.
func TestRecupAcheteur_SelectionSansCSVEchoue(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t,
		bo.serveur(t, `{"code":200,"response":{"id_campagne":3,"selectionnes":5,"exclus":{},"fiches_parcourues":9,"epuise":true}}`, 200),
		wh.serveur(t, `{}`, 200))
	r := appelOutil(t, h, alice, "recup_acheteur", argsRecupValides)
	if r.Error == nil || !strings.HasPrefix(r.Error.Message, "moteur_indisponible") {
		t.Errorf("erreur = %+v", r.Error)
	}
}

// Le code d'erreur du BO (campagne_incoherente) remonte tel quel au LLM.
func TestRecupAcheteur_ErreurMoteurRelayee(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t,
		bo.serveur(t, `{"code":409,"response":{"erreur":"campagne_incoherente","message":"canal different"}}`, 409),
		wh.serveur(t, `{}`, 200))
	r := appelOutil(t, h, alice, "recup_acheteur", argsRecupValides)
	if r.Error == nil || !strings.HasPrefix(r.Error.Message, "campagne_incoherente") {
		t.Errorf("erreur = %+v", r.Error)
	}
}

func TestOutilsCampagne_RefusesAUnNonAutorise(t *testing.T) {
	inconnu := Identite{Email: "dave@example.test", Role: "readonly"}
	for _, nom := range []string{"recup_acheteur", "bilan_campagnes", "enregistrer_reponses"} {
		bo, wh := &amont{}, &amont{}
		h := handlerCampagne(t, bo.serveur(t, `{}`, 200), wh.serveur(t, `{}`, 200))
		r := appelOutil(t, h, inconnu, nom, argsRecupValides)
		if r.Error == nil || !strings.HasPrefix(r.Error.Message, "acces_refuse") {
			t.Errorf("%s: erreur = %+v, attendu acces_refuse", nom, r.Error)
		}
		if bo.nb()+wh.nb() != 0 {
			t.Errorf("%s: aucun appel reseau attendu", nom)
		}
	}
}

func TestBilanCampagnes(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t,
		bo.serveur(t, `{"code":200,"response":{"campagnes":[{"code":"c1","nom":"N","canal":"sms","envoyes":20,"positive":3,"sans_reponse":17}]}}`, 200),
		wh.serveur(t, `{}`, 200))
	sortie := texte(t, appelOutil(t, h, alice, "bilan_campagnes", `{"code":"c1"}`))
	if bo.actions[0] != "bilan_campagnes" || !strings.Contains(bo.corps[0], `"code":"c1"`) {
		t.Errorf("BO: action %q corps %s", bo.actions[0], bo.corps[0])
	}
	if !strings.Contains(sortie, `"envoyes": 20`) || wh.nb() != 0 {
		t.Errorf("sortie = %s, webhook = %d", sortie, wh.nb())
	}
}

func TestBilanCampagnes_ListeVideJamaisNull(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t, bo.serveur(t, `{"code":200,"response":{}}`, 200), wh.serveur(t, `{}`, 200))
	if sortie := texte(t, appelOutil(t, h, alice, "bilan_campagnes", `{}`)); !strings.Contains(sortie, `"campagnes": []`) {
		t.Errorf("sortie = %s", sortie)
	}
}

func reponses(n int, categorie string) string {
	var b strings.Builder
	b.WriteString(`{"code_campagne":"relance-btp-2026-10","reponses":[`)
	for i := 0; i < n; i++ {
		if i > 0 {
			b.WriteString(",")
		}
		b.WriteString(`{"telephone":"0612345678","reponse_brute":"non merci","categorie":"` + categorie + `"}`)
	}
	b.WriteString(`]}`)
	return b.String()
}

func TestEnregistrerReponses_RefusAvantReseau(t *testing.T) {
	gros := `{"code_campagne":"c","reponses":[` +
		strings.TrimSuffix(strings.Repeat(`{"telephone":"0612345678","reponse_brute":"`+strings.Repeat("a", 600)+`","categorie":"positive"},`, 450), ",") +
		`]}`
	cas := []struct{ nom, args, code string }{
		{"categorie inconnue", reponses(1, "peut_etre"), "categorie_invalide"},
		{"trop de reponses", reponses(ReponsesMax+1, "positive"), "trop_de_reponses"},
		{"aucune reponse", `{"code_campagne":"c","reponses":[]}`, "reponses_vides"},
		{"code absent", `{"reponses":[{"telephone":"06","reponse_brute":"x","categorie":"positive"}]}`, "code_campagne_invalide"},
		{"telephone absent", `{"code_campagne":"c","reponses":[{"reponse_brute":"x","categorie":"positive"}]}`, "telephone_manquant"},
		{"corps trop gros", gros, "corps_trop_gros"},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			bo, wh := &amont{}, &amont{}
			h := handlerCampagne(t, bo.serveur(t, `{}`, 200), wh.serveur(t, `{}`, 200))
			r := appelOutil(t, h, alice, "enregistrer_reponses", c.args)
			if r.Error == nil || !strings.HasPrefix(r.Error.Message, c.code) {
				t.Errorf("erreur = %+v, attendu le code %q", r.Error, c.code)
			}
			if bo.nb()+wh.nb() != 0 {
				t.Errorf("aucun appel reseau attendu, BO=%d webhook=%d", bo.nb(), wh.nb())
			}
		})
	}
	// Controle positif : 500 reponses exactement passent la validation.
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t, bo.serveur(t, `{}`, 200), wh.serveur(t, `{"code":200,"response":{"mis_a_jour":500}}`, 200))
	if r := appelOutil(t, h, alice, "enregistrer_reponses", reponses(ReponsesMax, "positive")); r.Error != nil || wh.nb() != 1 {
		t.Errorf("500 reponses: erreur = %+v, appels webhook = %d", r.Error, wh.nb())
	}
}

func TestEnregistrerReponses_VersLeWebhook(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t,
		bo.serveur(t, `{}`, 200),
		wh.serveur(t, `{"code":200,"response":{"mis_a_jour":1,"inconnus":["0700000000"],"stop_force":1}}`, 200))

	sortie := texte(t, appelOutil(t, h, alice, "enregistrer_reponses", reponses(1, "negative_stop")))
	if bo.nb() != 0 {
		t.Errorf("le BO ne doit pas etre appele par enregistrer_reponses")
	}
	if wh.nb() != 1 || wh.actions[0] != "enregistrer_reponses" || wh.auth[0] != "Bearer jeton-webhook" {
		t.Fatalf("webhook: actions %v auth %v", wh.actions, wh.auth)
	}
	if !strings.Contains(wh.corps[0], `"code_campagne":"relance-btp-2026-10"`) || !strings.Contains(wh.corps[0], `"categorie":"negative_stop"`) {
		t.Errorf("corps = %s", wh.corps[0])
	}
	var res hellodata.ResultatReponses
	if err := json.Unmarshal([]byte(sortie), &res); err != nil {
		t.Fatalf("sortie illisible: %v", err)
	}
	if res.MisAJour != 1 || res.StopForce != 1 || len(res.Inconnus) != 1 || res.HorsCampagne == nil {
		t.Errorf("resultat = %+v (hors_campagne doit etre [] et non null)", res)
	}
}

func TestEnregistrerReponses_ErreurWebhookRelayee(t *testing.T) {
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t, bo.serveur(t, `{}`, 200),
		wh.serveur(t, `{"code":404,"response":{"erreur":"campagne_inconnue","message":"code absent"}}`, 404))
	r := appelOutil(t, h, alice, "enregistrer_reponses", reponses(1, "positive"))
	if r.Error == nil || !strings.HasPrefix(r.Error.Message, "campagne_inconnue") {
		t.Errorf("erreur = %+v", r.Error)
	}
}
