package tools

import (
	"context"
	"encoding/json"
	"log"

	"mcp-hellodata/internal/acces"
	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/mcp"
)

// Identite est ce que le gateway injecte en X-End-User-Email,
// X-End-User-Role et X-End-User-Granted. Les champs vides signifient "on
// ignore qui appelle", ce qui vaut refus — pas confiance.
type Identite struct {
	Email string
	Role  string
	// Granted : le gateway a constate un grant server_authorizations sur
	// ce serveur (en-tete exactement "true").
	Granted bool
}

type Handler struct {
	client *hellodata.Client
	// webhook parle au FRONT (partenaires_externes/mcp/hellodata), qui
	// enregistre les reponses de campagne ; client parle au BO.
	webhook   *hellodata.Client
	publicURL string
	jetons    *Jetons
}

func Nouveau(c, webhook *hellodata.Client, publicURL string) *Handler {
	return &Handler{client: c, webhook: webhook, publicURL: publicURL, jetons: NouveauxJetons()}
}

// Jetons rend la table de jetons de ce Handler — la MEME instance que
// celle que hellodata_export_csv alimente (internal/tools/selection.go),
// pas une copie. C'est le point d'accroche public de internal/download :
// il permet de relier le proxy de telechargement a la table reelle par une
// API ordinaire, sans reflexion ni acces a un champ prive.
func (h *Handler) Jetons() *Jetons {
	return h.jetons
}

func (h *Handler) Traiter(ctx context.Context, id Identite, req mcp.Requete) mcp.Reponse {
	switch req.Methode {
	case "initialize":
		// initialize ne divulgue rien et doit repondre meme sans identite,
		// sinon aucun client ne peut se connecter pour decouvrir qu'il n'a
		// pas acces.
		return mcp.OK(req.ID, map[string]interface{}{
			"protocolVersion": "2025-03-26",
			"capabilities":    map[string]interface{}{"tools": map[string]interface{}{}},
			"serverInfo":      map[string]interface{}{"name": "mcp-hellodata", "version": "1.0.0"},
		})

	case "tools/list":
		// Liste variable selon l'appelant : un non autorise ne voit rien,
		// donc son LLM n'essaie pas d'appeler ce qu'il ne peut pas obtenir.
		if !acces.Autorise(id.Email, id.Role, id.Granted) {
			return mcp.OK(req.ID, map[string]interface{}{"tools": []mcp.Outil{}})
		}
		return mcp.OK(req.ID, map[string]interface{}{"tools": Definitions()})

	case "tools/call":
		// Le masquage de tools/list est du confort. La barriere est ici :
		// un outil non liste reste appelable directement.
		if !acces.Autorise(id.Email, id.Role, id.Granted) {
			return mcp.Echec(req.ID, mcp.CodeParamsInvalides,
				"acces_refuse: ce service est reserve aux administrateurs et aux utilisateurs autorises")
		}
		var p struct {
			Name      string          `json:"name"`
			Arguments json.RawMessage `json:"arguments"`
		}
		if err := json.Unmarshal(req.Params, &p); err != nil {
			return mcp.Echec(req.ID, mcp.CodeParamsInvalides, "params illisibles: "+err.Error())
		}
		log.Printf("[hellodata] appel outil=%s demandeur=%s droit=%s", p.Name, id.Email, acces.Source(id.Role))
		return h.appeler(ctx, id, req.ID, p.Name, p.Arguments)
	}
	return mcp.Echec(req.ID, mcp.CodeMethodeInconnue, "methode inconnue: "+req.Methode)
}
