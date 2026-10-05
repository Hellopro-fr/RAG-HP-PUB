package hellodata

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"testing"
)

// lienDe rend un lien download.php sur l'hote qui a recu la requete (= HELLODATA_BASE_URL).
func lienDe(r *http.Request) string {
	return "http://" + r.Host + "/admin/mcp/hellodata/download.php?t=abc.def"
}

// Le BO joint a l'export l'URL signee de download.php dans X-Hellodata-Lien.
func TestExporterCSV_LienDuMoteur(t *testing.T) {
	var attendu string
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		attendu = lienDe(r)
		w.Header().Set("X-Hellodata-Lien", attendu)
		io.WriteString(w, bomUTF8+"id;ville\n1;Rennes\n# fin-export;1;\n")
	})
	got, err := c.ExporterCSV(context.Background(), Demande{Filtre: json.RawMessage(`{}`)})
	if err != nil || got.Lien == "" || got.Lien != attendu || got.Lignes != 1 {
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

// Un lien qui n'est pas sur l'hote du moteur (ou pas http(s)) est ignore.
func TestExporterCSV_LienNonHTTPIgnore(t *testing.T) {
	for _, mauvais := range []string{"javascript:alert(1)", "https://autre.example.test/download.php?t=a.b", "ftp://x/y"} {
		c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("X-Hellodata-Lien", mauvais)
			io.WriteString(w, bomUTF8+"id\n1\n# fin-export;1;\n")
		})
		got, err := c.ExporterCSV(context.Background(), Demande{Filtre: json.RawMessage(`{}`)})
		if err != nil || got.Lien != "" {
			t.Fatalf("%q: Lien = %q, err %v", mauvais, got.Lien, err)
		}
	}
}

// Hote etranger refuse, meme hote accepte ; https exige quand la base est en https.
func TestLienValide_MemeSchemaEtHote(t *testing.T) {
	c := Nouveau("https://bo.example.test/admin/mcp/hellodata", "j")
	cas := map[string]string{
		"https://bo.example.test/admin/mcp/hellodata/download.php?t=a.b":    "https://bo.example.test/admin/mcp/hellodata/download.php?t=a.b",
		"https://BO.example.test/admin/mcp/hellodata/download.php?t=a.b":    "https://BO.example.test/admin/mcp/hellodata/download.php?t=a.b",
		"http://bo.example.test/admin/mcp/hellodata/download.php?t=a.b":     "",
		"https://evil.example.test/admin/mcp/hellodata/download.php?t=a.b":  "",
		"https://bo.example.test.evil.test/download.php?t=a.b":              "",
		"https://bo.example.test:8443/admin/mcp/hellodata/download.php?t=x": "",
		"https://user@bo.example.test/download.php?t=a.b":                   "",
		"": "",
	}
	for lien, attendu := range cas {
		if got := c.lienValide(lien); got != attendu {
			t.Errorf("lienValide(%q) = %q, attendu %q", lien, got, attendu)
		}
	}
	if got := Nouveau("http://hd-php82:8080/admin/mcp/hellodata", "j").lienValide("http://hd-php82:8080/admin/mcp/hellodata/download.php?t=a.b"); got == "" {
		t.Error("base en http : un lien http du meme hote doit passer")
	}
}

func TestRecupAcheteur_URLCSV(t *testing.T) {
	var attendu string
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		attendu = lienDe(r)
		io.WriteString(w, `{"code":200,"response":{"id_campagne":7,"selectionnes":1,"csv":"a;b\n","url_csv":"`+attendu+`"}}`)
	})
	rec, err := c.RecupAcheteur(context.Background(), DemandeRecup{N: 1, CreePar: "a@example.test"})
	if err != nil || rec.URLCSV == "" || rec.URLCSV != attendu {
		t.Fatalf("recup = %+v, err %v", rec, err)
	}
	c2 := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"code":200,"response":{"id_campagne":7,"selectionnes":1,"csv":"a;b\n","url_csv":"https://autre.example.test/x"}}`)
	})
	rec, err = c2.RecupAcheteur(context.Background(), DemandeRecup{N: 1, CreePar: "a@example.test"})
	if err != nil || rec.URLCSV != "" {
		t.Fatalf("url_csv d'un hote etranger doit etre ignore: %+v, err %v", rec, err)
	}
}
