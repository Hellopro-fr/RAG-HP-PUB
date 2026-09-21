package tools

import (
	"context"
	"encoding/json"

	"mcp-hellodata/internal/acces"
	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/mcp"
)

// Identite est ce que le gateway injecte en X-End-User-Email et
// X-End-User-Role. Les deux champs vides signifient "on ignore qui
// appelle", ce qui vaut refus — pas confiance.
type Identite struct {
	Email string
	Role  string
}

type Handler struct {
	client    *hellodata.Client
	acces     *acces.Acces
	publicURL string
	jetons    *jetons
}

func Nouveau(c *hellodata.Client, a *acces.Acces, publicURL string) *Handler {
	return &Handler{client: c, acces: a, publicURL: publicURL, jetons: nouveauxJetons()}
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
		if !h.acces.Autorise(id.Email, id.Role) {
			return mcp.OK(req.ID, map[string]interface{}{"tools": []mcp.Outil{}})
		}
		return mcp.OK(req.ID, map[string]interface{}{"tools": Definitions()})

	case "tools/call":
		// Le masquage de tools/list est du confort. La barriere est ici :
		// un outil non liste reste appelable directement.
		if !h.acces.Autorise(id.Email, id.Role) {
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
		return h.appeler(ctx, id, req.ID, p.Name, p.Arguments)
	}
	return mcp.Echec(req.ID, mcp.CodeMethodeInconnue, "methode inconnue: "+req.Methode)
}
