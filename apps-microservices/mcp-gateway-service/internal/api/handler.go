package api

import (
	"encoding/json"
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

	apiMux.HandleFunc("/api/v1/servers/generate-slugs", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleGenerateSlugs(w, r)
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
		role := auth.UserRoleFromContext(r.Context())
		displayName := auth.UserNameFromContext(r.Context())
		writeJSON(w, http.StatusOK, map[string]string{
			"email":        email,
			"display_name": displayName,
			"role":         role,
		})
	})

	// ── Token routes ─────────────────────────────────────────────────────────
	if h.tokenRepo != nil {
		apiMux.HandleFunc("/api/v1/tokens", h.handleTokens)
		apiMux.HandleFunc("/api/v1/tokens/", h.handleTokenByID)
	}

	// ── Leexi proxy routes (used by token + OAuth2 forms to populate the
	//    user/team picker). Always mounted; the handlers themselves return
	//    503 when LEEXI_INTERNAL_URL / LEEXI_ADMIN_TOKEN are unset.
	apiMux.HandleFunc("/api/v1/leexi/users", h.handleLeexiUsers)
	apiMux.HandleFunc("/api/v1/leexi/teams", h.handleLeexiTeams)

	// ── OAuth2 client routes ─────────────────────────────────────────────────
	if h.oauth2Repo != nil {
		apiMux.HandleFunc("/api/v1/oauth2/clients", h.handleOAuth2Clients)
		apiMux.HandleFunc("/api/v1/oauth2/clients/", h.handleOAuth2ClientByID)
	}

	// ── User management routes ────────────────────────────────────────────────
	if h.userRepo != nil {
		apiMux.HandleFunc("/api/v1/users", h.handleUsers)
		apiMux.HandleFunc("/api/v1/users/", h.handleUserByID)
	}

	// ── Audit log routes ──────────────────────────────────────────────────────
	if h.auditRepo != nil {
		apiMux.HandleFunc("/api/v1/audit-logs", h.handleAuditLogs)
	}

	// ── Install guide admin routes ────────────────────────────────────────────
	if h.installGuideRepo != nil {
		apiMux.HandleFunc("/api/v1/install-guides/executors", h.handleExecutors)
		apiMux.HandleFunc("/api/v1/install-guides/executors/", h.handleExecutorByID)
		apiMux.HandleFunc("/api/v1/install-guides/configs", h.handleConfigs)
		apiMux.HandleFunc("/api/v1/install-guides/configs/", h.handleConfigByID)
	}

	// ── Google Sheets import routes ──────────────────────────────────────────
	if h.googleTokenRepo != nil {
		apiMux.HandleFunc("/api/v1/google/auth-url", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodGet {
				w.Header().Set("Allow", "GET")
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
				return
			}
			h.handleGoogleAuthURL(w, r)
		})
		apiMux.HandleFunc("/api/v1/google/callback", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodGet {
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
				return
			}
			h.handleGoogleCallback(w, r)
		})
		apiMux.HandleFunc("/api/v1/google/disconnect", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodDelete {
				w.Header().Set("Allow", "DELETE")
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
				return
			}
			h.handleGoogleDisconnect(w, r)
		})
		apiMux.HandleFunc("/api/v1/google/status", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodGet {
				w.Header().Set("Allow", "GET")
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
				return
			}
			h.handleGoogleStatus(w, r)
		})
		apiMux.HandleFunc("/api/v1/google/spreadsheets", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodGet {
				w.Header().Set("Allow", "GET")
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
				return
			}
			h.handleListSpreadsheets(w, r)
		})
		apiMux.HandleFunc("/api/v1/google/sheets/info", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodPost {
				w.Header().Set("Allow", "POST")
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
				return
			}
			h.handleSheetInfo(w, r)
		})
		apiMux.HandleFunc("/api/v1/google/sheets/preview", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodPost {
				w.Header().Set("Allow", "POST")
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
				return
			}
			h.handleSheetPreview(w, r)
		})
		apiMux.HandleFunc("/api/v1/google/sheets/import", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodPost {
				w.Header().Set("Allow", "POST")
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
				return
			}
			h.handleSheetImport(w, r)
		})
		// Template-instance batch import from a Google Sheet. Admin-only via
		// the /api/v1/google/* prefix match in isAdminOnly; the handler itself
		// also guards on the templates feature wiring.
		apiMux.HandleFunc("/api/v1/google/sheets/import-instances", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodPost {
				w.Header().Set("Allow", "POST")
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
				return
			}
			h.handleImportInstancesFromSheet(w, r)
		})
	}

	// ── Templates + template instances ───────────────────────────────────────
	// GET /api/v1/templates (catalog) and /api/v1/templates/{slug} are open
	// to all authenticated users. Writes on /api/v1/template-instances are
	// gated to admin via isAdminOnly (see below). The handlers themselves
	// return 503 when the templates feature is not wired (Task 13 deps unset).
	apiMux.HandleFunc("/api/v1/templates", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleListTemplates(w, r)
	})
	// /templates/export and /templates/import are registered with exact paths
	// BEFORE the /templates/ slug catch-all below. net/http's ServeMux prefers
	// the longer literal match over a prefix pattern, so these never fall into
	// handleGetTemplate. Extra defence-in-depth: handleGetTemplate explicitly
	// rejects the slugs "export" and "import" to avoid accidental collisions
	// if the mux behaviour ever regresses.
	apiMux.HandleFunc("/api/v1/templates/export", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleExportTemplates(w, r)
	})
	apiMux.HandleFunc("/api/v1/templates/import", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleImportTemplates(w, r)
	})
	apiMux.HandleFunc("/api/v1/templates/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleGetTemplate(w, r)
	})

	apiMux.HandleFunc("/api/v1/template-instances", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			h.handleListInstances(w, r)
		case http.MethodPost:
			h.handleCreateInstance(w, r)
		default:
			w.Header().Set("Allow", "GET, POST")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		}
	})
	apiMux.HandleFunc("/api/v1/template-instances/", func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasSuffix(r.URL.Path, "/restart"):
			if r.Method != http.MethodPost {
				w.Header().Set("Allow", "POST")
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
				return
			}
			h.handleRestartInstance(w, r)
		case strings.HasSuffix(r.URL.Path, "/rotate-credentials"):
			if r.Method != http.MethodPost {
				w.Header().Set("Allow", "POST")
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
				return
			}
			h.handleRotateCredentials(w, r)
		default:
			switch r.Method {
			case http.MethodGet:
				h.handleGetInstance(w, r)
			case http.MethodDelete:
				h.handleDeleteInstance(w, r)
			default:
				w.Header().Set("Allow", "GET, DELETE")
				http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			}
		}
	})

	// Runner ↔ gateway sync endpoint. The runner authenticates with
	// X-Admin-Token; the handler itself enforces that. We add the path to
	// the auth middleware's public-prefix list so JWT is bypassed, and
	// isAdminOnly leaves it alone so the role check doesn't block it.
	apiMux.HandleFunc("/api/v1/internal/runner/sync", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleRunnerSync(w, r)
	})

	// ── Server icons routes ──────────────────────────────────────────────────
	apiMux.HandleFunc("/api/v1/server-icons", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			h.handleListIcons(w, r)
		case http.MethodPost:
			h.handleUploadIcon(w, r)
		default:
			w.Header().Set("Allow", "GET, POST")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		}
	})

	// ── Documentation image upload ───────────────────────────────────────────
	apiMux.HandleFunc("/api/v1/doc-images", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
			return
		}
		h.handleUploadImage(w, r)
	})

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

	// Public docs endpoints (no auth, no role check)
	mux.HandleFunc("/api/v1/public/docs", h.handleListDocServers)
	mux.HandleFunc("/api/v1/public/docs/", h.handleGetDocServer)

	// Public install guide endpoints (no auth)
	if h.installGuideRepo != nil {
		mux.HandleFunc("/api/v1/public/install-guides/executors", h.handlePublicExecutors)
		mux.HandleFunc("/api/v1/public/install-guides/executors/", h.handlePublicExecutorBySlug)
		mux.HandleFunc("/api/v1/public/install-guides/configs", h.handlePublicConfigs)
		mux.HandleFunc("/api/v1/public/install-guides/configs/", h.handlePublicConfigBySlug)
	}

	// Applique les middlewares et monte sur le mux principal
	wrapped := chain(apiMux, recovery, requestLogger, jsonContentType, bodyLimit, roleCheckMiddleware)
	mux.Handle("/api/", wrapped)
}

