package transport

import (
	"encoding/json"
	"net/http"

	"mcp-hellodata/internal/mcp"
	"mcp-hellodata/internal/tools"
)

// Plafond du corps JSON-RPC entrant, aligne sur celui du moteur.
const corpsMax = 256 << 10

// IdentiteDepuis lit ce que le gateway injecte. Un en-tete absent donne
// une chaine vide, qui vaut refus en aval : l'absence n'est pas une
// confiance implicite. X-End-User-Granted ne compte que s'il vaut
// exactement "true" : "TRUE", "1" ou "yes" ne sont pas un grant.
func IdentiteDepuis(r *http.Request) tools.Identite {
	return tools.Identite{
		Email:   r.Header.Get("X-End-User-Email"),
		Role:    r.Header.Get("X-End-User-Role"),
		Granted: r.Header.Get("X-End-User-Granted") == "true",
	}
}

func MCP(h *tools.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			http.Error(w, "methode non autorisee", http.StatusMethodNotAllowed)
			return
		}
		var req mcp.Requete
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, corpsMax)).Decode(&req); err != nil {
			ecrire(w, mcp.Echec(nil, mcp.CodeErreurParsing, "JSON illisible"))
			return
		}
		ecrire(w, h.Traiter(r.Context(), IdentiteDepuis(r), req))
	})
}

func ecrire(w http.ResponseWriter, rep mcp.Reponse) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(rep)
}
