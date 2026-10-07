package tools

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

// Reproduit le bug vu depuis claude.ai : le $ref de schemaFiltre etait casse,
// le client envoyait filtre comme une CHAINE JSON et tous les outils a filtre
// repondaient "filtre illisible: cannot unmarshal string".

const filtreObjet = `{"operateur":"ET","conditions":[{"critere":"departement","comparateur":"dans","valeur":["75"]}]}`

// filtreRecuParLeMoteur rend le champ filtre tel que le faux BO l'a recu.
func filtreRecuParLeMoteur(t *testing.T, corps []byte) json.RawMessage {
	t.Helper()
	var d struct {
		Filtre json.RawMessage `json:"filtre"`
	}
	if err := json.Unmarshal(corps, &d); err != nil {
		t.Fatalf("corps envoye au moteur illisible: %s", corps)
	}
	return d.Filtre
}

func TestCompter_FiltreEnChaineAccepteEtTransmisCommeObjet(t *testing.T) {
	var recu []byte
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		recu, _ = io.ReadAll(r.Body)
		io.WriteString(w, `{"code":200,"response":{"count":7,"exact":false,"plafonne":false,"depuis_cache":false}}`)
	})
	chaine, _ := json.Marshal(filtreObjet)
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "admin", false},
		req("tools/call", `{"name":"compter","arguments":{"filtre":`+string(chaine)+`}}`))
	if r.Error != nil {
		t.Fatalf("filtre en chaine refuse: %+v", r.Error)
	}
	f := filtreRecuParLeMoteur(t, recu)
	if len(f) == 0 || f[0] != '{' {
		t.Fatalf("le moteur doit recevoir un objet, recu: %s", f)
	}
}

func TestRecupAcheteur_FiltreEnChaineTransmisCommeObjet(t *testing.T) {
	var amontBO, amontWebhook amont
	bo := amontBO.serveur(t, `{"code":200,"response":{"code_campagne":"T","selectionnes":0,"exclus":{},"epuise":true}}`, 200)
	webhook := amontWebhook.serveur(t, `{}`, 200)
	h := handlerCampagne(t, bo, webhook)
	chaine, _ := json.Marshal(filtreObjet)
	args := `{"campagne":{"code":"T","nom":"t","canal":"sms","date_campagne":"2026-10-05"},"n":1,"filtre":` + string(chaine) + `}`

	r := appelOutil(t, h, alice, "recup_acheteur", args)
	if r.Error != nil {
		t.Fatalf("filtre en chaine refuse: %+v", r.Error)
	}
	if amontBO.nb() != 1 {
		t.Fatalf("appels au BO = %d, attendu 1", amontBO.nb())
	}
	f := filtreRecuParLeMoteur(t, []byte(amontBO.corps[0]))
	if len(f) == 0 || f[0] != '{' {
		t.Fatalf("le moteur doit recevoir un objet, recu: %s", f)
	}
}

func TestFiltre_ChaineNonObjetToujoursRefusee(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("aucun appel reseau attendu pour un filtre invalide")
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "admin", false},
		req("tools/call", `{"name":"compter","arguments":{"filtre":"pas du json"}}`))
	if r.Error == nil || !strings.Contains(r.Error.Message, "filtre illisible") {
		t.Fatalf("attendu filtre illisible, recu: %+v", r.Error)
	}
}

// Aucun $ref dans le catalogue, et filtre type objet sur chaque outil.
func TestToolsList_FiltreTypeObjetSansRef(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {})
	rep := h.Traiter(context.Background(), Identite{"alice@example.test", "admin", false}, req("tools/list", `{}`))
	b, _ := json.Marshal(rep.Result)
	if strings.Contains(string(b), "$ref") {
		t.Fatalf("le catalogue contient encore un $ref: %s", b)
	}
	var out struct {
		Tools []struct {
			Name        string `json:"name"`
			InputSchema struct {
				Properties map[string]map[string]interface{} `json:"properties"`
			} `json:"inputSchema"`
		} `json:"tools"`
	}
	json.Unmarshal(b, &out)
	vus := 0
	for _, tl := range out.Tools {
		if f, ok := tl.InputSchema.Properties["filtre"]; ok {
			vus++
			if f["type"] != "object" {
				t.Errorf("%s: filtre.type = %v, attendu object", tl.Name, f["type"])
			}
		}
	}
	if vus != 4 {
		t.Fatalf("outils a filtre vus = %d, attendu 4", vus)
	}
}
