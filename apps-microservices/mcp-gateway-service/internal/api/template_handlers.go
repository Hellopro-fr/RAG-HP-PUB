package api

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/hellopro/mcp-gateway/internal/auth"
	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/runnerclient"
	"github.com/hellopro/mcp-gateway/internal/validation"
	"gorm.io/gorm"
)

// handleListTemplates returns the catalog of available templates with live
// instance counts per slug.
func (h *Handler) handleListTemplates(w http.ResponseWriter, r *http.Request) {
	if h.templateRepo == nil || h.instanceRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}
	templates, err := h.templateRepo.ListActive()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "list templates: " + err.Error()})
		return
	}
	counts, err := h.instanceRepo.CountsByTemplate()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "count: " + err.Error()})
		return
	}
	out := make([]TemplateResponse, 0, len(templates))
	for _, t := range templates {
		out = append(out, toTemplateResponse(t, counts[t.Slug]))
	}
	writeJSON(w, http.StatusOK, map[string]any{"templates": out})
}

// handleGetTemplate returns a single template by slug.
func (h *Handler) handleGetTemplate(w http.ResponseWriter, r *http.Request) {
	if h.templateRepo == nil || h.instanceRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}
	slug := strings.TrimPrefix(r.URL.Path, "/api/v1/templates/")
	if slug == "" || strings.Contains(slug, "/") {
		http.NotFound(w, r)
		return
	}
	t, err := h.templateRepo.GetBySlug(slug)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "template not found"})
			return
		}
		log.Printf("[templates] get template %s failed: %v", slug, err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "template lookup failed"})
		return
	}
	counts, _ := h.instanceRepo.CountsByTemplate()
	writeJSON(w, http.StatusOK, toTemplateResponse(*t, counts[t.Slug]))
}

func toTemplateResponse(t db.Template, count int) TemplateResponse {
	return TemplateResponse{
		Slug:             t.Slug,
		Name:             t.Name,
		Description:      t.Description,
		Icon:             t.Icon,
		StdioCommand:     t.StdioCommand,
		StdioArgs:        t.StdioArgs,
		DefaultEnv:       t.DefaultEnv,
		RequiredExtraEnv: t.RequiredExtraEnv,
		ToolPrefix:       t.ToolPrefix,
		Tags:             t.Tags,
		InstanceCount:    count,
	}
}

// handleListInstances returns all template instances, optionally filtered by
// the `template_slug` query parameter.
func (h *Handler) handleListInstances(w http.ResponseWriter, r *http.Request) {
	if h.instanceRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}
	slug := r.URL.Query().Get("template_slug")
	var instances []db.TemplateInstance
	var err error
	if slug != "" {
		instances, err = h.instanceRepo.ListByTemplate(slug)
	} else {
		instances, err = h.instanceRepo.ListAll()
	}
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	out := make([]TemplateInstanceResponse, 0, len(instances))
	for _, inst := range instances {
		out = append(out, toInstanceResponse(inst, "", ""))
	}
	writeJSON(w, http.StatusOK, map[string]any{"instances": out})
}

// handleGetInstance returns a single template instance by ID, enriched with
// the live stderr tail from the runner (best-effort).
func (h *Handler) handleGetInstance(w http.ResponseWriter, r *http.Request) {
	if h.instanceRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}
	id := strings.TrimPrefix(r.URL.Path, "/api/v1/template-instances/")
	id = strings.TrimSuffix(id, "/")
	if id == "" || strings.Contains(id, "/") {
		http.NotFound(w, r)
		return
	}
	inst, err := h.instanceRepo.GetByID(id)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instance not found"})
			return
		}
		log.Printf("[templates] get instance %s failed: %v", id, err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "instance lookup failed"})
		return
	}
	// Surface the live URL without the Tools/Resources/Prompts/Tags preload that
	// GetByID triggers — we only need the address here.
	var serverURL string
	if h.repo != nil {
		if u, uerr := h.repo.GetURL(inst.MCPServerID); uerr == nil {
			serverURL = u
		}
	}
	// Best-effort: fetch live stderr tail from runner.
	tail := ""
	if h.runner != nil {
		if statuses, rerr := h.runner.List(r.Context()); rerr == nil {
			for _, s := range statuses {
				if s.ID == id {
					tail = s.StderrTail
					break
				}
			}
		}
	}
	writeJSON(w, http.StatusOK, toInstanceResponse(*inst, tail, serverURL))
}

