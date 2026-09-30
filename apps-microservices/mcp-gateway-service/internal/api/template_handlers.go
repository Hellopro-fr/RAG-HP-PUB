package api

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/runnerclient"
	"mcp-gateway/internal/validation"
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
	// Defence-in-depth: "export" and "import" are reserved sub-paths of
	// /api/v1/templates/ and are registered with exact handlers above. This
	// guard ensures we never silently fall through to a slug lookup if the
	// mux routing order ever regresses.
	if slug == "export" || slug == "import" {
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
		Kind:             t.Kind,
		Runner:           templateRunnerName(&t),
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
	creator := effectiveCreatorFilter(r.Context())
	var instances []db.TemplateInstance
	var err error
	if slug != "" {
		instances, err = h.instanceRepo.ListByTemplate(slug, creator)
	} else {
		instances, err = h.instanceRepo.ListAll(creator)
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
	// Best-effort: fetch live stderr tail from the instance's runner.
	tail := ""
	if ep, rerr := h.runnerForInstance(inst); rerr == nil {
		if statuses, lerr := ep.Client.List(r.Context()); lerr == nil {
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
	if h.templateRepo == nil || h.instanceRepo == nil || h.repo == nil || h.config == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}

	// Multipart: "template_slug", "name", "extra_env" (JSON string), plus either file "credentials" (Google runner) or neo4j_* fields (Neo4j runner).
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
	// Only "stdio" templates create per-instance subprocesses. http_batch rows
	// are admin shortcuts that bulk-create full HTTP mcp_servers via the
	// existing server-import flow — they cannot accept SA JSON nor spawn.
	if tpl.Kind != "" && tpl.Kind != "stdio" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{
			Error: fmt.Sprintf("template %s does not support instance creation", tpl.Slug),
		})
		return
	}
	runnerName := templateRunnerName(tpl)
	if _, err := h.runnerEndpoint(runnerName); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: err.Error()})
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
	if err := validateRunnerExtraEnv(runnerName, extraEnv); err != nil {
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

	// The static mcp-neo4j-service already owns the "neo4j" prefix and the
	// gateway has no tool-name collision check: every Neo4j instance must
	// carry its own prefix (the seed leaves the template prefix empty).
	if runnerName == RunnerNeo4j {
		if p := firstNonEmpty(toolPrefixOverride, tpl.ToolPrefix); p == "" || strings.EqualFold(p, "neo4j") {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{
				Error: `tool_prefix is required for Neo4j instances and must not be "neo4j" (used by the static Neo4j server), e.g. neo4jprod`,
			})
			return
		}
	}

	credBytes, err := credentialsFromRequest(r, runnerName)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
		return
	}

	// Delegate to the shared spec-based flow.
	createdBy := auth.UserEmailFromContext(r.Context())
	freshInst, instanceURL, err := h.createInstanceFromSpec(
		r.Context(), tpl, name, credBytes, extraEnv, tags, icon, toolPrefixOverride, autoDiscover, createdBy,
	)
	if err != nil {
		status, msg := classifyCreateInstanceError(err)
		writeJSON(w, status, ErrorResponse{Error: msg})
		return
	}
	writeJSON(w, http.StatusCreated, toInstanceResponse(*freshInst, "", instanceURL))
}

// createInstanceErrorKind categorizes failures surfaced by createInstanceFromSpec
// so callers can map them to HTTP status codes (handleCreateInstance) or row
// statuses (handleImportInstancesFromSheet).
type createInstanceErrorKind int

const (
	createInstanceErrDB createInstanceErrorKind = iota
	createInstanceErrSpawn
	createInstanceErrUnhealthy
	createInstanceErrMCPServerInsert
	createInstanceErrRunnerMissing
	createInstanceErrPrecheck
)

// createInstanceError carries the failure stage + underlying cause so the
// calling HTTP handler can produce a specific status code and log the root
// reason. Rollback of template_instances + runner kill is already performed
// internally before this error is returned.
type createInstanceError struct {
	Kind createInstanceErrorKind
	Err  error
}

