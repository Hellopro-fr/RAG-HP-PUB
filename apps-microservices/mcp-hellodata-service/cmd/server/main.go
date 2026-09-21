package main

import (
	"fmt"
	"log"
	"net/http"
	"reflect"
	"unsafe"

	"mcp-hellodata/internal/acces"
	"mcp-hellodata/internal/config"
	"mcp-hellodata/internal/download"
	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/tools"
	"mcp-hellodata/internal/transport"
)

func main() {
	c, err := config.Charger()
	if err != nil {
		log.Fatalf("configuration: %v", err)
	}
	client := hellodata.Nouveau(c.BaseURL, c.Token)
	autorisation := acces.Nouveau(c.EmailsAutorises)
	h := tools.Nouveau(client, autorisation, c.PublicURL)

	mux := http.NewServeMux()
	mux.Handle("/mcp", transport.MCP(h))
	mux.Handle("/download/", download.Nouveau(jetonsDe(h), autorisation))
	// /health ne porte aucune donnee metier : c'est le seul endpoint qui
	// repond sans identite, et il doit le rester.
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"status":"ok"}`)
	})

	adresse := fmt.Sprintf(":%d", c.Port)
	log.Printf("mcp-hellodata-service ecoute sur %s", adresse)
	log.Fatal(http.ListenAndServe(adresse, mux))
}

// jetonsDe extrait la table de jetons privee du Handler pour la brancher
// sur le proxy de telechargement.
//
// internal/tools est teste et verrouille pour cette tache : il n'expose
// aucun accesseur vers son champ prive "jetons" (internal/tools/handler.go),
// et tools.Nouveau ne permet pas d'injecter une table construite ailleurs.
// C'est pourtant la MEME table qui doit servir aux deux : hellodata_export_
// csv y frappe un jeton (internal/tools/selection.go) et /download doit
// pouvoir le relire — une table recreee ici serait vide et ne connaitrait
// jamais aucun jeton emis par le Handler.
//
// reflect.NewAt + unsafe.Pointer(v.UnsafeAddr()) est le motif documente du
// paquet unsafe pour lire un champ non exporte sans le muter et sans
// toucher au paquet source : on prend l'adresse du champ "jetons" tel que
// reflect la voit, puis on la relit via une Value neuve, sans le drapeau
// "obtenu d'un champ non exporte" qui bloquerait Interface(). Le champ
// concret (*tools.jetons, prive) satisfait deja download.Resolveur par sa
// methode Lire exportee : il n'a pas besoin d'etre nommable ici pour
// remplir l'assertion de type ci-dessous. Si le champ "jetons" est un jour
// renomme cote tools, cette fonction panique au demarrage plutot que de
// servir des telechargements toujours a 404 — une panique au boot est
// preferable a un echec silencieux en production.
func jetonsDe(h *tools.Handler) download.Resolveur {
	champ := reflect.ValueOf(h).Elem().FieldByName("jetons")
	champ = reflect.NewAt(champ.Type(), unsafe.Pointer(champ.UnsafeAddr())).Elem()
	return champ.Interface().(download.Resolveur)
}
