package api

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"log"
	"net/http"
	"regexp"
	"strings"
	"unicode"

	"github.com/google/uuid"
	"github.com/hellopro/mcp-gateway/internal/auth"
	"github.com/hellopro/mcp-gateway/internal/config"
	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/gateway"
	goGoogle "github.com/hellopro/mcp-gateway/internal/google"
	"github.com/hellopro/mcp-gateway/internal/leexiadmin"
	oauth2pkg "github.com/hellopro/mcp-gateway/internal/oauth2"
	"github.com/hellopro/mcp-gateway/internal/repository"
	"github.com/hellopro/mcp-gateway/internal/runnerclient"
	"github.com/hellopro/mcp-gateway/internal/urlvalidation"
)

var alphanumericRe = regexp.MustCompile(`^[a-zA-Z0-9]+$`)
var nonSlugRe = regexp.MustCompile(`[^a-z0-9-]+`)
var multiDashRe = regexp.MustCompile(`-{2,}`)

// generateDocSlug creates a URL-safe slug from a name and appends a short hash for uniqueness.
func generateDocSlug(name, id string) string {
	// Lowercase and replace non-alphanumeric with dashes
	slug := strings.ToLower(name)
	// Replace common accented chars
	replacer := strings.NewReplacer(
		"é", "e", "è", "e", "ê", "e", "ë", "e",
		"à", "a", "â", "a", "ä", "a",
		"ù", "u", "û", "u", "ü", "u",
		"ô", "o", "ö", "o",
		"î", "i", "ï", "i",
		"ç", "c",
		" ", "-",
	)
	slug = replacer.Replace(slug)
	// Remove remaining non-slug characters
	slug = nonSlugRe.ReplaceAllString(slug, "")
	slug = multiDashRe.ReplaceAllString(slug, "-")
	slug = strings.Trim(slug, "-")
	// Remove any remaining unicode
	clean := make([]rune, 0, len(slug))
	for _, r := range slug {
		if unicode.IsLetter(r) || unicode.IsDigit(r) || r == '-' {
			clean = append(clean, r)
		}
	}
	slug = string(clean)
	if slug == "" {
		slug = "server"
	}
	// Append short hash from ID for uniqueness
	hash := sha256.Sum256([]byte(id))
	slug = slug + "-" + hex.EncodeToString(hash[:])[:6]
	return slug
}

// Handler holds dependencies for the REST API.
type Handler struct {
	repo              *repository.ServerRepo
	tokenRepo         *repository.TokenRepo
	tokenCache        TokenCache
	oauth2Repo        *repository.OAuth2Repo
	oauth2Cache       *oauth2pkg.Cache
	gw                *gateway.Gateway
	registry          *gateway.Registry
	allowInternalURLs bool
	userRepo          *repository.UserRepo
	auditRepo         *repository.AuditRepo
	// leexiAdmin is the in-cluster client used to resolve users/teams for the
	// per-token Leexi filter UI and the runtime header injection. nil when the
	// integration is disabled (LEEXI_INTERNAL_URL or LEEXI_ADMIN_TOKEN unset).
	leexiAdmin *leexiadmin.Client
	// uploadDir is the base directory for uploaded files (icons, etc.)
	uploadDir string
	// installGuideRepo is the repository for install guide CRUD (executors + configs).
	installGuideRepo *repository.InstallGuideRepo
	// Google Sheets import
	googleTokenRepo *repository.GoogleTokenRepo
	googleOAuth     *goGoogle.OAuthClient
	// Template instances (Google templates dynamic secrets feature).
	// These stay zero-valued (nil) until Task 13 wires them in main.go.
	templateRepo *repository.TemplateRepo
	instanceRepo *repository.InstanceRepo
	runner       *runnerclient.Client
	config       *config.Config
}

// TokenCache is an interface for scope token cache operations.
type TokenCache interface {
	InvalidateAll()
}

// NewHandler creates a new API handler.
func NewHandler(repo *repository.ServerRepo, gw *gateway.Gateway, registry *gateway.Registry, allowInternalURLs bool) *Handler {
	return &Handler{repo: repo, gw: gw, registry: registry, allowInternalURLs: allowInternalURLs}
}