func (e *createInstanceError) Error() string { return e.Err.Error() }
func (e *createInstanceError) Unwrap() error { return e.Err }

// classifyCreateInstanceError maps a createInstanceError to a (status, message)
// pair matching the legacy single-instance behaviour. Any non-typed error is
// treated as a generic 500.
func classifyCreateInstanceError(err error) (int, string) {
	var cerr *createInstanceError
	if errors.As(err, &cerr) {
		switch cerr.Kind {
		case createInstanceErrDB:
			return http.StatusInternalServerError, "create instance failed"
		case createInstanceErrSpawn:
			return http.StatusBadGateway, "runner unavailable — see server logs"
		case createInstanceErrUnhealthy:
			return http.StatusBadGateway, "instance failed to become healthy"
		case createInstanceErrRunnerMissing:
			return http.StatusServiceUnavailable, cerr.Err.Error()
		case createInstanceErrPrecheck:
			msg, _ := runnerPrecheckMessage(cerr.Err)
			return http.StatusUnprocessableEntity, msg
		case createInstanceErrMCPServerInsert:
			return http.StatusInternalServerError, "create mcp_server failed"
		}
	}
	return http.StatusInternalServerError, err.Error()
}

// createInstanceFromSpec runs the full create flow (DB insert → runner spawn →
// TCP ready → mcp_servers insert → tags → auto-discover) from a pre-validated
// spec. Returns the refreshed TemplateInstance and the in-cluster URL, or a
// *createInstanceError describing where the flow aborted. Rollback of
// template_instances + runner kill is handled internally before any error
// returns, so callers do not need to clean up on failure.
//
// Preconditions (callers MUST validate): tpl non-nil, name non-empty,
// credentialsJSON already validated for the template's runner (credentialsFromRequest),
// extraEnv already passed validateExtraEnv against tpl.RequiredExtraEnv,
// toolPrefixOverride already alphanumeric-validated.
func (h *Handler) createInstanceFromSpec(
	ctx context.Context,
	tpl *db.Template,
	name string,
	credentialsJSON []byte,
	extraEnv map[string]string,
	tags []string,
	icon string,
	toolPrefixOverride string,
	autoDiscover bool,
	createdBy string,
) (*db.TemplateInstance, string, error) {
	ep, err := h.runnerForTemplate(tpl)
	if err != nil {
		return nil, "", &createInstanceError{Kind: createInstanceErrRunnerMissing, Err: err}
	}
	// IDs and hash
	instanceID := uuid.New().String()
	mcpServerID := instanceID // reuse the same UUID per spec
	hash := sha256.Sum256(credentialsJSON)
	hashHex := hex.EncodeToString(hash[:])

	// Decode stdio_args + compute env. Initialise to an empty slice so a
	// null JSON never reaches the runner — Pydantic's list[str] rejects null
	// and returns 422.
	stdioArgs := []string{}
	if len(tpl.StdioArgs) > 0 {
		_ = json.Unmarshal(tpl.StdioArgs, &stdioArgs)
		if stdioArgs == nil {
			stdioArgs = []string{}
		}
	}
	env := renderEnv(tpl.DefaultEnv, extraEnv, instanceID)

	// 1) Insert template_instances row first (status=pending). mcp_servers is
	// deferred until we know the runner spawned + the instance is healthy —
	// otherwise a failed spawn leaves a ghost "pending" server in the servers
	// list that tokens/OAuth2 clients can bind to.
	// mcp_server_id is pre-assigned but the mcp_servers row doesn't exist yet;
	// the detail view tolerates missing servers (GetURL returns empty).
	extraEnvJSON, _ := json.Marshal(extraEnv)
	inst := db.TemplateInstance{
		ID:              instanceID,
		TemplateSlug:    tpl.Slug,
		Name:            name,
		CredentialsHash: hashHex,
		ExtraEnv:        extraEnvJSON,
		RunnerStatus:    "pending",
		MCPServerID:     mcpServerID,
		CreatedBy:       createdBy,
	}
	if err := h.instanceRepo.Create(&inst, credentialsJSON); err != nil {
		return nil, "", &createInstanceError{Kind: createInstanceErrDB, Err: err}
	}

	// 2) Spawn via the runner.
	resp, err := ep.Client.Spawn(ctx, runnerclient.SpawnRequest{
		InstanceID:      instanceID,
		TemplateSlug:    tpl.Slug,
		StdioCommand:    tpl.StdioCommand,
		StdioArgs:       stdioArgs,
		Env:             env,
		CredentialsJSON: string(credentialsJSON),
		CredentialsHash: hashHex,
	})
	if err != nil {
		log.Printf("[templates] runner spawn failed for instance %s: %v", instanceID, err)
		if delErr := h.instanceRepo.DeleteWithMCPServer(instanceID); delErr != nil {
			log.Printf("[templates][WARN] could not roll back instance row %s: %v", instanceID, delErr)
		}
		kind := createInstanceErrSpawn
		if _, ok := runnerPrecheckMessage(err); ok {
			kind = createInstanceErrPrecheck
		}
		return nil, "", &createInstanceError{Kind: kind, Err: err}
	}

	// Compute the in-cluster URL. The gateway and runner share a Docker network.
	host := runnerHost(ep.URL)
	instanceURL := fmt.Sprintf("http://%s:%d", host, resp.Port)
	hostPort := fmt.Sprintf("%s:%d", host, resp.Port)

	// 3) Wait until mcp-proxy is accepting TCP connections on its port. The
	// Spawn call returns as soon as the supervisor launches the child, but
	// mcp-proxy needs a beat to bind. Without this, auto-discover and the
	// first client request both race the startup.
	if err := waitForTCPReady(ctx, hostPort, 15*time.Second); err != nil {
		log.Printf("[templates] instance %s never became TCP-ready at %s: %v", instanceID, hostPort, err)
		if kerr := ep.Client.Kill(ctx, instanceID); kerr != nil {
			log.Printf("[templates][WARN] kill after unhealthy startup failed for %s: %v", instanceID, kerr)
		}
		if delErr := h.instanceRepo.DeleteWithMCPServer(instanceID); delErr != nil {
			log.Printf("[templates][WARN] could not roll back unhealthy instance row %s: %v", instanceID, delErr)
		}
		return nil, "", &createInstanceError{Kind: createInstanceErrUnhealthy, Err: err}
	}

	// 4) Insert mcp_servers row now that we know the instance is live.
	port := resp.Port
	mcpSrv := db.MCPServer{
		ID:                  mcpServerID,
		Name:                tpl.Name + " — " + name,
		URL:                 instanceURL,
		MCPTransport:        "http",
		TransportPreference: "auto",
		ConnectTimeoutMs:    10000,
		IsActive:            true,
		HealthStatus:        "healthy",
		ToolPrefix:          firstNonEmpty(toolPrefixOverride, tpl.ToolPrefix),
		Icon:                firstNonEmpty(icon, tpl.Icon),
		// TemplateSlug flags this row as template-origin so ListWithDocs,
		// GetByDocSlug and the docs-admin exclude_templates filter can all
		// skip it via a single column predicate.
		TemplateSlug: tpl.Slug,
		// Generate a unique doc_slug so the UNIQUE index on mcp_servers is
		// satisfied — empty strings would collide on the second row. The
		// slug is never surfaced: ServerRepo.ListWithDocs, GetByDocSlug and
		// the docs-admin filter all exclude template-backed servers.
		DocSlug:   generateDocSlug(tpl.Name+"-"+name, mcpServerID),
		CreatedBy: createdBy,
	}
	if err := h.repo.Create(&mcpSrv); err != nil {
		log.Printf("[templates] create mcp_server failed for %s: %v", mcpServerID, err)
		if kerr := ep.Client.Kill(ctx, instanceID); kerr != nil {
			log.Printf("[templates][WARN] kill after mcp_server insert failure for %s: %v", instanceID, kerr)
		}
		if delErr := h.instanceRepo.DeleteWithMCPServer(instanceID); delErr != nil {
			log.Printf("[templates][WARN] could not roll back instance row %s: %v", instanceID, delErr)
		}
		return nil, "", &createInstanceError{Kind: createInstanceErrMCPServerInsert, Err: err}
	}

	// Tags (best-effort).
	if len(tags) > 0 {
		if err := h.repo.SaveTags(mcpServerID, tags); err != nil {
			log.Printf("[templates] save tags failed for %s: %v", mcpServerID, err)
		}
	}

	// 5) Mark instance running with its bound port.
	if err := h.instanceRepo.UpdateStatus(instanceID, "running", "", &port); err != nil {
		log.Printf("[templates][WARN] could not persist running status (id=%s): %v", instanceID, err)
	}

	// 6) Optional: auto-discover tools against the live instance. No auth
	// headers — the runner proxies with the decrypted SA JSON internally.
	if autoDiscover && h.gw != nil && h.registry != nil {
		log.Printf("[templates] auto-discover for %s at %s", mcpServerID, instanceURL)
		if err := h.gw.DiscoverAndRegister(ctx, mcpServerID, instanceURL, nil); err != nil {
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

	// 7) Re-fetch to populate CreatedAt/UpdatedAt. Fallback to the in-memory
	// row if the re-fetch fails (unlikely but survivable).
	freshInst, err := h.instanceRepo.GetByID(instanceID)
	if err != nil {
		inst.RunnerPort = &port
		inst.RunnerStatus = "running"
		freshInst = &inst
	}
	return freshInst, instanceURL, nil
}

// waitForTCPReady dials hostPort with an exponential-ish backoff until a
// connect succeeds or the deadline expires. Used to verify that mcp-proxy
// has bound its port before we commit the mcp_servers row.
func waitForTCPReady(ctx context.Context, hostPort string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	backoff := 200 * time.Millisecond
	for {
		if time.Now().After(deadline) {
			return fmt.Errorf("tcp ready deadline exceeded for %s", hostPort)
		}
		dialer := net.Dialer{Timeout: 2 * time.Second}
		conn, err := dialer.DialContext(ctx, "tcp", hostPort)
		if err == nil {
			_ = conn.Close()
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(backoff):
		}
		if backoff < 2*time.Second {
			backoff *= 2
		}
	}
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
	if h.instanceRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}
	id := extractInstanceID(r.URL.Path, "/restart")
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
		log.Printf("[templates] restart: lookup %s failed: %v", id, err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "instance lookup failed"})
		return
	}
	ep, err := h.runnerForInstance(inst)
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: err.Error()})
		return
	}
	if err := ep.Client.Restart(r.Context(), id); err != nil {
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
	if h.templateRepo == nil || h.instanceRepo == nil {
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
	runnerName := templateRunnerName(tpl)
	ep, err := h.runnerEndpoint(runnerName)
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: err.Error()})
		return
	}
	credBytes, err := credentialsFromRequest(r, runnerName)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
		return
	}
	hash := sha256.Sum256(credBytes)
	hashHex := hex.EncodeToString(hash[:])

	var extraEnv map[string]string
	if len(inst.ExtraEnv) > 0 {
		_ = json.Unmarshal(inst.ExtraEnv, &extraEnv)
	}
	// A Neo4j rotate may also change NEO4J_READ_ONLY (the "Lecture seule"
	// checkbox lives in the same dialog). A Google rotate keeps extra_env.
	newExtraEnvJSON := inst.ExtraEnv
	if runnerName == RunnerNeo4j {
		if raw := r.FormValue("extra_env"); raw != "" {
			var parsed map[string]string
			if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
				writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "extra_env: invalid JSON"})
				return
			}
			if err := validateExtraEnv(tpl.RequiredExtraEnv, parsed); err != nil {
				writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
				return
			}
			if err := validateRunnerExtraEnv(runnerName, parsed); err != nil {
				writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
				return
			}
			extraEnv = parsed
			newExtraEnvJSON, _ = json.Marshal(parsed)
		}
	}
	extraEnvChanged := string(newExtraEnvJSON) != string(inst.ExtraEnv)

	// persist writes the new credentials (encrypted blob + hash) and settings.
	persist := func() error {
		if err := h.instanceRepo.UpdateCredentials(id, credBytes, hashHex); err != nil {
			return err
		}
		if extraEnvChanged {
			return h.instanceRepo.UpdateExtraEnv(id, newExtraEnvJSON)
		}
		return nil
	}
	// Google: DB first — the runner respawn below re-reads from us on reconcile.
	// Neo4j: the runner pre-checks the new credentials, so they are persisted
	// only once it accepted them. A rejected rotate never touches the DB, and a
	// reconcile racing with the pre-check keeps using the stored (previous)
	// credentials.
	persistAfterSpawn := runnerName == RunnerNeo4j
	if !persistAfterSpawn {
		if err := persist(); err != nil {
			log.Printf("[templates] rotate credentials DB update failed (id=%s): %v", id, err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "could not persist new credentials"})
			return
		}
	}

	// Respawn with the new credentials. See handleCreateInstance for why the
	// slice is initialised to empty rather than left nil.
	stdioArgs := []string{}
	if len(tpl.StdioArgs) > 0 {
		_ = json.Unmarshal(tpl.StdioArgs, &stdioArgs)
		if stdioArgs == nil {
			stdioArgs = []string{}
		}
	}
	env := renderEnv(tpl.DefaultEnv, extraEnv, id)
	if _, err := ep.Client.Spawn(r.Context(), runnerclient.SpawnRequest{
		InstanceID:      id,
		TemplateSlug:    inst.TemplateSlug,
		StdioCommand:    tpl.StdioCommand,
		StdioArgs:       stdioArgs,
		Env:             env,
		CredentialsJSON: string(credBytes),
		CredentialsHash: hashHex,
		RunnerPort:      inst.RunnerPort,
	}); err != nil {
		if msg, ok := runnerPrecheckMessage(err); ok {
			// Nothing was persisted and the runner left the running process alone.
			writeJSON(w, http.StatusUnprocessableEntity, ErrorResponse{Error: msg})
			return
		}
		log.Printf("[templates] runner respawn after rotate failed (id=%s): %v", id, err)
		if uErr := h.instanceRepo.UpdateStatus(id, "failed", "rotate: "+err.Error(), nil); uErr != nil {
			log.Printf("[templates][WARN] could not persist failed status after rotate (id=%s): %v", id, uErr)
		}
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "runner unavailable — see server logs"})
		return
	}
	if persistAfterSpawn {
		if err := persist(); err != nil {
			// The runner already serves the new credentials; the next reconcile
			// reverts it to the stored (previous) ones, the safe direction.
			log.Printf("[templates] rotate credentials DB update failed after respawn (id=%s): %v", id, err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "could not persist new credentials"})
			return
		}
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"status": "rotating"})
}

