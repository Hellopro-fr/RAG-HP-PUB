package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"
	"unicode/utf8"

	"mcp-hellodata/internal/filtre"
	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/mcp"
)

// Bornes des outils de campagne (spec 2026-09-28-mcp-hellodata-campagnes-design.md).
const (
	// NMax : au-dela, appels repetes sur la meme campagne (decision C6).
	NMax = 2000
	// ReponsesMax : le webhook refuse au-dela, le LLM decoupe.
	ReponsesMax = 500
	// CorpsReponsesMax : plafond du corps accepte par le webhook. Verifie
	// ici pour refuser avant le reseau, avec un message que le LLM corrige.
	CorpsReponsesMax = 256 << 10
	codeMax          = 64
	texteMax         = 255
)

var canaux = map[string]bool{"sms": true, "appel": true}

var categories = map[string]bool{
	"positive":             true,
	"negative_contactable": true,
	"negative_stop":        true,
}

// argsRecup ne porte volontairement aucun cree_par : un champ inconnu est
// ignore au decodage, et cree_par vient toujours de l'identite.
type argsRecup struct {
	Campagne hellodata.Campagne `json:"campagne"`
	N        int                `json:"n"`
	Filtre   json.RawMessage    `json:"filtre"`
}

// sortieRecup est ce que voit le LLM : la reponse du BO sans le CSV, plus
// le lien /download qui le sert.
type sortieRecup struct {
	IDCampagne       int            `json:"id_campagne"`
	CampagneCreee    bool           `json:"campagne_creee"`
	Selectionnes     int            `json:"selectionnes"`
	Exclus           map[string]int `json:"exclus"`
	FichesParcourues int            `json:"fiches_parcourues"`
	Epuise           bool           `json:"epuise"`
	URLCSV           string         `json:"url_csv,omitempty"`
}

func (h *Handler) recupAcheteur(ctx context.Context, id Identite, rpcID json.RawMessage, brut json.RawMessage) mcp.Reponse {
	var a argsRecup
	if err := json.Unmarshal(brut, &a); err != nil {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "arguments illisibles: "+err.Error())
	}
	if err := validerCampagne(a.Campagne); err != nil {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, err.Error())
	}
	if a.N < 1 || a.N > NMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("n_hors_bornes: %d hors bornes 1..%d ; au-dela, rappeler sur la meme campagne", a.N, NMax))
	}
	if errRep := validerFiltre(rpcID, a.Filtre); errRep != nil {
		return *errRep
	}

	res, err := h.client.RecupAcheteur(ctx, hellodata.DemandeRecup{
		Campagne: a.Campagne,
		N:        a.N,
		Filtre:   a.Filtre,
		// L'auteur est l'appelant authentifie, jamais un argument.
		CreePar: id.Email,
	})
	if err != nil {
		return erreurMoteur(rpcID, err)
	}

	sortie := sortieRecup{
		IDCampagne:       res.IDCampagne,
		CampagneCreee:    res.CampagneCreee,
		Selectionnes:     res.Selectionnes,
		Exclus:           res.Exclus,
		FichesParcourues: res.FichesParcourues,
		Epuise:           res.Epuise,
	}
	if res.Selectionnes > 0 && res.URLCSV != "" {
		// Lien signe du BO (download.php, 15 min, CSV regenere depuis edgb2b).
		log.Printf("[hellodata] recup_acheteur lien_bo campagne=%s demandeur=%s selectionnes=%d", a.Campagne.Code, id.Email, res.Selectionnes)
		sortie.URLCSV = res.URLCSV
		return contenu(rpcID, sortie)
	}
	if res.Selectionnes > 0 {
		if res.CSV == "" {
			log.Printf("[hellodata] recup_acheteur campagne=%s: %d selectionnes mais CSV absent", a.Campagne.Code, res.Selectionnes)
			return mcp.Echec(rpcID, mcp.CodeErreurInterne, "moteur_indisponible: CSV absent de la reponse")
		}
		jeton, err := h.jetons.Frapper([]byte(res.CSV))
		if err != nil {
			log.Printf("[hellodata] recup_acheteur: %v", err)
			return mcp.Echec(rpcID, mcp.CodeErreurInterne, "export_indisponible: reessayer plus tard")
		}
		// Seule trace d'une extraction de numeros de telephone : on la garde.
		log.Printf("[hellodata] recup_acheteur jeton=%s campagne=%s demandeur=%s selectionnes=%d", jeton, a.Campagne.Code, id.Email, res.Selectionnes)
		sortie.URLCSV = h.publicURL + "/download/" + jeton
	}
	return contenu(rpcID, sortie)
}

