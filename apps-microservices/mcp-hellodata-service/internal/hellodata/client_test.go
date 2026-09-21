package hellodata

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func serveur(t *testing.T, gestionnaire http.HandlerFunc) *Client {
	t.Helper()
	s := httptest.NewServer(gestionnaire)
	t.Cleanup(s.Close)
	return Nouveau(s.URL, "jeton-test")
}

func TestCompter_DeballeLEnveloppe(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Authorization"); got != "Bearer jeton-test" {
			t.Errorf("Authorization = %q", got)
		}
		if r.URL.Query().Get("action") != "comptage" {
			t.Errorf("action = %q", r.URL.Query().Get("action"))
		}
		io.WriteString(w, `{"code":200,"response":{"count":1234,"exact":false,"plafonne":false,"depuis_cache":true}}`)
	})
	got, err := c.Compter(context.Background(), Demande{Filtre: json.RawMessage(`{"critere":"region","comparateur":"dans","valeur":[6]}`)})
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if got.Count != 1234 || !got.DepuisCache {
		t.Errorf("Comptage = %+v", got)
	}
}

// Le code d'erreur stable du moteur doit remonter tel quel : c'est lui que
// le LLM lit pour corriger son appel.
func TestCompter_RemonteLeCodeDErreurDuMoteur(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		io.WriteString(w, `{"code":400,"response":{"erreur":"critere_invalide","message":"critere_inconnu: 'couleur'. Criteres connus: region, ..."}}`)
	})
	_, err := c.Compter(context.Background(), Demande{Filtre: json.RawMessage(`{}`)})
	var em *ErreurMoteur
	if !errors.As(err, &em) {
		t.Fatalf("attendu une *ErreurMoteur, obtenu %T: %v", err, err)
	}
	if em.Code != "critere_invalide" {
		t.Errorf("Code = %q, attendu critere_invalide", em.Code)
	}
	if !strings.Contains(em.Message, "Criteres connus") {
		t.Errorf("le message du moteur doit etre conserve, obtenu %q", em.Message)
	}
}

// Un moteur qui rend du HTML (page d'erreur Apache, redirection de session)
// ne doit pas produire un resultat vide qui passerait pour un succes.
func TestCompter_ReponseNonJSON(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, "<html>Service Unavailable</html>")
	})
	if _, err := c.Compter(context.Background(), Demande{Filtre: json.RawMessage(`{}`)}); err == nil {
		t.Fatal("attendu une erreur sur une reponse non JSON")
	}
}

func TestEchantillon_TransmetCurseurEtTaille(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		var recu Demande
		json.NewDecoder(r.Body).Decode(&recu)
		if recu.Taille != 50 || recu.Cursor == nil || *recu.Cursor != 999 {
			t.Errorf("Demande = %+v", recu)
		}
		io.WriteString(w, `{"code":200,"response":{"rows":[{"id_acheteur":1}],"next_cursor":1,"has_more":true}}`)
	})
	cur := 999
	got, err := c.Echantillon(context.Background(), Demande{
		Filtre: json.RawMessage(`{}`), Taille: 50, Cursor: &cur})
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if !got.HasMore || len(got.Rows) != 1 {
		t.Errorf("Echantillon = %+v", got)
	}
}

// Le budget de l'appel doit etre honore, sinon un moteur lent bloque le
// gateway.
func TestCompter_RespecteLeContexte(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		<-r.Context().Done()
	})
	ctx, annule := context.WithCancel(context.Background())
	annule()
	if _, err := c.Compter(ctx, Demande{Filtre: json.RawMessage(`{}`)}); err == nil {
		t.Fatal("attendu une erreur sur contexte annule")
	}
}

// La sentinelle presente doit livrer le nombre de lignes et le curseur
// suivant portes par le moteur, pas seulement le contenu CSV.
func TestExporterCSV_SentinellePresente(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("action") != "export" {
			t.Errorf("action = %q", r.URL.Query().Get("action"))
		}
		var recu Demande
		json.NewDecoder(r.Body).Decode(&recu)
		if string(recu.Filtre) != `{}` {
			t.Errorf("Filtre = %s", recu.Filtre)
		}
		io.WriteString(w, "id;ville\n1;Rennes\n2;Nantes\n# fin-export;2;17\n")
	})
	got, err := c.ExporterCSV(context.Background(), Demande{Filtre: json.RawMessage(`{}`)})
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if got.Lignes != 2 {
		t.Errorf("Lignes = %d, attendu 2", got.Lignes)
	}
	if got.NextCursor == nil || *got.NextCursor != 17 {
		t.Errorf("NextCursor = %v, attendu 17", got.NextCursor)
	}
	if !got.HasMore {
		t.Error("HasMore = false, attendu true")
	}
	if !strings.Contains(string(got.Contenu), "Rennes") || strings.Contains(string(got.Contenu), "fin-export") {
		t.Errorf("Contenu = %q", got.Contenu)
	}
}

// Une derniere page n'a pas de curseur suivant : la sentinelle porte un
// next_cursor vide, ce qui doit se traduire par HasMore=false.
func TestExporterCSV_DerniereBage_PasDeCurseurSuivant(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, "id;ville\n1;Rennes\n# fin-export;1;\n")
	})
	got, err := c.ExporterCSV(context.Background(), Demande{Filtre: json.RawMessage(`{}`)})
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if got.HasMore || got.NextCursor != nil {
		t.Errorf("attendu HasMore=false et NextCursor=nil, obtenu %+v", got)
	}
}

// Une reponse coupee en cours de transfert n'a pas de sentinelle finale :
// elle doit echouer, jamais passer pour un CSV complet.
func TestExporterCSV_SentinelleAbsente(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, "id;ville\n1;Rennes\n2;Nant")
	})
	got, err := c.ExporterCSV(context.Background(), Demande{Filtre: json.RawMessage(`{}`)})
	if err == nil {
		t.Fatal("attendu une erreur sur sentinelle absente")
	}
	if len(got.Contenu) != 0 {
		t.Errorf("le contenu tronque ne doit pas etre rendu, obtenu %q", got.Contenu)
	}
}