func toInstanceResponse(inst db.TemplateInstance, stderrTail, url string) TemplateInstanceResponse {
	return TemplateInstanceResponse{
		ID:              inst.ID,
		TemplateSlug:    inst.TemplateSlug,
		Name:            inst.Name,
		ExtraEnv:        inst.ExtraEnv,
		RunnerPort:      inst.RunnerPort,
		RunnerStatus:    inst.RunnerStatus,
		RunnerLastError: inst.RunnerLastError,
		MCPServerID:     inst.MCPServerID,
		URL:             url,
		CreatedBy:       inst.CreatedBy,
		CreatedAt:       inst.CreatedAt,
		UpdatedAt:       inst.UpdatedAt,
		StderrTail:      stderrTail,
	}
}

func (h *Handler) handleCreateInstance(w http.ResponseWriter, r *http.Request) {
	// Dependencies must all be wired (done in Task 13) for this to work.
	if h.templateRepo == nil || h.instanceRepo == nil || h.repo == nil || h.runner == nil || h.config == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}

	// Multipart: fields "template_slug", "name", "extra_env" (JSON string), file "credentials"
	// 16KB SA JSON + 48KB for non-file fields (name, template_slug, extra_env).
	if err := r.ParseMultipartForm(int64(validation.MaxSAJSONSize) + 48*1024); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "multipart parse: " + err.Error()})
		return
	}

	slug := r.FormValue("template_slug")
	name := strings.TrimSpace(r.FormValue("name"))
	if slug == "" || name == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "template_slug and name required"})
		return
	}
	tpl, err := h.templateRepo.GetBySlug(slug)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "unknown template: " + slug})
		return
	}

	// Parse extra_env
	var extraEnv map[string]string
	if raw := r.FormValue("extra_env"); raw != "" {
		if err := json.Unmarshal([]byte(raw), &extraEnv); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "extra_env: invalid JSON"})
			return
		}
	}
	if err := validateExtraEnv(tpl.RequiredExtraEnv, extraEnv); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
		return
	}

	// Optional extras: tags, icon, tool_prefix, auto_discover
	var tags []string
	if raw := r.FormValue("tags"); raw != "" {
		if err := json.Unmarshal([]byte(raw), &tags); err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "tags: invalid JSON"})
			return
		}
	}
	icon := r.FormValue("icon")
	toolPrefixOverride := r.FormValue("tool_prefix")
	autoDiscover := r.FormValue("auto_discover") == "true"

	// Validate tool prefix (alphanumeric only) when provided.
	if toolPrefixOverride != "" && !alphanumericRe.MatchString(toolPrefixOverride) {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "tool_prefix must contain only alphanumeric characters (a-z, A-Z, 0-9)"})
		return
	}

	// Read credentials file
	file, hdr, err := r.FormFile("credentials")
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "missing credentials file"})
		return
	}
	defer file.Close()
	if hdr.Size > int64(validation.MaxSAJSONSize) {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "credentials file too large"})
		return
	}
	credBytes, err := io.ReadAll(io.LimitReader(file, int64(validation.MaxSAJSONSize)+1))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "read credentials: " + err.Error()})
		return
	}
	if _, err := validation.ValidateServiceAccountJSON(credBytes); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid credentials: " + err.Error()})
		return
	}

	// IDs and hash
	instanceID := uuid.New().String()
	mcpServerID := instanceID // reuse the same UUID per spec
	hash := sha256.Sum256(credBytes)
	hashHex := hex.EncodeToString(hash[:])

	// Decode stdio_args + compute env
	var stdioArgs []string
	if len(tpl.StdioArgs) > 0 {
		_ = json.Unmarshal(tpl.StdioArgs, &stdioArgs)
	}
	env := renderEnv(tpl.DefaultEnv, extraEnv, instanceID)

	// 1) Insert mcp_servers row (URL is a placeholder — runner returns the real port)
	mcpSrv := db.MCPServer{
		ID:                  mcpServerID,
		Name:                tpl.Name + " — " + name,
		URL:                 "http://pending",
		MCPTransport:        "http",
		TransportPreference: "auto",
		ConnectTimeoutMs:    10000,
		IsActive:            true,
		HealthStatus:        "unknown",
		ToolPrefix:          firstNonEmpty(toolPrefixOverride, tpl.ToolPrefix),
		Icon:                firstNonEmpty(icon, tpl.Icon),
		DocSlug:             generateDocSlug(tpl.Name+"-"+name, mcpServerID),
		CreatedBy:           auth.UserEmailFromContext(r.Context()),
	}
	if err := h.repo.Create(&mcpSrv); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "create mcp_server: " + err.Error()})
		return
	}

	// Persist tags (best-effort — failure is logged but does not abort creation).
	if len(tags) > 0 {
		if err := h.repo.SaveTags(mcpServerID, tags); err != nil {
			log.Printf("[templates] save tags failed for %s: %v", mcpServerID, err)
		}
	}

	// 2) Insert template_instances row (encrypts credentials)
	extraEnvJSON, _ := json.Marshal(extraEnv)
	inst := db.TemplateInstance{
		ID:              instanceID,
		TemplateSlug:    slug,
		Name:            name,
		CredentialsHash: hashHex,
		ExtraEnv:        extraEnvJSON,
		RunnerStatus:    "pending",
		MCPServerID:     mcpServerID,
		CreatedBy:       auth.UserEmailFromContext(r.Context()),
	}
	if err := h.instanceRepo.Create(&inst, credBytes); err != nil {
		// Roll back the mcp_servers insert — without this the user sees an orphan server.
		if delErr := h.repo.Delete(mcpServerID); delErr != nil {
			log.Printf("[templates][ERROR] orphan mcp_server row id=%s — manual cleanup needed. delete err: %v (original err: %v)", mcpServerID, delErr, err)
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "create instance failed"})
		return
	}

	// 3) Call runner to spawn
	resp, err := h.runner.Spawn(r.Context(), runnerclient.SpawnRequest{
		InstanceID:      instanceID,
		TemplateSlug:    slug,
		StdioCommand:    tpl.StdioCommand,
		StdioArgs:       stdioArgs,
		Env:             env,
		CredentialsJSON: string(credBytes),
		CredentialsHash: hashHex,
	})
	if err != nil {
		log.Printf("[templates] runner spawn failed for instance %s: %v", instanceID, err)
		if uErr := h.instanceRepo.UpdateStatus(instanceID, "failed", err.Error(), nil); uErr != nil {
			log.Printf("[templates] could not persist failed status for %s: %v", instanceID, uErr)
		}
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "runner unavailable — see server logs"})
		return
	}

	// 4) Update mcp_servers URL + instance port
	// NOTE: assumes the gateway and runner share a Docker network — GoogleTemplatesRunnerURL
	// is the in-cluster URL (e.g. http://mcp-google-templates-runner:8595). If the runner is
	// ever exposed through a proxy or different public host, this extraction will need to
	// point at that public address instead. Consider a separate GOOGLE_TEMPLATES_RUNNER_PUBLIC_HOST env var.
	runnerHost := strings.TrimPrefix(strings.TrimPrefix(h.config.GoogleTemplatesRunnerURL, "http://"), "https://")
	runnerHost = strings.SplitN(runnerHost, ":", 2)[0]
	instanceURL := fmt.Sprintf("http://%s:%d", runnerHost, resp.Port)
	if err := h.repo.UpdateURL(mcpServerID, instanceURL); err != nil {
		log.Printf("[templates][WARN] could not update mcp_server URL (id=%s): %v", mcpServerID, err)
	}
	port := resp.Port
	if err := h.instanceRepo.UpdateStatus(instanceID, "running", "", &port); err != nil {
		log.Printf("[templates][WARN] could not persist running status (id=%s): %v", instanceID, err)
	}

	// 4b) Optional: auto-discover tools against the freshly-spawned instance.
	// Template instances never carry auth headers — the runner proxies with the
	// decrypted credentials internally.
	if autoDiscover && h.gw != nil && h.registry != nil {
		log.Printf("[templates] auto-discover for %s at %s", mcpServerID, instanceURL)
		if err := h.gw.DiscoverAndRegister(r.Context(), mcpServerID, instanceURL, nil); err != nil {
			log.Printf("[templates] auto-discover failed for %s: %v", mcpServerID, err)
			_ = h.repo.UpdateHealth(mcpServerID, "unhealthy", err.Error())
		} else {
			if mcpSrv.ToolPrefix != "" {
				h.registry.SetToolPrefix(mcpServerID, mcpSrv.ToolPrefix)
			}
			if backend := h.registry.FindByID(mcpServerID); backend != nil {
				h.saveBackendCapabilities(mcpServerID, backend)
			}
		}
	}

	// 5) Return 201 — re-fetch to populate CreatedAt/UpdatedAt.
	freshInst, err := h.instanceRepo.GetByID(instanceID)
	if err != nil {
		// Persisted but can't re-read — return the in-memory version.
		inst.RunnerPort = &port
		inst.RunnerStatus = "running"
		freshInst = &inst
	}
	writeJSON(w, http.StatusCreated, toInstanceResponse(*freshInst, "", instanceURL))
}