// SetTokenRepo sets the token repository for token CRUD operations.
func (h *Handler) SetTokenRepo(repo *repository.TokenRepo, cache TokenCache) {
	h.tokenRepo = repo
	h.tokenCache = cache
}

// SetOAuth2Repo sets the OAuth2 repository for client CRUD operations.
func (h *Handler) SetOAuth2Repo(repo *repository.OAuth2Repo, cache *oauth2pkg.Cache) {
	h.oauth2Repo = repo
	h.oauth2Cache = cache
}

// SetUserRepo sets the user repository for RBAC user management.
func (h *Handler) SetUserRepo(repo *repository.UserRepo) {
	h.userRepo = repo
}

// SetAuditRepo sets the audit repository for audit log access.
func (h *Handler) SetAuditRepo(repo *repository.AuditRepo) {
	h.auditRepo = repo
}

// SetLeexiAdmin wires the Leexi admin client used by the Leexi-scoped token
// filter UI and the proxy at /api/v1/leexi/*. Pass nil to disable.
func (h *Handler) SetLeexiAdmin(client *leexiadmin.Client) {
	h.leexiAdmin = client
}

// SetUploadDir sets the base directory for uploaded files.
func (h *Handler) SetUploadDir(dir string) {
	h.uploadDir = dir
}

// SetInstallGuideRepo sets the install guide repository.
func (h *Handler) SetInstallGuideRepo(repo *repository.InstallGuideRepo) {
	h.installGuideRepo = repo
}

// ── Create Server ─────────────────────────────────────────────────────────────

func (h *Handler) handleCreateServer(w http.ResponseWriter, r *http.Request) {
	var req CreateServerRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
		return
	}
	if req.Name == "" || req.URL == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "name and url are required"})
		return
	}

	// SSRF protection: validate that the URL does not point to internal/private ranges
	if err := urlvalidation.ValidateServerURL(req.URL, h.allowInternalURLs); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid server URL: " + err.Error()})
		return
	}

	pref := req.TransportPreference
	if pref == "" {
		pref = "auto"
	}
	if pref != "auto" && pref != "sse" && pref != "streamable-http" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "transport_preference must be auto, sse, or streamable-http"})
		return
	}

	mcpTransport := req.MCPTransport
	if mcpTransport == "" {
		mcpTransport = "http"
	}
	if mcpTransport != "http" && mcpTransport != "sse" && mcpTransport != "stdio" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "mcp_transport must be http, sse, or stdio"})
		return
	}

	// Validate tool prefix: must be alphanumeric if provided
	if req.ToolPrefix != "" && !alphanumericRe.MatchString(req.ToolPrefix) {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "tool_prefix must contain only alphanumeric characters (a-z, A-Z, 0-9)"})
		return
	}

	id := uuid.New().String()
	srv := db.MCPServer{
		ID:                  id,
		Name:                req.Name,
		URL:                 strings.TrimRight(req.URL, "/"),
		TransportPreference: pref,
		ConnectTimeoutMs:    10000,
		IsActive:            true,
		HealthStatus:        "unknown",
		MCPTransport:        mcpTransport,
		MCPCommand:          req.MCPCommand,
		ToolPrefix:          req.ToolPrefix,
		Icon:                req.Icon,
		DocSlug:             generateDocSlug(req.Name, id),
		CreatedBy:           auth.UserEmailFromContext(r.Context()),
	}
	if req.ConnectTimeoutMs != nil {
		srv.ConnectTimeoutMs = *req.ConnectTimeoutMs
	}
	if len(req.MCPArgs) > 0 {
		srv.MCPArgs, _ = json.Marshal(req.MCPArgs)
	}
	if len(req.MCPEnv) > 0 {
		srv.MCPEnv, _ = json.Marshal(req.MCPEnv)
	}

	// Encode auth headers as JSON bytes for encryption
	if len(req.AuthHeaders) > 0 {
		b, _ := json.Marshal(req.AuthHeaders)
		srv.AuthHeaders = b
	}

	if err := h.repo.Create(&srv); err != nil {
		if strings.Contains(err.Error(), "Duplicate") {
			writeJSON(w, http.StatusConflict, ErrorResponse{Error: "a server with this URL already exists"})
			return
		}
		log.Printf("[api] create server error: %v", err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to create server"})
		return
	}

	// Sauvegarde les tags
	if len(req.Tags) > 0 {
		if err := h.repo.SaveTags(id, req.Tags); err != nil {
			log.Printf("[api] save tags error: %v", err)
		}
	}

	// Découverte automatique
	// Use req.AuthHeaders directly because repo.Create() encrypted srv.AuthHeaders in-place
	if req.AutoDiscover {
		log.Printf("[api] auto-discover for %s with %d auth headers", srv.URL, len(req.AuthHeaders))
		if err := h.gw.DiscoverAndRegister(r.Context(), id, srv.URL, req.AuthHeaders); err != nil {
			log.Printf("[api] auto-discover failed for %s: %v", srv.URL, err)
			_ = h.repo.UpdateHealth(id, "unhealthy", err.Error())
		} else {
			// Set the tool prefix on the registered backend
			if req.ToolPrefix != "" {
				h.registry.SetToolPrefix(id, req.ToolPrefix)
			}
			// Récupère le serveur mis à jour pour sauvegarder les capabilities
			if backend := h.registry.FindByID(id); backend != nil {
				h.saveBackendCapabilities(id, backend)
			}
		}
	}

	// Récupère le serveur complet pour la réponse
	created, err := h.repo.GetByID(id)
	if err != nil {
		log.Printf("[api] get created server error: %v", err)
		writeJSON(w, http.StatusCreated, map[string]string{"id": id})
		return
	}
	writeJSON(w, http.StatusCreated, toServerResponse(created))
}

