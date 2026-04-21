package api

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
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
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "template not found"})
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
		out = append(out, toInstanceResponse(inst, ""))
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
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instance not found"})
		return
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
	writeJSON(w, http.StatusOK, toInstanceResponse(*inst, tail))
}

func toInstanceResponse(inst db.TemplateInstance, stderrTail string) TemplateInstanceResponse {
	return TemplateInstanceResponse{
		ID:              inst.ID,
		TemplateSlug:    inst.TemplateSlug,
		Name:            inst.Name,
		ExtraEnv:        inst.ExtraEnv,
		RunnerPort:      inst.RunnerPort,
		RunnerStatus:    inst.RunnerStatus,
		RunnerLastError: inst.RunnerLastError,
		MCPServerID:     inst.MCPServerID,
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
	if err := r.ParseMultipartForm(int64(validation.MaxSAJSONSize) + 16*1024); err != nil {
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
		ToolPrefix:          tpl.ToolPrefix,
		DocSlug:             generateDocSlug(tpl.Name+"-"+name, mcpServerID),
		CreatedBy:           auth.UserEmailFromContext(r.Context()),
	}
	if err := h.repo.Create(&mcpSrv); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "create mcp_server: " + err.Error()})
		return
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
			log.Printf("[templates] rollback mcp_server delete failed: %v", delErr)
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "create instance: " + err.Error()})
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
		_ = h.instanceRepo.UpdateStatus(instanceID, "failed", err.Error(), nil)
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: "runner spawn failed: " + err.Error()})
		return
	}

	// 4) Update mcp_servers URL + instance port
	runnerHost := strings.TrimPrefix(strings.TrimPrefix(h.config.GoogleTemplatesRunnerURL, "http://"), "https://")
	runnerHost = strings.SplitN(runnerHost, ":", 2)[0]
	instanceURL := fmt.Sprintf("http://%s:%d", runnerHost, resp.Port)
	if err := h.repo.UpdateURL(mcpServerID, instanceURL); err != nil {
		log.Printf("[templates] warn: could not update mcp_server URL: %v", err)
	}
	port := resp.Port
	_ = h.instanceRepo.UpdateStatus(instanceID, "running", "", &port)

	// 5) Return 201
	inst.RunnerPort = &port
	inst.RunnerStatus = "running"
	writeJSON(w, http.StatusCreated, toInstanceResponse(inst, ""))
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
