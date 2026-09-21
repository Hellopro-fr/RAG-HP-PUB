// Package filtre porte la forme de l'arbre de filtres et ses bornes.
//
// Il valide la STRUCTURE, jamais le contenu des feuilles : la liste
// blanche des criteres vit cote moteur, en un seul endroit. La dupliquer
// ici garantirait qu'elle diverge au premier critere ajoute.
package filtre

import (
	"encoding/json"
	"fmt"
)

const (
	ProfondeurMax = 5
	FeuillesMax   = 50
	EnfantsMax    = 20
)

// Noeud est soit un groupe (Operateur + Conditions), soit une feuille
// (Critere + Comparateur + Valeur). Valeur reste brute pour traverser le
// wrapper sans perte : c'est le moteur qui en juge.
type Noeud struct {
	Operateur   string          `json:"operateur,omitempty"`
	Conditions  []Noeud         `json:"conditions,omitempty"`
	Critere     string          `json:"critere,omitempty"`
	Comparateur string          `json:"comparateur,omitempty"`
	Valeur      json.RawMessage `json:"valeur,omitempty"`
}

func (n Noeud) estFeuille() bool { return n.Critere != "" }

// Valider rend le nombre de feuilles, ou la premiere erreur rencontree.
func Valider(n Noeud) (int, error) {
	feuilles := 0
	if err := parcourir(n, 1, &feuilles); err != nil {
		return 0, err
	}
	return feuilles, nil
}

// Le compteur est verifie a CHAQUE feuille, pas a la fin : avec 20 enfants
// et 5 niveaux un arbre peut porter 3,2 millions de feuilles, et le
// parcourir entierement avant de le refuser serait le deni de service
// qu'on veut eviter. La profondeur est verifiee des l'entree, feuille
// comprise : sinon une feuille placee un niveau trop bas se glisserait
// sous la limite, le dernier groupe l'ayant deja laissee passer.
func parcourir(n Noeud, profondeur int, feuilles *int) error {
	if profondeur > ProfondeurMax {
		return fmt.Errorf("arbre_trop_complexe: profondeur superieure a %d", ProfondeurMax)
	}
	// Un noeud qui porte les deux etait traite comme une feuille et tout
	// son sous-arbre disparaissait sans le moindre signal : le LLM
	// obtenait une requete differente de celle qu'il croyait avoir
	// demandee. Rien n'est jamais ignore silencieusement. Meme refus, meme
	// code, meme formulation que arbre.php cote moteur.
	if n.Critere != "" && n.Operateur != "" {
		return fmt.Errorf("noeud_ambigu: un noeud porte a la fois 'critere' '%s' et 'operateur' '%s'. "+
			"Choisir l un des deux : une feuille {critere, comparateur, valeur}, "+
			"ou un groupe {operateur, conditions}", n.Critere, n.Operateur)
	}
	if n.estFeuille() {
		*feuilles++
		if *feuilles > FeuillesMax {
			return fmt.Errorf("arbre_trop_complexe: plus de %d feuilles", FeuillesMax)
		}
		return nil
	}
	if n.Operateur == "" {
		return fmt.Errorf("noeud_invalide: ni 'critere' ni 'operateur'")
	}
	if n.Operateur != "ET" && n.Operateur != "OU" && n.Operateur != "NON" {
		return fmt.Errorf("operateur_inconnu: %q (attendus: ET, OU, NON)", n.Operateur)
	}
	if len(n.Conditions) == 0 {
		return fmt.Errorf("groupe_vide: %q doit porter au moins une condition", n.Operateur)
	}
	if n.Operateur == "NON" && len(n.Conditions) != 1 {
		return fmt.Errorf("non_unaire: NON prend exactement 1 condition, %d fournies", len(n.Conditions))
	}
	if len(n.Conditions) > EnfantsMax {
		return fmt.Errorf("arbre_trop_complexe: %d enfants, maximum %d", len(n.Conditions), EnfantsMax)
	}
	for _, enfant := range n.Conditions {
		if err := parcourir(enfant, profondeur+1, feuilles); err != nil {
			return err
		}
	}
	return nil
}
