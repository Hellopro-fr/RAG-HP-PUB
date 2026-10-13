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
	// Lien est l'URL signee (15 min) de download.php sur le BO, lue dans
	// l'en-tete X-Hellodata-Lien. Vide quand le moteur ne la fournit pas
	// encore : le wrapper retombe alors sur son propre /download.
	Lien string
}

// ErreurMoteur porte le code stable rendu par le moteur. Le LLM le lit
// pour corriger son appel, donc il remonte tel quel jusqu'au tool.
type ErreurMoteur struct {
	Code    string
	Message string
}

func (e *ErreurMoteur) Error() string { return e.Code + ": " + e.Message }

// Campagne identifie une campagne SMS / appel. Code est la cle naturelle :
// le moteur cree la campagne si le code est inconnu, la reutilise sinon.
// Pas de cree_par ici : il vient de l'identite (Recuperation.CreePar),
// jamais des arguments de l'outil.
type Campagne struct {
	Code         string `json:"code"`
	Nom          string `json:"nom"`
	Canal        string `json:"canal"`
	Prestataire  string `json:"prestataire,omitempty"`
	Message      string `json:"message,omitempty"`
	DateCampagne string `json:"date_campagne"`
}

// DemandeRecup est la charge utile de l'action recup_acheteur du BO.
type DemandeRecup struct {
	Campagne Campagne        `json:"campagne"`
	N        int             `json:"n"`
	Filtre   json.RawMessage `json:"filtre"`
	CreePar  string          `json:"cree_par"`
	// Colonnes vide : CSV historique a 8 colonnes. Sinon telephone_normalise
	// puis ces colonnes, lues sur la fiche active du numero.
	Colonnes    []string `json:"colonnes,omitempty"`
	Restreintes bool     `json:"colonnes_restreintes_autorisees,omitempty"`
	// Simulation : meme parcours, aucune ecriture, pas de CSV.
	Simulation bool `json:"simulation,omitempty"`
}

// Recuperation est la reponse de recup_acheteur. CSV porte la liste des
// numeros retenus (BOM compris) : le wrapper la sert par /download et ne
// la renvoie jamais telle quelle au LLM.
type Recuperation struct {
	IDCampagne       int            `json:"id_campagne"`
	CampagneCreee    bool           `json:"campagne_creee"`
	Selectionnes     int            `json:"selectionnes"`
	Exclus           map[string]int `json:"exclus"`
	FichesParcourues int            `json:"fiches_parcourues"`
	Epuise           bool           `json:"epuise"`
	CSV              string         `json:"csv"`
	// URLCSV est le lien signe (15 min) de download.php sur le BO qui
	// regenere ce CSV. Vide sur un moteur plus ancien : repli sur /download.
	URLCSV string `json:"url_csv"`
	// Simulation est l'echo du moteur : absent alors qu'on l'a demande, le
	// moteur ne connait pas le mode et a REELLEMENT reserve.
	Simulation bool `json:"simulation"`
}

// Contact est un element de liste deja envoyee : exactement un des deux
// identifiants (le wrapper le verifie avant le reseau).
type Contact struct {
	Telephone  string `json:"telephone,omitempty"`
	IDAcheteur int    `json:"id_acheteur,omitempty"`
}

// DemandeInscription est la charge utile de l'action inscrire_contacts du
// BO : une liste deja envoyee, a la date reelle de la campagne.
type DemandeInscription struct {
	Campagne Campagne  `json:"campagne"`
	Contacts []Contact `json:"contacts"`
	CreePar  string    `json:"cree_par"`
}

// Inscription est la reponse de inscrire_contacts. Les listes rendent les
// valeurs telles que recues, pour que l'utilisateur les retrouve dans son
// fichier.
type Inscription struct {
	IDCampagne       int      `json:"id_campagne"`
	CampagneCreee    bool     `json:"campagne_creee"`
	Inscrits         int      `json:"inscrits"`
	DejaDansCampagne int      `json:"deja_dans_campagne"`
	DoublonsListe    int      `json:"doublons_liste"`
	Inconnus         []string `json:"inconnus"`
	Invalides        []string `json:"invalides"`
	NePlusContacter  []string `json:"ne_plus_contacter"`
}

// LigneBilan est une campagne vue par bilan_campagnes.
type LigneBilan struct {
	Code                string `json:"code"`
	Nom                 string `json:"nom"`
	Canal               string `json:"canal"`
	DateCampagne        string `json:"date_campagne"`
	CreePar             string `json:"cree_par"`
	Envoyes             int    `json:"envoyes"`
	Positive            int    `json:"positive"`
	NegativeContactable int    `json:"negative_contactable"`
	NegativeStop        int    `json:"negative_stop"`
	SansReponse         int    `json:"sans_reponse"`
	LeadsTransmis       int    `json:"leads_transmis"`
}

type Bilan struct {
	Campagnes []LigneBilan `json:"campagnes"`
}

// Reponse est une reponse du prestataire, deja classee par le LLM.
type Reponse struct {
	Telephone    string `json:"telephone"`
	ReponseBrute string `json:"reponse_brute"`
	Categorie    string `json:"categorie"`
	// DateReponse : date reelle de la reponse saisie apres coup ; absente,
	// le webhook prend NOW().
	DateReponse string `json:"date_reponse,omitempty"`
}

// DemandeReponses est la charge utile du webhook FRONT enregistrer_reponses.
type DemandeReponses struct {
	CodeCampagne string    `json:"code_campagne"`
	Reponses     []Reponse `json:"reponses"`
}

type ResultatReponses struct {
	MisAJour     int      `json:"mis_a_jour"`
	Inconnus     []string `json:"inconnus"`
	HorsCampagne []string `json:"hors_campagne"`
	StopForce    int      `json:"stop_force"`
}

// Lead est un contact transmis au client, apres une reponse positive.
type Lead struct {
	Telephone        string `json:"telephone"`
	DateTransmission string `json:"date_transmission,omitempty"`
}

// DemandeLeads est la charge utile du webhook FRONT marquer_leads.
type DemandeLeads struct {
	CodeCampagne string `json:"code_campagne"`
	Leads        []Lead `json:"leads"`
}

type ResultatLeads struct {
	Marques      int      `json:"marques"`
	Inconnus     []string `json:"inconnus"`
	HorsCampagne []string `json:"hors_campagne"`
	NonPositifs  []string `json:"non_positifs"`
}
