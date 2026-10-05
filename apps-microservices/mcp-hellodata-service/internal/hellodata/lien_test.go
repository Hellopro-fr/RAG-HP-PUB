package hellodata

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"testing"
)

const lienBO = "https://bo.example.test/admin/mcp/hellodata/download.php?t=abc.def"

// Le BO joint a l'export l'URL signee de download.php dans X-Hellodata-Lien.
func TestExporterCSV_LienDuMoteur(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Hellodata-Lien", lienBO)
		io.WriteString(w, bomUTF8+"id;ville\n1;Rennes\n# fin-export;1;\n")
	})
	got, err := c.ExporterCSV(context.Background(), Demande{Filtre: json.RawMessage(`{}`)})
	if err != nil || got.Lien != lienBO || got.Lignes != 1 {
		t.Fatalf("page = %+v, err %v", got, err)
	}
}

// Moteur plus ancien : pas d'en-tete, Lien vide (le wrapper retombe sur /download).
func TestExporterCSV_SansLien(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, bomUTF8+"id\n1\n# fin-export;1;\n")
	})
	got, err := c.ExporterCSV(context.Background(), Demande{Filtre: json.RawMessage(`{}`)})
	if err != nil || got.Lien != "" {
		t.Fatalf("Lien = %q, err %v", got.Lien, err)
	}
}

// Un en-tete qui n'est pas une URL http(s) absolue est ignore.
func TestExporterCSV_LienNonHTTPIgnore(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Hellodata-Lien", "javascript:alert(1)")
		io.WriteString(w, bomUTF8+"id\n1\n# fin-export;1;\n")
	})
	got, err := c.ExporterCSV(context.Background(), Demande{Filtre: json.RawMessage(`{}`)})
	if err != nil || got.Lien != "" {
		t.Fatalf("Lien = %q, err %v", got.Lien, err)
	}
}

func TestRecupAcheteur_URLCSV(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"code":200,"response":{"id_campagne":7,"selectionnes":1,"csv":"a;b\n","url_csv":"`+lienBO+`"}}`)
	})
	rec, err := c.RecupAcheteur(context.Background(), DemandeRecup{N: 1, CreePar: "a@example.test"})
	if err != nil || rec.URLCSV != lienBO {
		t.Fatalf("recup = %+v, err %v", rec, err)
	}
	c2 := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"code":200,"response":{"id_campagne":7,"selectionnes":1,"csv":"a;b\n","url_csv":"ftp://x"}}`)
	})
	rec, err = c2.RecupAcheteur(context.Background(), DemandeRecup{N: 1, CreePar: "a@example.test"})
	if err != nil || rec.URLCSV != "" {
		t.Fatalf("url_csv non http doit etre ignore: %+v, err %v", rec, err)
	}
}