func (h *Handler) handleDeleteInstance(w http.ResponseWriter, r *http.Request) {
	if h.instanceRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}
	id := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/api/v1/template-instances/"), "/")
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
		log.Printf("[templates] delete: lookup %s failed: %v", id, err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "instance lookup failed"})
		return
	}
	// 1) Kill the runner subprocess first (idempotent on the runner side). An
	//    unconfigured runner cannot be reached anyway; its reconcile loop drops
	//    the instance once the row is gone.
	if ep, rerr := h.runnerForInstance(inst); rerr != nil {
		log.Printf("[templates][WARN] %v — skipping kill for %s (continuing with DB delete)", rerr, id)
	} else if err := ep.Client.Kill(r.Context(), id); err != nil {
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

// maxTemplateImportBody caps the catalog import JSON at 256 KB. 2 real
// templates serialize to < 2 KB, so this is ~100× headroom for reasonable
// growth without enabling DoS via giant uploads.
const maxTemplateImportBody = 256 * 1024

// handleExportTemplates returns the entire catalog as a JSON attachment.
// Active + inactive rows are included so a re-imported dump restores the
// exact catalog state. Instances and credentials are intentionally excluded.
func (h *Handler) handleExportTemplates(w http.ResponseWriter, r *http.Request) {
	if h.templateRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}
	rows, err := h.templateRepo.ListAll()
	if err != nil {
		log.Printf("[templates] export list failed: %v", err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "list templates failed"})
		return
	}
	out := TemplateExportPayload{
		Version:    1,
		ExportedAt: time.Now().UTC(),
		Templates:  make([]TemplateExportRow, 0, len(rows)),
	}
	for _, t := range rows {
		out.Templates = append(out.Templates, toTemplateExportRow(t))
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Content-Disposition", `attachment; filename="templates-export.json"`)
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(out)
}