// ── List Servers ──────────────────────────────────────────────────────────────

func (h *Handler) handleListServers(w http.ResponseWriter, r *http.Request) {
	var isActive *bool
	if v := r.URL.Query().Get("is_active"); v != "" {
		b := v == "true"
		isActive = &b
	}
	tag := r.URL.Query().Get("tag")

	servers, err := h.repo.ListAll(isActive, tag, "")
	if err != nil {
		log.Printf("[api] list servers error: %v", err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to list servers"})
		return
	}

	resp := ListServersResponse{
		Servers: make([]ServerResponse, 0, len(servers)),
		Total:   len(servers),
	}
	for i := range servers {
		for _, t := range servers[i].Tools {
			if !t.IsActive {
				log.Printf("[api] list: server %s tool %s is_active=%v", servers[i].Name, t.Name, t.IsActive)
			}
		}
		resp.Servers = append(resp.Servers, toServerResponse(&servers[i]))
	}
	writeJSON(w, http.StatusOK, resp)
}

// ── Get Server ────────────────────────────────────────────────────────────────

func (h *Handler) handleGetServer(w http.ResponseWriter, r *http.Request) {
	id := extractID(r)
	srv, err := h.repo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "server not found"})
		return
	}
	if !checkOwnership(r, srv, w) {
		return
	}
	writeJSON(w, http.StatusOK, toServerDetailResponse(srv))
}

// ── Update Server ─────────────────────────────────────────────────────────────

