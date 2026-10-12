package hellodata

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"testing"
)

// Les deux actions ajoutees le 2026-10-09 suivent le meme contrat que les
// autres : POST index.php?action=<nom>, jeton en Authorization et en
// X-Hellodata-Token, enveloppe {code, response}.

func TestClient_InscrireContacts(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Query().Get("action") != "inscrire_contacts" {
			t.Errorf("requete = %s %s", r.Method, r.URL)
		}
		if r.Header.Get("Authorization") != "Bearer jeton-test" || r.Header.Get(EnteteJeton) != "jeton-test" {
			t.Errorf("jeton absent: %v", r.Header)
		}
		var d DemandeInscription
		if err := json.NewDecoder(r.Body).Decode(&d); err != nil || d.CreePar != "alice@example.test" ||
			len(d.Contacts) != 2 || d.Contacts[1].IDAcheteur != 42 {
			t.Errorf("corps = %+v, err %v", d, err)
		}
		io.WriteString(w, `{"code":200,"response":{"id_campagne":3,"inscrits":1,"inconnus":["0700000000"],"doublons_liste":1}}`)
	})
	got, err := c.InscrireContacts(context.Background(), DemandeInscription{
		Campagne: Campagne{Code: "c", Nom: "n", Canal: "sms", DateCampagne: "2026-10-07"},
		Contacts: []Contact{{Telephone: "0612345678"}, {IDAcheteur: 42}},
		CreePar:  "alice@example.test",
	})
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if got.IDCampagne != 3 || got.Inscrits != 1 || got.DoublonsListe != 1 || len(got.Inconnus) != 1 {
		t.Errorf("resultat = %+v", got)
	}
}

func TestClient_MarquerLeadsRelaieLErreur(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("action") != "marquer_leads" {
			t.Errorf("URL = %s", r.URL)
		}
		w.WriteHeader(http.StatusNotFound)
		io.WriteString(w, `{"code":404,"response":{"erreur":"campagne_inconnue","message":"code absent"}}`)
	})
	_, err := c.MarquerLeads(context.Background(), DemandeLeads{CodeCampagne: "x", Leads: []Lead{{Telephone: "06"}}})
	var em *ErreurMoteur
	if !errors.As(err, &em) || em.Code != "campagne_inconnue" {
		t.Fatalf("erreur = %v, attendu campagne_inconnue", err)
	}
}
