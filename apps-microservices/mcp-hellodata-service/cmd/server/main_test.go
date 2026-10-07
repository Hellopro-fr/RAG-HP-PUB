package main

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
	"mcp-hellodata/internal/tools"
)

// h.Jetons() est le pont entre tools.Handler et le proxy de telechargement
// (voir son commentaire dans main.go). Ce test verifie qu'il rend bien la
// MEME table que celle qu'alimente hellodata_export_csv, et pas une table
// neuve qui ne connaitrait jamais aucun jeton emis par le Handler.
func TestHandlerJetons_RendLaTableQuAlimenteLExport(t *testing.T) {
	moteur := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, "id;ville\n1;Rennes\n# fin-export;1;\n")
	}))
	defer moteur.Close()

	h := tools.Nouveau(hellodata.Nouveau(moteur.URL, "jeton"), hellodata.Nouveau("http://webhook.invalid", "jeton-webhook"), "https://mcp.example.test")

	rep := h.Traiter(context.Background(), tools.Identite{Email: "alice@example.test", Role: "readonly", Granted: true},
		mcp.Requete{
			JSONRPC: "2.0", ID: json.RawMessage(`1`), Methode: "tools/call",
			Params: json.RawMessage(`{"name":"export_csv","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"colonnes":["raison_sociale","ville"]}}`),
		})
	if rep.Error != nil {
		t.Fatalf("erreur inattendue: %+v", rep.Error)
	}

	b, _ := json.Marshal(rep.Result)
	const prefixe = "https://mcp.example.test/download/"
	idx := strings.Index(string(b), prefixe)
	if idx == -1 {
		t.Fatalf("URL de telechargement absente de la reponse: %s", string(b))
	}
	debut := idx + len(prefixe)
	jeton := string(b)[debut : debut+32]

	contenu, ok := h.Jetons().Lire(jeton)
	if !ok {
		t.Fatalf("h.Jetons() ne retrouve pas le jeton %q emis par hellodata_export_csv", jeton)
	}
	if !strings.Contains(string(contenu), "Rennes") {
		t.Errorf("contenu relu = %q", string(contenu))
	}
}

// Un jeton qui n'a jamais ete frappe ne doit rien rendre : h.Jetons() ne
// doit pas exposer une table qui accepterait n'importe quoi.
func TestHandlerJetons_JetonInconnuNonTrouve(t *testing.T) {
	h := tools.Nouveau(hellodata.Nouveau("http://exemple.invalid", "jeton"), hellodata.Nouveau("http://webhook.invalid", "jeton-webhook"), "https://mcp.example.test")
	if _, ok := h.Jetons().Lire("deadbeefdeadbeefdeadbeefdeadbeef"); ok {
		t.Error("un jeton jamais frappe ne doit pas etre trouve")
	}
}