func (h *Handler) handleUpdateServer(w http.ResponseWriter, r *http.Request) {
	id := extractID(r)

	existing, err := h.repo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "server not found"})
		return
	}
	if !checkOwnership(r, existing, w) {
		return
	}

	var req UpdateServerRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
		return
	}

	updates := make(map[string]interface{})
	urlChanged := false
	authChanged := false

	if req.Name != nil {
		updates["name"] = *req.Name
	}
	if req.URL != nil {
		// SSRF protection: validate that the new URL does not point to internal/private ranges
		if err := urlvalidation.ValidateServerURL(*req.URL, h.allowInternalURLs); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid server URL: " + err.Error()})
			return
		}
		updates["url"] = strings.TrimRight(*req.URL, "/")
		urlChanged = true
	}
	if len(req.AuthHeaders) > 0 {
		b, _ := json.Marshal(req.AuthHeaders)
		tmpSrv := &db.MCPServer{AuthHeaders: b}
		if err := h.repo.EncryptAuthHeaders(tmpSrv); err == nil {
			updates["auth_headers"] = tmpSrv.AuthHeaders
		} else {
			updates["auth_headers"] = b
		}
		authChanged = true
	}
	if req.TransportPreference != nil {
		updates["transport_preference"] = *req.TransportPreference
	}
	if req.ConnectTimeoutMs != nil {
		updates["connect_timeout_ms"] = *req.ConnectTimeoutMs
	}
	if req.MCPTransport != nil {
		updates["mcp_transport"] = *req.MCPTransport
	}
	if req.MCPCommand != nil {
		updates["mcp_command"] = *req.MCPCommand
	}
	if req.MCPArgs != nil {
		b, _ := json.Marshal(*req.MCPArgs)
		updates["mcp_args"] = b
	}
	if len(req.MCPEnv) > 0 {
		b, _ := json.Marshal(req.MCPEnv)
		updates["mcp_env"] = b
	}
	if req.ToolPrefix != nil {
		if *req.ToolPrefix != "" && !alphanumericRe.MatchString(*req.ToolPrefix) {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "tool_prefix must contain only alphanumeric characters (a-z, A-Z, 0-9)"})
			return
		}
		updates["tool_prefix"] = *req.ToolPrefix
	}
	if req.Icon != nil {
		updates["icon"] = *req.Icon
	}
	if req.DocSlug != nil {
		// Check for duplicate doc_slug (skip if empty — clearing is always allowed)
		if *req.DocSlug != "" {
			existing, err := h.repo.GetByDocSlug(*req.DocSlug)
			if err == nil && existing != nil && existing.ID != id {
				writeJSON(w, http.StatusConflict, ErrorResponse{Error: "doc_slug '" + *req.DocSlug + "' is already used by server '" + existing.Name + "'"})
				return
			}
		}
		updates["doc_slug"] = *req.DocSlug
	}
	if req.DocDescription != nil {
		updates["doc_description"] = decodeEntitiesString(*req.DocDescription)
	}
	if req.DocConfigGuide != nil {
		updates["doc_config_guide"] = decodeEntitiesJSON(*req.DocConfigGuide)
	}

	if len(updates) > 0 {
		if err := h.repo.Update(id, updates); err != nil {
			log.Printf("[api] update server error: %v", err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to update server"})
			return
		}
	}

	if req.Tags != nil {
		if err := h.repo.SaveTags(id, *req.Tags); err != nil {
			log.Printf("[api] save tags error: %v", err)
		}
	}

	// Update tool prefix on the in-memory registry if changed (even without re-discovery)
	if req.ToolPrefix != nil {
		h.registry.SetToolPrefix(id, *req.ToolPrefix)
	}

	// Re-discover if URL or auth headers changed
	if (urlChanged || authChanged) && existing.IsActive {
		h.registry.Unregister(id)
		// Re-read from DB to get the fully updated record
		refreshed, _ := h.repo.GetByID(id)
		if err := h.gw.DiscoverAndRegister(r.Context(), id, refreshed.URL, parseAuthHeaders(refreshed.AuthHeaders)); err != nil {
			log.Printf("[api] re-discover failed for %s: %v", refreshed.URL, err)
			_ = h.repo.UpdateHealth(id, "unhealthy", err.Error())
		} else {
			h.registry.SetToolPrefix(id, refreshed.ToolPrefix)
			if backend := h.registry.FindByID(id); backend != nil {
				h.saveBackendCapabilities(id, backend)
			}
		}
	}

	updated, _ := h.repo.GetByID(id)
	writeJSON(w, http.StatusOK, toServerResponse(updated))
}

// ── Delete Server ─────────────────────────────────────────────────────────────

