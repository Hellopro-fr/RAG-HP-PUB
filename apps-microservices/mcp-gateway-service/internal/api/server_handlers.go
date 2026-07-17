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
	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/bddcatalog"
	"mcp-gateway/internal/config"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
	goGoogle "mcp-gateway/internal/google"
	"mcp-gateway/internal/crypto"
	"mcp-gateway/internal/leexiadmin"
	"mcp-gateway/internal/ringoveradmin"
	oauth2pkg "mcp-gateway/internal/oauth2"
	"mcp-gateway/internal/repository"
	"mcp-gateway/internal/runnerclient"
	"mcp-gateway/internal/slack"
	"mcp-gateway/internal/urlvalidation"
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
	// ringoverAdmin is the Ringover counterpart of leexiAdmin.
	ringoverAdmin *ringoveradmin.Client
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
	// slack is the optional Slack notification client. nil disables all
	// discovery-time notifications (ToolsRegression). Wired via SetSlack.
	slack *slack.Client
	// instructionRepo backs the /api/v1/llm-instructions CRUD. The same repo
	// is shared with scopetoken/oauth2 middleware to resolve per-scope
	// instructions at cache-miss time.
	instructionRepo *repository.InstructionRepo
	// BDD registry + upstream catalog client (Hellopro BDD tables onglet).
	// bddUsedRepo writes to the gateway-owned bdd_used_tables/fields tables;
	// bddCatalog is a read-only client to the upstream catalog HTTP API.
	// Both are nil until wired by main.go.
	bddUsedRepo *repository.BDDUsedRepo
	bddCatalog  *bddcatalog.Client
	// serverAuthRepo backs the /api/v1/server-authorizations admin CRUD.
	serverAuthRepo *repository.ServerAuthorizationRepo
	// zohoImportRepo backs the /api/v1/zoho-imports/admin REST endpoints.
	zohoImportRepo *repository.ZohoImportRepo
	// encryptor is used by handlers that encrypt/decrypt sensitive blobs (e.g.
	// auth_headers on the admin Zoho import row). nil when ENCRYPTION_KEY is unset.
	encryptor *crypto.Encryptor
}

// TokenCache is an interface for scope token cache operations.
type TokenCache interface {
	InvalidateAll()
}