// firstNonEmpty returns a when non-empty, otherwise b. Used to let per-instance
// overrides (icon, tool_prefix) fall back to the template-level default.
func firstNonEmpty(a, b string) string {
	if a != "" {
		return a
	}
	return b
}

// renderEnv merges default_env (from template) + extra_env (admin input),
// substituting {instance_id} in default_env values.
func renderEnv(defaultEnvRaw json.RawMessage, extra map[string]string, instanceID string) map[string]string {
	out := make(map[string]string)
	var def map[string]string
	if len(defaultEnvRaw) > 0 {
		_ = json.Unmarshal(defaultEnvRaw, &def)
	}
	for k, v := range def {
		out[k] = strings.ReplaceAll(v, "{instance_id}", instanceID)
	}
	for k, v := range extra {
		out[k] = v
	}
	return out
}

// validateExtraEnv checks that admin-supplied extra_env matches the template's schema.
func validateExtraEnv(schemaRaw json.RawMessage, extra map[string]string) error {
	if len(schemaRaw) == 0 {
		return nil
	}
	var schema []struct {
		Key      string `json:"key"`
		Required bool   `json:"required"`
	}
	if err := json.Unmarshal(schemaRaw, &schema); err != nil {
		return nil // best-effort — if schema is malformed, skip
	}
	for _, field := range schema {
		if field.Required {
			if v, ok := extra[field.Key]; !ok || v == "" {
				return fmt.Errorf("extra_env: %q is required", field.Key)
			}
		}
	}
	return nil
}

