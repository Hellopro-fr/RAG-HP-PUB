package tools

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

const lienBO = "https://bo.example.test/admin/mcp/hellodata/download.php?t=abc.def"

// Le BO fournit le lien signe : il est rendu au LLM tel quel, aucun jeton
// /download du wrapper n'est frappe (sa route n'est pas publique).
func TestExportCSV_LienDuBO(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Hellodata-Lien", lienBO)
		io.WriteString(w, "siren,region\n123456789,6\n# fin-export;1;\n")
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly", true},
		req("tools/call", `{"name":"export_csv","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true}}}`))
	if r.Error != nil {
		t.Fatalf("erreur inattendue: %+v", r.Error)
	}
	b, _ := json.Marshal(r.Result)
	if !strings.Contains(string(b), lienBO) || strings.Contains(string(b), "/download/") {
		t.Errorf("le lien du BO doit etre rendu, sans jeton wrapper: %s", string(b))
	}
	if n := nbJetons(h.Jetons()); n != 0 {
		t.Errorf("%d jeton(s) frappe(s) alors que le BO fournit le lien", n)
	}
}

func TestRecupAcheteur_LienDuBO(t *testing.T) {
	reponse, _ := json.Marshal(map[string]interface{}{
		"code": 200,
		"response": map[string]interface{}{
			"id_campagne": 12, "campagne_creee": true, "selectionnes": 1,
			"exclus": map[string]int{}, "fiches_parcourues": 3, "epuise": true,
			"csv": "\xEF\xBB\xBFtelephone_normalise;id_acheteur\n0612345678;42\n", "url_csv": lienBO,
		},
	})
	bo, wh := &amont{}, &amont{}
	h := handlerCampagne(t, bo.serveur(t, string(reponse), 200), wh.serveur(t, `{}`, 200))
	sortie := texte(t, appelOutil(t, h, alice, "recup_acheteur", argsRecupValides))
	var s sortieRecup
	if err := json.Unmarshal([]byte(sortie), &s); err != nil {
		t.Fatalf("sortie illisible: %v", err)
	}
	if s.URLCSV != lienBO || strings.Contains(sortie, "0612345678") {
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
