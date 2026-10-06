package tools

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
)

// L'utilisateur choisit les champs d'une extraction : sans colonnes,
// export_csv refuse AVANT tout appel reseau et rend la liste a lui montrer.
func TestExportCSV_SansColonnesDemandeALUtilisateur(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("aucun appel au moteur attendu sans colonnes")
	})
	for _, args := range []string{
		`{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true}}`,
		`{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"colonnes":[]}`,
	} {
		r := h.Traiter(context.Background(), Identite{"alice@example.test", "admin", false},
			req("tools/call", `{"name":"export_csv","arguments":`+args+`}`))
		if r.Error == nil || !strings.HasPrefix(r.Error.Message, "colonnes_requises:") {
			t.Fatalf("attendu colonnes_requises, recu %+v", r.Error)
		}
		for _, attendu := range []string{"ID societe (id_fiche)", "Email (email, admin)", "Validite email"} {
			if !strings.Contains(r.Error.Message, attendu) {
				t.Errorf("la liste rendue doit contenir %q : %s", attendu, r.Error.Message)
			}
		}
	}
}

func TestExportCSV_ColonneInconnueRefuseeAvantAppel(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("aucun appel au moteur attendu pour une colonne inconnue")
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "admin", false},
		req("tools/call", `{"name":"export_csv","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"colonnes":["validite_email"]}}`))
	if r.Error == nil || !strings.HasPrefix(r.Error.Message, "colonne_inconnue: 'validite_email'") {
		t.Fatalf("attendu colonne_inconnue, recu %+v", r.Error)
	}
}

// Les colonnes choisies partent telles quelles au moteur.
func TestExportCSV_ColonnesChoisiesTransmises(t *testing.T) {
	var recu []byte
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		recu, _ = io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "text/csv")
		io.WriteString(w, "id_acheteur;siret;naf\n1;123;4520A\n# fin-export;1;\n")
	})
	h.Traiter(context.Background(), Identite{"alice@example.test", "admin", false},
		req("tools/call", `{"name":"export_csv","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"colonnes":["siret","naf"]}}`))
	var d struct {
		Colonnes []string `json:"colonnes"`
	}
	json.Unmarshal(recu, &d)
	if len(d.Colonnes) != 2 || d.Colonnes[0] != "siret" || d.Colonnes[1] != "naf" {
		t.Fatalf("colonnes transmises = %v, attendu [siret naf] (corps: %s)", d.Colonnes, recu)
	}
}

// echantillon garde son apercu par defaut : sans colonnes, pas de refus.
func TestEchantillon_SansColonnesResteUnApercu(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"code":200,"response":{"rows":[],"next_cursor":null,"has_more":false}}`)
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "admin", false},
		req("tools/call", `{"name":"echantillon","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true}}}`))
	if r.Error != nil {
		t.Fatalf("echantillon sans colonnes doit rester un apercu: %+v", r.Error)
	}
}

// Le schema rend colonnes obligatoire sur export_csv et liste les noms admis.
func TestToolsList_ExportCSVExigeColonnes(t *testing.T) {
	for _, o := range Definitions() {
		if o.Nom != "export_csv" {
			continue
		}
		b, _ := json.Marshal(o.SchemaEntre)
		var s struct {
			Required   []string `json:"required"`
			Properties struct {
				Colonnes struct {
					Items struct {
						Enum []string `json:"enum"`
					} `json:"items"`
				} `json:"colonnes"`
			} `json:"properties"`
		}
		json.Unmarshal(b, &s)
		if !strings.Contains(strings.Join(s.Required, ","), "colonnes") {
			t.Fatalf("export_csv.required = %v, attendu colonnes", s.Required)
		}
		if len(s.Properties.Colonnes.Items.Enum) != len(catalogueColonnes) {
			t.Fatalf("enum = %d noms, attendu %d", len(s.Properties.Colonnes.Items.Enum), len(catalogueColonnes))
		}
		if !strings.HasPrefix(o.Description, "AVANT d'appeler cet outil") {
			t.Fatalf("la description doit commencer par la consigne de demander: %q", o.Description)
		}
		return
	}
	t.Fatal("export_csv absent du catalogue")
}