func (h *Handler) handleRestartInstance(w http.ResponseWriter, r *http.Request) {
	if h.instanceRepo == nil || h.runner == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}
	id := extractInstanceID(r.URL.Path, "/restart")
	if id == "" || strings.Contains(id, "/") {
		http.NotFound(w, r)
		return
	}
	if _, err := h.instanceRepo.GetByID(id); err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instance not found"})
			return
		}
		log.Printf("[templates] restart: lookup %s failed: %v", id, err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "instance lookup failed"})
		return
	}
	if err := h.runner.Restart(r.Context(), id); err != nil {
		log.Printf("[templates] runner restart failed for instance %s: %v", id, err)
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "runner unavailable — see server logs"})
		return
	}
	if err := h.instanceRepo.UpdateStatus(id, "pending", "", nil); err != nil {
		log.Printf("[templates][WARN] could not persist restarting status (id=%s): %v", id, err)
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"status": "restarting"})
}

func (h *Handler) handleRotateCredentials(w http.ResponseWriter, r *http.Request) {
	if h.templateRepo == nil || h.instanceRepo == nil || h.runner == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}
	id := extractInstanceID(r.URL.Path, "/rotate-credentials")
	if id == "" || strings.Contains(id, "/") {
		http.NotFound(w, r)
		return
	}
	if err := r.ParseMultipartForm(int64(validation.MaxSAJSONSize) + 48*1024); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "multipart parse: " + err.Error()})
		return
	}
	file, hdr, err := r.FormFile("credentials")
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "missing credentials file"})
		return
	}
	defer file.Close()
	if hdr.Size > int64(validation.MaxSAJSONSize) {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "credentials file too large"})
		return
	}
	credBytes, err := io.ReadAll(io.LimitReader(file, int64(validation.MaxSAJSONSize)+1))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "read credentials: " + err.Error()})
		return
	}
	if _, err := validation.ValidateServiceAccountJSON(credBytes); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid credentials: " + err.Error()})
		return
	}
	hash := sha256.Sum256(credBytes)
	hashHex := hex.EncodeToString(hash[:])

	inst, err := h.instanceRepo.GetByID(id)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instance not found"})
			return
		}
		log.Printf("[templates] rotate: lookup %s failed: %v", id, err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "instance lookup failed"})
		return
	}
	tpl, err := h.templateRepo.GetBySlug(inst.TemplateSlug)
	if err != nil {
		log.Printf("[templates] rotate: template lookup for slug %q failed: %v", inst.TemplateSlug, err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "template lookup failed"})
		return
	}

	// Update DB first (encrypted blob + hash) — the runner respawn below re-reads from us on reconcile.
	if err := h.instanceRepo.UpdateCredentials(id, credBytes, hashHex); err != nil {
		log.Printf("[templates] rotate credentials DB update failed (id=%s): %v", id, err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "could not persist new credentials"})
		return
	}

	// Respawn with the new credentials
	var stdioArgs []string
	if len(tpl.StdioArgs) > 0 {
		_ = json.Unmarshal(tpl.StdioArgs, &stdioArgs)
	}
	var extraEnv map[string]string
	if len(inst.ExtraEnv) > 0 {
		_ = json.Unmarshal(inst.ExtraEnv, &extraEnv)
	}
	env := renderEnv(tpl.DefaultEnv, extraEnv, id)
	if _, err := h.runner.Spawn(r.Context(), runnerclient.SpawnRequest{
		InstanceID:      id,
		TemplateSlug:    inst.TemplateSlug,
		StdioCommand:    tpl.StdioCommand,
		StdioArgs:       stdioArgs,
		Env:             env,
		CredentialsJSON: string(credBytes),
		CredentialsHash: hashHex,
	}); err != nil {
		log.Printf("[templates] runner respawn after rotate failed (id=%s): %v", id, err)
		if uErr := h.instanceRepo.UpdateStatus(id, "failed", "rotate: "+err.Error(), nil); uErr != nil {
			log.Printf("[templates][WARN] could not persist failed status after rotate (id=%s): %v", id, uErr)
		}
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "runner unavailable — see server logs"})
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"status": "rotating"})
}