// roleCheckMiddleware enforces role-based access control on API routes.
func roleCheckMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Path
		method := r.Method
		role := auth.UserRoleFromContext(r.Context())

		// Routes that require admin only
		if isAdminOnly(path, method) {
			if auth.RoleLevelFor(role) < auth.RoleLevelFor(auth.RoleAdmin) {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusForbidden)
				json.NewEncoder(w).Encode(map[string]string{"error": "insufficient permissions"})
				return
			}
		} else if isReadOnlyPlus(path, method) {
			// Routes that require read-only or higher
			if auth.RoleLevelFor(role) < auth.RoleLevelFor(auth.RoleReadOnly) {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusForbidden)
				json.NewEncoder(w).Encode(map[string]string{"error": "insufficient permissions"})
				return
			}
		}
		// config-only and /api/v1/me: any authenticated user (role injected by auth middleware, always >= config-only)

		next.ServeHTTP(w, r)
	})
}

// isAdminOnly returns true when the path+method combination requires admin role.
func isAdminOnly(path, method string) bool {
	// User, audit, install guide, and Google management always require admin
	if strings.HasPrefix(path, "/api/v1/users") || strings.HasPrefix(path, "/api/v1/audit-logs") || strings.HasPrefix(path, "/api/v1/install-guides") || strings.HasPrefix(path, "/api/v1/google") {
		return true
	}
	// Server writes require admin
	if strings.HasPrefix(path, "/api/v1/servers") &&
		(method == http.MethodPost || method == http.MethodPut || method == http.MethodDelete) {
		return true
	}
	// Template-instance writes (create, delete, restart, rotate-credentials) require admin.
	// GET routes on /api/v1/templates and /api/v1/template-instances stay open to all authenticated users.
	if strings.HasPrefix(path, "/api/v1/template-instances") &&
		(method == http.MethodPost || method == http.MethodDelete) {
		return true
	}
	// Catalog import/export ship the whole seed definition, including inactive
	// rows and internal config — admin-only even for the GET export.
	if path == "/api/v1/templates/export" || path == "/api/v1/templates/import" {
		return true
	}
	return false
}

// isReadOnlyPlus returns true when the path+method combination requires at least read-only.
func isReadOnlyPlus(path, method string) bool {
	// Server reads are allowed for ALL authenticated users (config-only needs server list
	// for token/client creation forms). The Servers PAGE is hidden in the frontend sidebar
	// for config-only, but the API itself is open to all roles.
	// Aggregated views are also open to all authenticated users.
	return false
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
