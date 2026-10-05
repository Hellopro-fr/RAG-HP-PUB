package tools

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"

	"mcp-hellodata/internal/acces"
	"mcp-hellodata/internal/filtre"
	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/mcp"
)

// colonnesRestreintes reflete requete.php cote moteur. Le refus se prend
// ici pour eviter un aller-retour reseau qui echouerait de toute facon.
var colonnesRestreintes = map[string]bool{"email": true, "mobile": true}

type argsCommuns struct {
	Filtre      json.RawMessage `json:"filtre"`
	Colonnes    []string        `json:"colonnes"`
	Taille      int             `json:"taille"`
	Cursor      *int            `json:"cursor"`
	TypeBlocage int             `json:"type_blocage"`
	Exact       bool            `json:"exact"`
}

// sortieExportCSV est la reponse rendue au LLM par hellodata_export_csv.
// NextCursor reste un pointeur pour marshaller en null quand la page est
// la derniere, plutot que d'omettre le champ.
type sortieExportCSV struct {
	URL        string `json:"url"`
	Lignes     int    `json:"lignes"`
	NextCursor *int   `json:"next_cursor"`
	HasMore    bool   `json:"has_more"`
}

func (h *Handler) appeler(ctx context.Context, id Identite, rpcID json.RawMessage, nom string, brut json.RawMessage) mcp.Reponse {
	// Les outils de campagne ont leurs propres arguments (campagnes.go).
	switch nom {
	case "recup_acheteur":
		return h.recupAcheteur(ctx, id, rpcID, brut)
	case "bilan_campagnes":
		return h.bilanCampagnes(ctx, rpcID, brut)
	case "enregistrer_reponses":
		return h.enregistrerReponses(ctx, id, rpcID, brut)
	}

	var a argsCommuns
	if len(brut) > 0 {
		if err := json.Unmarshal(brut, &a); err != nil {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "arguments illisibles: "+err.Error())
		}
	}
	admin := acces.EstAdmin(id.Role)

	switch nom {
	case "compter":
		d, errRep := h.demande(rpcID, a, admin, false)
		if errRep != nil {
			return *errRep
		}
		d.Exact = a.Exact
		res, err := h.client.Compter(ctx, d)
		if err != nil {
			return erreurMoteur(rpcID, err)
		}
		return contenu(rpcID, res)

	case "echantillon":
		if a.Taille < 0 || a.Taille > TailleMax {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
				fmt.Sprintf("taille_invalide: %d hors bornes 1..%d", a.Taille, TailleMax))
		}
		d, errRep := h.demande(rpcID, a, admin, true)
		if errRep != nil {
			return *errRep
		}
		if d.Taille == 0 {
			d.Taille = TailleDefaut
		}
		d.Cursor = a.Cursor
		res, err := h.client.Echantillon(ctx, d)
		if err != nil {
			return erreurMoteur(rpcID, err)
		}
		return contenu(rpcID, res)

	case "export_csv":
		// Une seule page, plafonnee a 2000 lignes cote moteur : pas de
		// statut a interroger, le CSV revient dans cet appel.
		d, errRep := h.demande(rpcID, a, admin, true)
		if errRep != nil {
			return *errRep
		}
		d.Cursor = a.Cursor
		d.Demandeur = id.Email
		page, err := h.client.ExporterCSV(ctx, d)
		if err != nil {
			return erreurMoteur(rpcID, err)
		}
		// Le BO fournit un lien signe (download.php, 15 min, CSV regenere) :
		// le /download du wrapper n'a pas de route publique. Repli sur notre
		// jeton seulement quand un moteur plus ancien ne le fournit pas.
		if page.Lien != "" {
			log.Printf("[hellodata] export lien_bo demandeur=%s lignes=%d", id.Email, page.Lignes)
			return contenu(rpcID, sortieExportCSV{
				URL:        page.Lien,
				Lignes:     page.Lignes,
				NextCursor: page.NextCursor,
				HasMore:    page.HasMore,
			})
		}
		jeton, err := h.jetons.Frapper(page.Contenu)
		if err != nil {
			log.Printf("[hellodata] export: %v", err)
			return mcp.Echec(rpcID, mcp.CodeErreurInterne, "export_indisponible: reessayer plus tard")
		}
		// La liste statique ne fournit aucune trace d'audit. Cette ligne
		// est la seule qui existera sur une extraction de donnees
		// personnelles.
		log.Printf("[hellodata] export jeton=%s demandeur=%s lignes=%d", jeton, id.Email, page.Lignes)
		// Repli : l'URL pointe le /download du wrapper.
		return contenu(rpcID, sortieExportCSV{
			URL:        h.publicURL + "/download/" + jeton,
			Lignes:     page.Lignes,
			NextCursor: page.NextCursor,
			HasMore:    page.HasMore,
		})
	}
	return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "outil inconnu: "+nom)
}

// demande valide la forme de l'arbre et les colonnes AVANT tout appel
// reseau : un refus doit etre immediat et porter un message que le LLM
// peut corriger.
func (h *Handler) demande(rpcID json.RawMessage, a argsCommuns, admin, avecColonnes bool) (hellodata.Demande, *mcp.Reponse) {
	if len(a.Filtre) == 0 {
		r := mcp.Echec(rpcID, mcp.CodeParamsInvalides, "filtre requis")
		return hellodata.Demande{}, &r
	}
	var n filtre.Noeud
	if err := json.Unmarshal(a.Filtre, &n); err != nil {
		r := mcp.Echec(rpcID, mcp.CodeParamsInvalides, "filtre illisible: "+err.Error())
		return hellodata.Demande{}, &r
	}
	if _, err := filtre.Valider(n); err != nil {
		r := mcp.Echec(rpcID, mcp.CodeParamsInvalides, err.Error())
		return hellodata.Demande{}, &r
	}
	if avecColonnes && !admin {
		for _, c := range a.Colonnes {
			if colonnesRestreintes[c] {
				r := mcp.Echec(rpcID, mcp.CodeParamsInvalides,
					"colonne_restreinte: '"+c+"' exige le role admin")
				return hellodata.Demande{}, &r
			}
		}
	}
	return hellodata.Demande{
		Filtre:      a.Filtre,
		Colonnes:    a.Colonnes,
		Taille:      a.Taille,
		TypeBlocage: a.TypeBlocage,
		Restreintes: admin,
	}, nil
}

func contenu(rpcID json.RawMessage, v interface{}) mcp.Reponse {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return mcp.Echec(rpcID, mcp.CodeErreurInterne, "encodage du resultat")
	}
	return mcp.OK(rpcID, map[string]interface{}{
		"content": []map[string]interface{}{{"type": "text", "text": string(b)}},
	})
}

// erreurMoteur conserve le code stable du moteur : c'est ce que le LLM lit
// pour corriger son appel. Une erreur reseau devient un code generique,
// jamais un message technique brut.
func erreurMoteur(rpcID json.RawMessage, err error) mcp.Reponse {
	var em *hellodata.ErreurMoteur
	if errors.As(err, &em) {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, em.Code+": "+em.Message)
	}
	log.Printf("[hellodata] appel moteur en echec: %v", err)
	return mcp.Echec(rpcID, mcp.CodeErreurInterne, "moteur_indisponible: reessayer plus tard")
}
