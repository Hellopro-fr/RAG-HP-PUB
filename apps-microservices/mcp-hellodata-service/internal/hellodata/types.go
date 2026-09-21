package hellodata

import "encoding/json"

// Demande est la charge utile envoyee au moteur. Filtre reste brut :
// le wrapper en a valide la forme (package filtre), le moteur en juge
// le contenu.
type Demande struct {
	Filtre      json.RawMessage `json:"filtre"`
	Colonnes    []string        `json:"colonnes,omitempty"`
	Taille      int             `json:"taille,omitempty"`
	Cursor      *int            `json:"cursor,omitempty"`
	TypeBlocage int             `json:"type_blocage,omitempty"`
	Exact       bool            `json:"exact,omitempty"`
	Restreintes bool            `json:"colonnes_restreintes_autorisees,omitempty"`
	Demandeur   string          `json:"demandeur,omitempty"`
}

type Comptage struct {
	Count       int  `json:"count"`
	Exact       bool `json:"exact"`
	Plafonne    bool `json:"plafonne"`
	DureeMs     int  `json:"duree_ms"`
	DepuisCache bool `json:"depuis_cache"`
}

type Echantillon struct {
	Rows       []map[string]interface{} `json:"rows"`
	NextCursor *int                     `json:"next_cursor"`
	HasMore    bool                     `json:"has_more"`
}

// PageCSV est le contenu d'UNE page d'export, deja lu en entier, plus le
// curseur pour la page suivante. Une page est plafonnee a 2000 lignes,
// donc la charger en memoire est borne par construction.
type PageCSV struct {
	Contenu    []byte
	Lignes     int
	NextCursor *int
	HasMore    bool
}

// ErreurMoteur porte le code stable rendu par le moteur. Le LLM le lit
// pour corriger son appel, donc il remonte tel quel jusqu'au tool.
type ErreurMoteur struct {
	Code    string
	Message string
}

func (e *ErreurMoteur) Error() string { return e.Code + ": " + e.Message }
