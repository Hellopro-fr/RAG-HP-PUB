package tools

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"sync"
	"time"
)

// Une page vaut au plus 2000 lignes, donc la memoire d'un jeton est bornee
// a l'avance et ne depend pas de ce que demande le LLM.
const (
	JetonTTL = 15 * time.Minute
	JetonMax = 32
)

type entreeJeton struct {
	contenu []byte
	expire  time.Time
}

// Jetons est la table en memoire des pages CSV exportees, adressables par
// jeton. Elle ne survit pas a un redemarrage du service : c'est le contrat
// annonce au LLM dans la description de hellodata_export_csv.
//
// Exportee pour que internal/download puisse relire, via (*Handler).Jetons,
// exactement l'instance que hellodata_export_csv alimente — meme table,
// pas une copie. Les champs internes (mu, table) restent prives : seules
// Frapper et Lire forment le contrat public.
type Jetons struct {
	mu    sync.Mutex
	table map[string]entreeJeton
}

func NouveauxJetons() *Jetons {
	return &Jetons{table: make(map[string]entreeJeton)}
}

// Frapper purge les entrees expirees, refuse au-dela de JetonMax, tire 128
// bits d'alea et rend le jeton en hexadecimal minuscule — le format que
// /download validera.
func (j *Jetons) Frapper(contenu []byte) (string, error) {
	j.mu.Lock()
	defer j.mu.Unlock()

	maintenant := time.Now()
	for cle, e := range j.table {
		if maintenant.After(e.expire) {
			delete(j.table, cle)
		}
	}
	if len(j.table) >= JetonMax {
		return "", fmt.Errorf("trop_de_jetons: %d jetons actifs, maximum %d", len(j.table), JetonMax)
	}

	brut := make([]byte, 16)
	if _, err := rand.Read(brut); err != nil {
		return "", fmt.Errorf("jeton: generation: %w", err)
	}
	jeton := hex.EncodeToString(brut)
	j.table[jeton] = entreeJeton{contenu: contenu, expire: maintenant.Add(JetonTTL)}
	return jeton, nil
}

// Lire rend le contenu associe a un jeton non expire. Utilise par
// internal/download/proxy.go via (*Handler).Jetons.
func (j *Jetons) Lire(jeton string) ([]byte, bool) {
	j.mu.Lock()
	defer j.mu.Unlock()
	e, ok := j.table[jeton]
	if !ok || time.Now().After(e.expire) {
		return nil, false
	}
	return e.contenu, true
}
