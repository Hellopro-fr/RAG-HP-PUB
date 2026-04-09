package api

import (
	"net/http"
	"strings"

	"github.com/hellopro/mcp-gateway/internal/auth"
)

// Register mounts all REST API routes on the given mux under /api/v1/.
func (h *Handler) Register(mux *http.ServeMux) {
	// On applique les middlewares sur toutes les routes API
	apiMux := http.NewServeMux()

	apiMux.HandleFunc("/api/v1/servers", func(w http.ResponseWriter, r *http.Request) {
		// /api/v1/servers exactement (pas de sous-chemin)
		if r.URL.Path != "/api/v1/servers" && r.URL.Path != "/api/v1/servers/" {
			http.NotFound(w, r)
			return
		}
		switch r.Method {
		case http.MethodGet:
			h.handleListServers(w, r)
		case http.MethodPost:
			h.handleCreateServer(w, r)
		default:
			w.Header().Set("Allow", "GET, POST")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		}
	})

	apiMux.HandleFunc("/api/v1/servers/import", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleImportMCPJSON(w, r)
	})

	apiMux.HandleFunc("/api/v1/servers/discover-all", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleDiscoverAll(w, r)
	})

	apiMux.HandleFunc("/api/v1/tags", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		tags, err := h.repo.ListAllTags()
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to list tags"})
			return
		}
		writeJSON(w, http.StatusOK, map[string]interface{}{"tags": tags})
	})

	apiMux.HandleFunc("/api/v1/tools", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleListAllTools(w, r)
	})

	apiMux.HandleFunc("/api/v1/resources", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleListAllResources(w, r)
	})

	apiMux.HandleFunc("/api/v1/prompts", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleListAllPrompts(w, r)
	})

	// ── Me route (session validation) ────────────────────────────────────────
	apiMux.HandleFunc("/api/v1/me", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		email := auth.UserEmailFromContext(r.Context())
		if email == "" {
			http.Error(w, `{"error":"not authenticated"}`, http.StatusUnauthorized)
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"email": email})
	})

	// ── Token routes ─────────────────────────────────────────────────────────
	if h.tokenRepo != nil {
		apiMux.HandleFunc("/api/v1/tokens", h.handleTokens)
		apiMux.HandleFunc("/api/v1/tokens/", h.handleTokenByID)
	}

	// ── OAuth2 client routes ─────────────────────────────────────────────────
	if h.oauth2Repo != nil {
		apiMux.HandleFunc("/api/v1/oauth2/clients", h.handleOAuth2Clients)
		apiMux.HandleFunc("/api/v1/oauth2/clients/", h.handleOAuth2ClientByID)
	}

	// Routes avec {id} — on utilise un handler prefix pour capturer le pattern
	apiMux.HandleFunc("/api/v1/servers/", func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimPrefix(r.URL.Path, "/api/v1/servers/")
		if path == "" || path == "discover-all" || path == "import" {
			// Déjà géré par les routes exactes ci-dessus
			http.NotFound(w, r)
			return
		}

		parts := strings.SplitN(path, "/", 2)
		id := parts[0]
		action := ""
		if len(parts) > 1 {
			action = parts[1]
		}

		if id == "" {
			http.NotFound(w, r)
			return
		}

		switch action {
		case "":
			// /api/v1/servers/{id}
			switch r.Method {
			case http.MethodGet:
				h.handleGetServer(w, r)
			case http.MethodPut:
				h.handleUpdateServer(w, r)
			case http.MethodDelete:
				h.handleDeleteServer(w, r)
			default:
				w.Header().Set("Allow", "GET, PUT, DELETE")
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			}
		case "enable":
			if r.Method == http.MethodPost {
				h.handleEnableServer(w, r)
			} else {
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			}
		case "disable":
			if r.Method == http.MethodPost {
				h.handleDisableServer(w, r)
			} else {
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			}
		case "discover":
			if r.Method == http.MethodPost {
				h.handleDiscoverServer(w, r)
			} else {
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			}
		default:
			// Check for tool enable/disable: /api/v1/servers/{id}/tools/{toolName}/enable|disable
			if strings.HasPrefix(action, "tools/") {
				h.routeToolAction(w, r, id, strings.TrimPrefix(action, "tools/"))
				return
			}
			http.NotFound(w, r)
		}
	})

	// OpenAPI spec (hors middleware API pour ne pas nécessiter le préfixe /api/)
	mux.HandleFunc("/openapi.json", h.handleOpenAPI)

	// Applique les middlewares et monte sur le mux principal
	wrapped := chain(apiMux, recovery, requestLogger, jsonContentType, bodyLimit)
	mux.Handle("/api/", wrapped)
}

// routeToolAction routes /api/v1/servers/{id}/tools/{toolName}/{action} requests.
func (h *Handler) routeToolAction(w http.ResponseWriter, r *http.Request, serverID, toolPath string) {
	// toolPath is "{toolName}/enable" or "{toolName}/disable"
	parts := strings.SplitN(toolPath, "/", 2)
	if len(parts) != 2 || r.Method != http.MethodPost {
		http.NotFound(w, r)
		return
	}
	toolName := parts[0]
	action := parts[1]

	switch action {
	case "enable":
		h.handleEnableTool(w, r, serverID, toolName)
	case "disable":
		h.handleDisableTool(w, r, serverID, toolName)
	default:
		http.NotFound(w, r)
	}
}

// handleDiscoverAll re-discovers all active servers.
func (h *Handler) handleDiscoverAll(w http.ResponseWriter, r *http.Request) {
	active := true
	userEmail := auth.UserEmailFromContext(r.Context())
	servers, err := h.repo.ListAll(&active, "", userEmail)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to list servers"})
		return
	}

	results := make([]map[string]interface{}, 0, len(servers))
	for _, srv := range servers {
		result := map[string]interface{}{"id": srv.ID, "name": srv.Name}
		h.registry.Unregister(srv.ID)
		if err := h.gw.DiscoverAndRegister(r.Context(), srv.ID, srv.URL, parseAuthHeaders(srv.AuthHeaders)); err != nil {
			_ = h.repo.UpdateHealth(srv.ID, "unhealthy", err.Error())
			result["status"] = "failed"
			result["error"] = err.Error()
		} else {
			if backend := h.registry.FindByID(srv.ID); backend != nil {
				h.saveBackendCapabilities(srv.ID, backend)
			}
			result["status"] = "discovered"
		}
		results = append(results, result)
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"results": results})
}
