package api

import (
	"net/http"
	"strings"

	"github.com/hellopro/mcp-gateway/internal/db"
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
