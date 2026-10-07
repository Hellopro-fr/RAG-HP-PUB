package main

import (
	"fmt"
	"log"
	"net/http"

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
	webhook := hellodata.Nouveau(c.WebhookURL, c.WebhookToken)
	h := tools.Nouveau(client, webhook, c.PublicURL)

	mux := http.NewServeMux()
	mux.Handle("/mcp", transport.MCP(h))
	// h.Jetons() rend la MEME table que celle que hellodata_export_csv
	// alimente : c'est l'instance reelle, obtenue par une API publique
	// ordinaire (internal/tools/handler.go), pas une copie.
	mux.Handle("/download/", download.Nouveau(h.Jetons()))
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