// NewHandler creates a new API handler.
func NewHandler(
	repo *repository.ServerRepo,
	gw *gateway.Gateway,
	registry *gateway.Registry,
	allowInternalURLs bool,
	templateRepo *repository.TemplateRepo,
	instanceRepo *repository.InstanceRepo,
	runner *runnerclient.Client,
	cfg *config.Config,
) *Handler {
	return &Handler{
		repo:              repo,
		gw:                gw,
		registry:          registry,
		allowInternalURLs: allowInternalURLs,
		templateRepo:      templateRepo,
		instanceRepo:      instanceRepo,
		runner:            runner,
		config:            cfg,
	}
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

// SetRingoverAdmin wires the Ringover admin client used by the Ringover-scoped
// token filter UI and the proxy at /api/v1/ringover/*. Pass nil to disable.
func (h *Handler) SetRingoverAdmin(client *ringoveradmin.Client) {
	h.ringoverAdmin = client
}

// SetUploadDir sets the base directory for uploaded files.
func (h *Handler) SetUploadDir(dir string) {
	h.uploadDir = dir
}

// SetInstallGuideRepo sets the install guide repository.
func (h *Handler) SetInstallGuideRepo(repo *repository.InstallGuideRepo) {
	h.installGuideRepo = repo
}

// SetSlack wires the Slack notifications client. Pass nil to disable.
func (h *Handler) SetSlack(client *slack.Client) {
	h.slack = client
}

// SetInstructionRepo wires the LLM-instruction repository.
func (h *Handler) SetInstructionRepo(repo *repository.InstructionRepo) {
	h.instructionRepo = repo
}

// SetServerAuthorizationRepo wires the per-server full-access grants repo
// used by /api/v1/server-authorizations admin endpoints.
func (h *Handler) SetServerAuthorizationRepo(repo *repository.ServerAuthorizationRepo) {
	h.serverAuthRepo = repo
}

// SetEncryptor wires the AES-256-GCM encryptor used by handlers that store or
// read encrypted blobs (e.g. the admin Zoho import auth_headers).
func (h *Handler) SetEncryptor(enc *crypto.Encryptor) {
	h.encryptor = enc
}

// SetZohoImportRepo injects the ZohoImportRepo used by the admin REST handlers
// and the sheet-import dispatch.
func (h *Handler) SetZohoImportRepo(repo *repository.ZohoImportRepo) {
	h.zohoImportRepo = repo
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
			// Mirror tags into the registry so HasTag-driven dispatch
			// (zoho injector) sees them on first registration.
			if len(req.Tags) > 0 {
				h.registry.SetTags(id, req.Tags)
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

	// Admins see every server; non-admins are scoped to rows they created.
	// Scope-picker callers (token / OAuth2 creation forms) opt into the
	// full active-server set with `?include_all=true` — see
	// resolveListServersCreatorFilter for the rationale.
	servers, err := h.repo.ListAll(isActive, tag, resolveListServersCreatorFilter(r))
	if err != nil {
		log.Printf("[api] list servers error: %v", err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to list servers"})
		return
	}

	// Opt-in filter used by the docs-admin view: hide servers that originated
	// from a template (stdio instance OR http_batch sheet import). Template
	// catalogs manage their own docs flow, so exposing template-origin servers
	// in the docs admin would be confusing. The filter reads the first-class
	// template_slug column so both template paths are covered uniformly
	// without a join against template_instances.
	if r.URL.Query().Get("exclude_templates") == "true" {
		filtered := servers[:0]
		for _, s := range servers {
			if s.TemplateSlug == "" {
				filtered = append(filtered, s)
			}
		}
		servers = filtered
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
		// Mirror tags into the in-memory registry so downstream dispatch
		// (HasTag-driven zoho injector) picks up the change without waiting
		// for a re-discovery cycle.
		h.registry.SetTags(id, *req.Tags)
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
			// Re-discovery rebuilds the registry entry from the upstream
			// init result; tags only live in the DB so we have to push
			// them back into the registry after every re-discover.
			refreshedTags := make([]string, 0, len(refreshed.Tags))
			for _, t := range refreshed.Tags {
				refreshedTags = append(refreshedTags, t.Tag)
			}
			h.registry.SetTags(id, refreshedTags)
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

	// If this server is backed by a template instance, route through the
	// template-aware delete path: kill the runner subprocess + shred credentials
	// first, then delete both rows in one transaction. Otherwise the runner
	// would keep the subprocess alive forever and the SA JSON would persist on
	// tmpfs, while the template_instances row would point at a now-deleted
	// mcp_server_id.
	if h.instanceRepo != nil {
		if inst, ferr := h.instanceRepo.FindByMCPServerID(id); ferr == nil && inst != nil {
			if h.runner != nil {
				if kerr := h.runner.Kill(r.Context(), inst.ID); kerr != nil {
					log.Printf("[api] runner kill failed for template instance %s (continuing with DB delete): %v", inst.ID, kerr)
				}
			}
			if derr := h.instanceRepo.DeleteWithMCPServer(inst.ID); derr != nil {
				log.Printf("[api] template-aware delete failed for %s: %v", inst.ID, derr)
				writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to delete server"})
				return
			}
			w.WriteHeader(http.StatusNoContent)
			return
		}
	}

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

	prevToolCount, err := h.repo.SaveDiscoveredCapabilities(dbSrv)
	if err != nil {
		log.Printf("[api] save capabilities error for %s: %v", id, err)
		return
	}
	// Regression: backend used to expose tools and now exposes none. Almost
	// always a misconfigured backend — alert so an operator can investigate.
	if prevToolCount > 0 && len(dbSrv.Tools) == 0 {
		log.Printf("[api] tools regression on server %s: prev=%d, now=0", id, prevToolCount)
		name := dbSrv.ServerName
		if name == "" {
			name = backend.Name
		}
		h.slack.Notify(slack.ToolsRegressionEvent{
			ServerID:   id,
			ServerName: name,
			PrevCount:  prevToolCount,
		})
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
// Admins (role == "admin") bypass the ownership check so they can fix or
// remove a server created by another user.
// Returns false and writes a 403 response if ownership check fails.
func checkOwnership(r *http.Request, srv *db.MCPServer, w http.ResponseWriter) bool {
	if auth.UserRoleFromContext(r.Context()) == auth.RoleAdmin {
		return true
	}
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
		TemplateSlug:        srv.TemplateSlug,
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