func (h *Handler) handleDeleteServer(w http.ResponseWriter, r *http.Request) {
	id := extractID(r)
	srv, err := h.repo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "server not found"})
		return
	}
	if !checkOwnership(r, srv, w) {
		return
	}
	h.registry.Unregister(id)
	if err := h.repo.Delete(id); err != nil {
		log.Printf("[api] delete server error: %v", err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to delete server"})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── Enable / Disable ──────────────────────────────────────────────────────────

func (h *Handler) handleEnableServer(w http.ResponseWriter, r *http.Request) {
	id := extractID(r)
	srv, err := h.repo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "server not found"})
		return
	}
	if !checkOwnership(r, srv, w) {
		return
	}

	if err := h.repo.SetActive(id, true); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to enable server"})
		return
	}

	// Découvrir et enregistrer
	if err := h.gw.DiscoverAndRegister(r.Context(), id, srv.URL, parseAuthHeaders(srv.AuthHeaders)); err != nil {
		log.Printf("[api] discover on enable failed for %s: %v", srv.URL, err)
		_ = h.repo.UpdateHealth(id, "unhealthy", err.Error())
	} else {
		h.registry.SetToolPrefix(id, srv.ToolPrefix)
		if backend := h.registry.FindByID(id); backend != nil {
			h.saveBackendCapabilities(id, backend)
		}
	}

	updated, _ := h.repo.GetByID(id)
	writeJSON(w, http.StatusOK, toServerResponse(updated))
}

func (h *Handler) handleDisableServer(w http.ResponseWriter, r *http.Request) {
	id := extractID(r)
	srv, err := h.repo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "server not found"})
		return
	}
	if !checkOwnership(r, srv, w) {
		return
	}
	if err := h.repo.SetActive(id, false); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to disable server"})
		return
	}
	h.registry.Unregister(id)

	updated, _ := h.repo.GetByID(id)
	writeJSON(w, http.StatusOK, toServerResponse(updated))
}

// ── Discover ──────────────────────────────────────────────────────────────────

func (h *Handler) handleDiscoverServer(w http.ResponseWriter, r *http.Request) {
	id := extractID(r)
	srv, err := h.repo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "server not found"})
		return
	}
	if !checkOwnership(r, srv, w) {
		return
	}

	h.registry.Unregister(id)
	if err := h.gw.DiscoverAndRegister(r.Context(), id, srv.URL, parseAuthHeaders(srv.AuthHeaders)); err != nil {
		_ = h.repo.UpdateHealth(id, "unhealthy", err.Error())
		// Clear stale tools/resources/prompts so UI doesn't show outdated data
		_ = h.repo.ClearCapabilities(id)
		updated, _ := h.repo.GetByID(id)
		writeJSON(w, http.StatusBadGateway, map[string]interface{}{
			"error":  "discovery failed: " + err.Error(),
			"server": toServerDetailResponse(updated),
		})
		return
	}

	h.registry.SetToolPrefix(id, srv.ToolPrefix)
	if backend := h.registry.FindByID(id); backend != nil {
		h.saveBackendCapabilities(id, backend)
	}

	updated, _ := h.repo.GetByID(id)
	for _, t := range updated.Tools {
		if !t.IsActive {
			log.Printf("[api] discover: tool %s (server %s) is_active=%v", t.Name, id, t.IsActive)
		}
	}
	writeJSON(w, http.StatusOK, toServerDetailResponse(updated))
}

// ── Aggregated listings ───────────────────────────────────────────────────────

func (h *Handler) handleListAllTools(w http.ResponseWriter, r *http.Request) {
	tools := h.registry.MergedTools()
	writeJSON(w, http.StatusOK, map[string]interface{}{"tools": tools, "total": len(tools)})
}

func (h *Handler) handleListAllResources(w http.ResponseWriter, r *http.Request) {
	resources := h.registry.MergedResources()
	writeJSON(w, http.StatusOK, map[string]interface{}{"resources": resources, "total": len(resources)})
}

func (h *Handler) handleListAllPrompts(w http.ResponseWriter, r *http.Request) {
	prompts := h.registry.MergedPrompts()
	writeJSON(w, http.StatusOK, map[string]interface{}{"prompts": prompts, "total": len(prompts)})
}

// ── Enable / Disable Tool ─────────────────────────────────────────────────