func (h *Handler) handleDeleteInstance(w http.ResponseWriter, r *http.Request) {
	if h.instanceRepo == nil || h.runner == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}
	id := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/api/v1/template-instances/"), "/")
	if id == "" || strings.Contains(id, "/") {
		http.NotFound(w, r)
		return
	}
	if _, err := h.instanceRepo.GetByID(id); err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instance not found"})
			return
		}
		log.Printf("[templates] delete: lookup %s failed: %v", id, err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "instance lookup failed"})
		return
	}
	// 1) Kill runner subprocess first (idempotent on runner side — a 404 from runner is OK;
	//    the instance may have already been cleaned up or never spawned successfully).
	if err := h.runner.Kill(r.Context(), id); err != nil {
		log.Printf("[templates][WARN] runner kill failed for %s: %v (continuing with DB delete)", id, err)
	}
	// 2) Transactional delete of template_instances + mcp_servers.
	//    ErrRecordNotFound here means a concurrent DELETE completed between the
	//    GetByID check above and the transaction — return 404 rather than a
	//    misleading 500.
	if err := h.instanceRepo.DeleteWithMCPServer(id); err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instance not found"})
			return
		}
		log.Printf("[templates] DB delete failed for %s: %v", id, err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "delete failed"})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// extractInstanceID pulls the {id} out of /api/v1/template-instances/{id}<suffix>.
// Example: extractInstanceID("/api/v1/template-instances/abc-123/restart", "/restart") == "abc-123".
// Returns "" when the path has no ID component (e.g. "/api/v1/template-instances" or
// "/api/v1/template-instances/"), so callers can 404 empty IDs explicitly.
func extractInstanceID(path, suffix string) string {
	const prefix = "/api/v1/template-instances"
	rest := strings.TrimPrefix(path, prefix)
	rest = strings.TrimPrefix(rest, "/")
	rest = strings.TrimSuffix(rest, suffix)
	return strings.TrimSuffix(rest, "/")
}
