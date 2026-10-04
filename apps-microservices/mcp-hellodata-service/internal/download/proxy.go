// Package download sert le CSV au client sans jamais appeler le moteur.
//
// Le CSV d'une page a deja ete recupere au moment de l'appel de l'outil
// hellodata_export_csv (internal/tools/selection.go) et memorise sous un
// jeton dans la table en memoire de internal/tools/jetons.go. Ici, on ne
// fait plus qu'autoriser, valider la forme du jeton et relire ce contenu
// deja en memoire : aucun aller-retour reseau, donc aucun risque de laisser
// fuir une URL ou un detail du moteur dans une reponse.
package download

import (
	"log"
	"net/http"
	"regexp"
	"strings"

	"mcp-hellodata/internal/acces"
	"mcp-hellodata/internal/transport"
)

// Le jeton vient du reseau. Liste blanche stricte plutot que nettoyage :
// on refuse tout ce qui n'est pas exactement 32 hexadecimaux minuscules,
// le format produit par jetons.Frapper (internal/tools/jetons.go).
var jetonValide = regexp.MustCompile(`^[0-9a-f]{32}$`)

// Resolveur lit le contenu memorise sous un jeton. La table de jetons de
// internal/tools/jetons.go la satisfait deja par sa methode Lire — ce
// paquet n'a pas besoin de nommer son type concret, qui reste prive a
// tools. Voir cmd/server/main.go pour la facon dont l'instance reelle
// (celle que hellodata_export_csv alimente) est branchee ici.
type Resolveur interface {
	Lire(jeton string) ([]byte, bool)
}

type proxy struct {
	jetons Resolveur
}

func Nouveau(j Resolveur) http.Handler {
	return &proxy{jetons: j}
}

func (p *proxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// Meme lecture des en-tetes que /mcp : une seule regle pour Granted.
	id := transport.IdentiteDepuis(r)
	email := id.Email
	if !acces.Autorise(id.Email, id.Role, id.Granted) {
		http.Error(w, "acces refuse", http.StatusForbidden)
		return
	}

	jeton := strings.TrimPrefix(r.URL.Path, "/download/")
	if !jetonValide.MatchString(jeton) {
		http.Error(w, "jeton invalide", http.StatusBadRequest)
		return
	}

	contenu, ok := p.jetons.Lire(jeton)
	if !ok {
		// Inconnu et expire rendent la meme reponse : distinguer les deux
		// cotes client ne ferait que confirmer qu'un jeton a existe.
		log.Printf("[hellodata] download jeton=%s demandeur=%s: introuvable ou expire", jeton, email)
		http.Error(w, "export indisponible", http.StatusNotFound)
		return
	}

	log.Printf("[hellodata] download jeton=%s demandeur=%s octets=%d", jeton, email, len(contenu))
	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	w.Header().Set("Content-Disposition", `attachment; filename="selection-`+jeton+`.csv"`)
	if _, err := w.Write(contenu); err != nil {
		// L'en-tete est deja parti : on ne peut plus changer le statut,
		// seulement tracer la coupure.
		log.Printf("[hellodata] download jeton=%s interrompu: %v", jeton, err)
	}
}