func (h *Handler) handleEnableTool(w http.ResponseWriter, r *http.Request, serverID, toolName string) {
	srv, err := h.repo.GetByID(serverID)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "server not found"})
		return
	}
	if !checkOwnership(r, srv, w) {
		return
	}
	// Strip prefix: API receives prefixed name (e.g. "ringovers_get_calls"),
	// but DB stores unprefixed name (e.g. "get_calls")
	dbToolName := gateway.UnprefixedToolName(srv.ToolPrefix, toolName)
	if err := h.repo.SetToolActive(serverID, dbToolName, true); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to enable tool"})
		return
	}
	h.registry.SetToolActive(serverID, dbToolName, true)
	updated, _ := h.repo.GetByID(serverID)
	writeJSON(w, http.StatusOK, toServerResponse(updated))
}

func (h *Handler) handleDisableTool(w http.ResponseWriter, r *http.Request, serverID, toolName string) {
	srv, err := h.repo.GetByID(serverID)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "server not found"})
		return
	}
	if !checkOwnership(r, srv, w) {
		return
	}
	// Strip prefix: API receives prefixed name, DB stores unprefixed name
	dbToolName := gateway.UnprefixedToolName(srv.ToolPrefix, toolName)
	if err := h.repo.SetToolActive(serverID, dbToolName, false); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to disable tool"})
		return
	}
	h.registry.SetToolActive(serverID, dbToolName, false)
	updated, _ := h.repo.GetByID(serverID)
	writeJSON(w, http.StatusOK, toServerResponse(updated))
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func (h *Handler) saveBackendCapabilities(id string, backend *gateway.BackendServer) {
	capsRaw, _ := json.Marshal(backend.Capabilities)
	dbSrv := &db.MCPServer{
		ID:            id,
		MessageURL:    backend.MessageURL,
		TransportType: backend.TransportType,
		ServerName:    backend.Name,
		ServerVersion: backend.Version,
		CapabilitiesRaw: capsRaw,
	}
	for _, t := range backend.Tools {
		dbSrv.Tools = append(dbSrv.Tools, db.ServerTool{
			Name:        t.Name,
			Description: t.Description,
			InputSchema: t.InputSchema,
		})
	}
	for _, res := range backend.Resources {
		dbSrv.Resources = append(dbSrv.Resources, db.ServerResource{
			URI:         res.URI,
			Name:        res.Name,
			Description: res.Description,
			MimeType:    res.MimeType,
		})
	}
	for _, p := range backend.Prompts {
		sp := db.ServerPrompt{
			Name:        p.Name,
			Description: p.Description,
		}
		for _, a := range p.Arguments {
			sp.Arguments = append(sp.Arguments, db.PromptArgument{
				Name:        a.Name,
				Description: a.Description,
				IsRequired:  a.Required,
			})
		}
		dbSrv.Prompts = append(dbSrv.Prompts, sp)
	}

	if err := h.repo.SaveDiscoveredCapabilities(dbSrv); err != nil {
		log.Printf("[api] save capabilities error for %s: %v", id, err)
		return
	}
	// Sync tool active states from DB back to registry (SaveDiscoveredCapabilities
	// preserves is_active for existing tools, but the registry has all tools as active)
	toolStates := make(map[string]bool, len(dbSrv.Tools))
	for _, t := range dbSrv.Tools {
		toolStates[t.Name] = t.IsActive
	}
	h.registry.SyncToolActiveStates(id, toolStates)
}

// checkOwnership verifies the current user owns the server.
// If auth is disabled (no user in context), access is allowed.
// Returns false and writes a 403 response if ownership check fails.
func checkOwnership(r *http.Request, srv *db.MCPServer, w http.ResponseWriter) bool {
	userEmail := auth.UserEmailFromContext(r.Context())
	if userEmail == "" {
		// Auth disabled — no ownership filtering
		return true
	}
	if srv.CreatedBy != "" && srv.CreatedBy != userEmail {
		writeJSON(w, http.StatusForbidden, ErrorResponse{Error: "you do not have access to this server"})
		return false
	}
	return true
}

func extractID(r *http.Request) string {
	// URL pattern: /api/v1/servers/{id} or /api/v1/servers/{id}/action
	path := strings.TrimPrefix(r.URL.Path, "/api/v1/servers/")
	parts := strings.SplitN(path, "/", 2)
	if len(parts) > 0 {
		return parts[0]
	}
	return ""
}