func (h *Handler) bilanCampagnes(ctx context.Context, rpcID json.RawMessage, brut json.RawMessage) mcp.Reponse {
	var a struct {
		Code string `json:"code"`
	}
	if len(brut) > 0 {
		if err := json.Unmarshal(brut, &a); err != nil {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "arguments illisibles: "+err.Error())
		}
	}
	if len(a.Code) > codeMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, fmt.Sprintf("code_invalide: plus de %d caracteres", codeMax))
	}
	res, err := h.client.BilanCampagnes(ctx, a.Code)
	if err != nil {
		return erreurMoteur(rpcID, err)
	}
	if res.Campagnes == nil {
		res.Campagnes = []hellodata.LigneBilan{}
	}
	return contenu(rpcID, res)
}

func (h *Handler) enregistrerReponses(ctx context.Context, id Identite, rpcID json.RawMessage, brut json.RawMessage) mcp.Reponse {
	var d hellodata.DemandeReponses
	if err := json.Unmarshal(brut, &d); err != nil {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "arguments illisibles: "+err.Error())
	}
	if strings.TrimSpace(d.CodeCampagne) == "" || len(d.CodeCampagne) > codeMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("code_campagne_invalide: requis, %d caracteres au plus", codeMax))
	}
	if len(d.Reponses) == 0 {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "reponses_vides: au moins une reponse")
	}
	if len(d.Reponses) > ReponsesMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("trop_de_reponses: %d, maximum %d par appel ; decouper en plusieurs appels", len(d.Reponses), ReponsesMax))
	}
	for i, r := range d.Reponses {
		if strings.TrimSpace(r.Telephone) == "" {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides, fmt.Sprintf("telephone_manquant: reponse %d", i))
		}
		if !categories[r.Categorie] {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
				fmt.Sprintf("categorie_invalide: reponse %d, %q (attendues: positive, negative_contactable, negative_stop)", i, r.Categorie))
		}
	}
	if corps, _ := json.Marshal(d); len(corps) > CorpsReponsesMax {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
			fmt.Sprintf("corps_trop_gros: %d octets, maximum %d ; decouper en plusieurs appels", len(corps), CorpsReponsesMax))
	}

	res, err := h.webhook.EnregistrerReponses(ctx, d)
	if err != nil {
		return erreurMoteur(rpcID, err)
	}
	log.Printf("[hellodata] enregistrer_reponses campagne=%s demandeur=%s recues=%d mis_a_jour=%d", d.CodeCampagne, id.Email, len(d.Reponses), res.MisAJour)
	if res.Inconnus == nil {
		res.Inconnus = []string{}
	}
	if res.HorsCampagne == nil {
		res.HorsCampagne = []string{}
	}
	return contenu(rpcID, res)
}

func validerCampagne(c hellodata.Campagne) error {
	if strings.TrimSpace(c.Code) == "" || len(c.Code) > codeMax {
		return fmt.Errorf("campagne_invalide: code requis, %d caracteres au plus", codeMax)
	}
	if strings.TrimSpace(c.Nom) == "" || utf8.RuneCountInString(c.Nom) > texteMax {
		return fmt.Errorf("campagne_invalide: nom requis, %d caracteres au plus", texteMax)
	}
	if !canaux[c.Canal] {
		return fmt.Errorf("campagne_invalide: canal %q (attendus: sms, appel)", c.Canal)
	}
	if utf8.RuneCountInString(c.Prestataire) > texteMax {
		return fmt.Errorf("campagne_invalide: prestataire, %d caracteres au plus", texteMax)
	}
	if _, err := time.Parse("2006-01-02", c.DateCampagne); err != nil {
		return fmt.Errorf("campagne_invalide: date_campagne %q, format AAAA-MM-JJ attendu", c.DateCampagne)
	}
	return nil
}

// validerFiltre applique la validation structurelle commune. Les feuilles
// hist_* sont des feuilles ordinaires ici : leur place dans l'arbre
// (hist_hors_et_racine) est jugee par le compilateur du moteur.
func validerFiltre(rpcID json.RawMessage, brut json.RawMessage) *mcp.Reponse {
	if len(brut) == 0 {
		r := mcp.Echec(rpcID, mcp.CodeParamsInvalides, "filtre requis")
		return &r
	}
	var n filtre.Noeud
	if err := json.Unmarshal(brut, &n); err != nil {
		r := mcp.Echec(rpcID, mcp.CodeParamsInvalides, "filtre illisible: "+err.Error())
		return &r
	}
	if _, err := filtre.Valider(n); err != nil {
		r := mcp.Echec(rpcID, mcp.CodeParamsInvalides, err.Error())
		return &r
	}
	return nil
}