// toTemplateExportRow decodes the json.RawMessage fields into their native
// types so the export is human-editable (arrays/objects instead of escaped
// strings). Malformed JSON in the DB defaults to empty values rather than
// failing the whole export — the DB is the source of truth.
func toTemplateExportRow(t db.Template) TemplateExportRow {
	row := TemplateExportRow{
		Slug:         t.Slug,
		Name:         t.Name,
		Description:  t.Description,
		Icon:         t.Icon,
		StdioCommand: t.StdioCommand,
		ToolPrefix:   t.ToolPrefix,
		Kind:         t.Kind,
		Runner:       t.Runner,
		IsActive:     t.IsActive,
	}
	if len(t.StdioArgs) > 0 {
		_ = json.Unmarshal(t.StdioArgs, &row.StdioArgs)
	}
	if len(t.DefaultEnv) > 0 {
		_ = json.Unmarshal(t.DefaultEnv, &row.DefaultEnv)
	}
	if len(t.RequiredExtraEnv) > 0 {
		_ = json.Unmarshal(t.RequiredExtraEnv, &row.RequiredExtraEnv)
	}
	if len(t.Tags) > 0 {
		_ = json.Unmarshal(t.Tags, &row.Tags)
	}
	return row
}

// handleImportTemplates accepts a JSON body matching the export shape and
// upserts every row by slug in one transaction. Body cap: 256 KB. Unknown
// top-level fields are ignored. Each row must have non-empty slug, name,
// and stdio_command — first offender aborts the whole import.
func (h *Handler) handleImportTemplates(w http.ResponseWriter, r *http.Request) {
	if h.templateRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "templates feature not configured"})
		return
	}
	// Enforce the per-endpoint cap. http.MaxBytesReader makes Read return a
	// *http.MaxBytesError once the client exceeds it; we map that to 413
	// explicitly. Any other read error (broken connection, slow client) is a
	// generic 400.
	r.Body = http.MaxBytesReader(w, r.Body, maxTemplateImportBody)
	body, err := io.ReadAll(r.Body)
	if err != nil {
		var mbe *http.MaxBytesError
		if errors.As(err, &mbe) {
			writeJSON(w, http.StatusRequestEntityTooLarge, ErrorResponse{Error: "payload too large (max 256 KB)"})
			return
		}
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "read body: " + err.Error()})
		return
	}

	var payload TemplateExportPayload
	if err := json.Unmarshal(body, &payload); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}
	// Distinguish "missing templates key" from "empty list". An export always
	// includes the key, even when empty, so a missing key implies a malformed
	// or unrelated file.
	if payload.Templates == nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "missing templates: []"})
		return
	}

	rows := make([]db.Template, 0, len(payload.Templates))
	for idx, row := range payload.Templates {
		// slug + name are always required. stdio_command is required for
		// "stdio" templates (which spawn subprocesses); "http_batch" rows carry
		// no stdio command.
		kind := row.Kind
		if kind == "" {
			kind = "stdio"
		}
		if strings.TrimSpace(row.Slug) == "" || strings.TrimSpace(row.Name) == "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{
				Error: fmt.Sprintf("template at index %d: slug and name are required", idx),
			})
			return
		}
		if kind == "stdio" && strings.TrimSpace(row.StdioCommand) == "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{
				Error: fmt.Sprintf("template at index %d: stdio_command is required for stdio templates", idx),
			})
			return
		}
		tpl, err := fromTemplateExportRow(row)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
			return
		}
		rows = append(rows, tpl)
	}

	// Changing templates.runner while instances exist would hand their
	// credentials to the other runner on its next sync (and kill them on the
	// old one). The repository allows it; the import refuses it.
	if h.instanceRepo != nil {
		counts, err := h.instanceRepo.CountsByTemplate()
		if err != nil {
			log.Printf("[templates] import: count instances failed: %v", err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "import failed"})
			return
		}
		// ListAll, not GetBySlug: GetBySlug only returns active templates, and an
		// inactive template can still have instances.
		current, err := h.templateRepo.ListAll()
		if err != nil {
			log.Printf("[templates] import: list templates failed: %v", err)
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "import failed"})
			return
		}
		bySlug := make(map[string]db.Template, len(current))
		for _, c := range current {
			bySlug[c.Slug] = c
		}
		for _, t := range rows {
			cur, ok := bySlug[t.Slug]
			if !ok || counts[t.Slug] == 0 {
				continue
			}
			if from, to := templateRunnerName(&cur), templateRunnerName(&t); from != to {
				writeJSON(w, http.StatusConflict, ErrorResponse{
					Error: fmt.Sprintf("template %s: cannot change runner %s -> %s while it has %d instance(s)", t.Slug, from, to, counts[t.Slug]),
				})
				return
			}
		}
	}

	if err := h.templateRepo.Upsert(rows); err != nil {
		log.Printf("[templates] import upsert failed: %v", err)
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "import failed"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]int{"imported": len(rows)})
}