func toServerResponse(srv *db.MCPServer) ServerResponse {
	tags := make([]string, 0, len(srv.Tags))
	for _, t := range srv.Tags {
		tags = append(tags, t.Tag)
	}

	// Decode MCP JSON fields
	var mcpArgs []string
	if len(srv.MCPArgs) > 0 {
		json.Unmarshal(srv.MCPArgs, &mcpArgs)
	}
	var mcpEnv map[string]string
	if len(srv.MCPEnv) > 0 {
		json.Unmarshal(srv.MCPEnv, &mcpEnv)
	}

	toolNames := make([]ToolSummary, 0, len(srv.Tools))
	for _, t := range srv.Tools {
		toolNames = append(toolNames, ToolSummary{
			Name:        gateway.PrefixedToolName(srv.ToolPrefix, t.Name),
			Description: t.Description,
			IsActive:    t.IsActive,
		})
	}

	return ServerResponse{
		ID:                  srv.ID,
		Name:                srv.Name,
		URL:                 srv.URL,
		MessageURL:          srv.MessageURL,
		TransportType:       srv.TransportType,
		ServerName:          srv.ServerName,
		ServerVersion:       srv.ServerVersion,
		TransportPreference: srv.TransportPreference,
		ConnectTimeoutMs:    srv.ConnectTimeoutMs,
		IsActive:            srv.IsActive,
		HealthStatus:        srv.HealthStatus,
		LastHealthCheck:     srv.LastHealthCheck,
		LastError:           srv.LastError,
		LastDiscoveredAt:    srv.LastDiscoveredAt,
		ToolPrefix:          srv.ToolPrefix,
		Icon:                srv.Icon,
		ToolsCount:          len(srv.Tools),
		ToolNames:           toolNames,
		ResourcesCount:      len(srv.Resources),
		PromptsCount:        len(srv.Prompts),
		MCPTransport:        srv.MCPTransport,
		MCPCommand:          srv.MCPCommand,
		MCPArgs:             mcpArgs,
		MCPEnv:              mcpEnv,
		HasAuthHeaders:      len(srv.AuthHeaders) > 0,
		DocSlug:             srv.DocSlug,
		DocDescription:      srv.DocDescription,
		DocConfigGuide:      srv.DocConfigGuide,
		CreatedBy:           srv.CreatedBy,
		Tags:                tags,
		CreatedAt:           srv.CreatedAt,
		UpdatedAt:           srv.UpdatedAt,
	}
}

func toServerDetailResponse(srv *db.MCPServer) ServerDetailResponse {
	resp := ServerDetailResponse{
		ServerResponse: toServerResponse(srv),
		Tools:          make([]ToolResponse, 0, len(srv.Tools)),
		Resources:      make([]ResourceResponse, 0, len(srv.Resources)),
		Prompts:        make([]PromptResponse, 0, len(srv.Prompts)),
	}
	for _, t := range srv.Tools {
		resp.Tools = append(resp.Tools, ToolResponse{
			Name:        t.Name,
			Description: t.Description,
			InputSchema: t.InputSchema,
			IsActive:    t.IsActive,
		})
	}
	for _, res := range srv.Resources {
		resp.Resources = append(resp.Resources, ResourceResponse{
			URI:         res.URI,
			Name:        res.Name,
			Description: res.Description,
			MimeType:    res.MimeType,
		})
	}
	for _, p := range srv.Prompts {
		pr := PromptResponse{
			Name:        p.Name,
			Description: p.Description,
			Arguments:   make([]PromptArgumentResponse, 0, len(p.Arguments)),
		}
		for _, a := range p.Arguments {
			pr.Arguments = append(pr.Arguments, PromptArgumentResponse{
				Name:        a.Name,
				Description: a.Description,
				IsRequired:  a.IsRequired,
			})
		}
		resp.Prompts = append(resp.Prompts, pr)
	}
	return resp
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

// parseAuthHeaders extracts auth headers from the DB model's encrypted []byte field.
func parseAuthHeaders(raw []byte) map[string]string {
	if len(raw) == 0 {
		return nil
	}
	var headers map[string]string
	if err := json.Unmarshal(raw, &headers); err != nil {
		return nil
	}
	if len(headers) == 0 {
		return nil
	}
	return headers
}
