package tools

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// lienBO : hote du faux moteur (= HELLODATA_BASE_URL), seul accepte par le client.
func lienBO(r *http.Request) string {
	return "http://" + r.Host + "/admin/mcp/hellodata/download.php?t=abc.def"
}

// Le BO fournit le lien signe : il est rendu au LLM tel quel, aucun jeton
// /download du wrapper n'est frappe (sa route n'est pas publique).
func TestExportCSV_LienDuBO(t *testing.T) {
	var lien string
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		lien = lienBO(r)
		w.Header().Set("X-Hellodata-Lien", lien)
		io.WriteString(w, "siren,region\n123456789,6\n# fin-export;1;\n")
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly", true},
		req("tools/call", `{"name":"export_csv","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"colonnes":["raison_sociale","ville"]}}`))
	if r.Error != nil {
		t.Fatalf("erreur inattendue: %+v", r.Error)
	}
	b, _ := json.Marshal(r.Result)
	if lien == "" || !strings.Contains(string(b), lien) || strings.Contains(string(b), "/download/") {
		t.Errorf("le lien du BO doit etre rendu, sans jeton wrapper: %s", string(b))
	}
	if n := nbJetons(h.Jetons()); n != 0 {
		t.Errorf("%d jeton(s) frappe(s) alors que le BO fournit le lien", n)
	}
}

func TestRecupAcheteur_LienDuBO(t *testing.T) {
	var lien string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		lien = lienBO(r)
		reponse, _ := json.Marshal(map[string]interface{}{
			"code": 200,
			"response": map[string]interface{}{
				"id_campagne": 12, "campagne_creee": true, "selectionnes": 1,
				"exclus": map[string]int{}, "fiches_parcourues": 3, "epuise": true,
				"csv": "\xEF\xBB\xBFtelephone_normalise;id_acheteur\n0612345678;42\n", "url_csv": lien,
			},
		})
		w.Write(reponse)
	}))
	t.Cleanup(srv.Close)
	wh := &amont{}
	h := handlerCampagne(t, srv, wh.serveur(t, `{}`, 200))
	sortie := texte(t, appelOutil(t, h, alice, "recup_acheteur", argsRecupValides))
	var s sortieRecup
	if err := json.Unmarshal([]byte(sortie), &s); err != nil {
		t.Fatalf("sortie illisible: %v", err)
	}
	if lien == "" || s.URLCSV != lien || strings.Contains(sortie, "0612345678") {
		t.Errorf("url_csv = %q (sortie %s)", s.URLCSV, sortie)
	}
	if n := nbJetons(h.Jetons()); n != 0 {
		t.Errorf("%d jeton(s) frappe(s) alors que le BO fournit le lien", n)
	}
}

// nbJetons compte les jetons /download frappes (aide de test).
func nbJetons(j *Jetons) int {
	j.mu.Lock()
	defer j.mu.Unlock()
	return len(j.table)
}