// fromTemplateExportRow re-encodes the decoded JSON fields back to
// json.RawMessage for GORM. Any field that fails to marshal surfaces a
// per-slug 400 response via a typed error.
func fromTemplateExportRow(row TemplateExportRow) (db.Template, error) {
	// Default unset `kind` to "stdio" for backward compatibility with dumps
	// created before the column existed.
	kind := row.Kind
	if kind == "" {
		kind = "stdio"
	}
	// Dumps created before templates.runner existed carry no runner: they are
	// Google templates.
	runner := row.Runner
	if runner == "" {
		runner = RunnerGoogle
	}
	if !knownRunners[runner] {
		return db.Template{}, fmt.Errorf("template %s: unknown runner %q", row.Slug, runner)
	}
	t := db.Template{
		Slug:         row.Slug,
		Name:         row.Name,
		Description:  row.Description,
		Icon:         row.Icon,
		StdioCommand: row.StdioCommand,
		ToolPrefix:   row.ToolPrefix,
		Kind:         kind,
		Runner:       runner,
		IsActive:     row.IsActive,
	}
	var err error
	if t.StdioArgs, err = marshalField(row.StdioArgs, row.Slug, "stdio_args"); err != nil {
		return t, err
	}
	if t.DefaultEnv, err = marshalField(row.DefaultEnv, row.Slug, "default_env"); err != nil {
		return t, err
	}
	if t.RequiredExtraEnv, err = marshalField(row.RequiredExtraEnv, row.Slug, "required_extra_env"); err != nil {
		return t, err
	}
	if t.Tags, err = marshalField(row.Tags, row.Slug, "tags"); err != nil {
		return t, err
	}
	return t, nil
}

// marshalField encodes v as JSON. nil or empty input produces nil so GORM
// writes a SQL NULL instead of a literal "null" string. Marshal failures
// surface the offending slug + field name in the returned error.
func marshalField(v interface{}, slug, field string) (json.RawMessage, error) {
	if v == nil {
		return nil, nil
	}
	// Reject obviously-empty inputs — keeps DB columns NULL-able after import.
	switch typed := v.(type) {
	case []string:
		if len(typed) == 0 {
			return nil, nil
		}
	case map[string]string:
		if len(typed) == 0 {
			return nil, nil
		}
	case []map[string]interface{}:
		if len(typed) == 0 {
			return nil, nil
		}
	}
	b, err := json.Marshal(v)
	if err != nil {
		return nil, fmt.Errorf("template %s: %s is invalid JSON", slug, field)
	}
	return b, nil
}
