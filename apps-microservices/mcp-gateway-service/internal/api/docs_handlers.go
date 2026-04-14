package api

import (
	"net/http"
	"strings"

	"github.com/hellopro/mcp-gateway/internal/gateway"
)

// handleGenerateSlugs backfills doc_slug on servers that don't have one yet.
func (h *Handler) handleGenerateSlugs(w http.ResponseWriter, r *http.Request) {
	servers, err := h.repo.ListAll(nil, "", "")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to list servers"})
		return
	}

	type slugResult struct {
		ID   string `json:"id"`
		Name string `json:"name"`
		Slug string `json:"slug"`
	}
	var updated []slugResult

	for _, srv := range servers {
		if srv.DocSlug != "" {
			continue
		}
		slug := generateDocSlug(srv.Name, srv.ID)
		if err := h.repo.Update(srv.ID, map[string]interface{}{"doc_slug": slug}); err != nil {
			continue
		}
		updated = append(updated, slugResult{ID: srv.ID, Name: srv.Name, Slug: slug})
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"updated": len(updated),
		"servers": updated,
	})
}

// handleListDocServers returns all servers that have documentation configured (doc_slug set).
func (h *Handler) handleListDocServers(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	servers, err := h.repo.ListWithDocs()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to list documentation"})
		return
	}

	docs := make([]DocsServerSummary, 0, len(servers))
	for _, srv := range servers {
		activeTools := 0
		for _, t := range srv.Tools {
			if t.IsActive {
				activeTools++
			}
		}
		docs = append(docs, DocsServerSummary{
			Slug:        srv.DocSlug,
			Name:        srv.Name,
			Description: srv.DocDescription,
			Icon:        srv.Icon,
			ToolsCount:  activeTools,
		})
	}

	writeJSON(w, http.StatusOK, docs)
}

// handleGetDocServer returns a single server's documentation by its doc_slug.
func (h *Handler) handleGetDocServer(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	slug := strings.TrimPrefix(r.URL.Path, "/api/v1/public/docs/")
	if slug == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "slug is required"})
		return
	}

	srv, err := h.repo.GetByDocSlug(slug)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "documentation not found"})
		return
	}

	tools := make([]ToolResponse, 0, len(srv.Tools))
	for _, t := range srv.Tools {
		if !t.IsActive {
			continue
		}
		tools = append(tools, ToolResponse{
			Name:        gateway.PrefixedToolName(srv.ToolPrefix, t.Name),
			Description: t.Description,
			InputSchema: t.InputSchema,
			IsActive:    t.IsActive,
		})
	}

	detail := DocsServerDetail{
		DocsServerSummary: DocsServerSummary{
			Slug:        srv.DocSlug,
			Name:        srv.Name,
			Description: srv.DocDescription,
			Icon:        srv.Icon,
			ToolsCount:  len(tools),
		},
		Tools:       tools,
		ConfigGuide: srv.DocConfigGuide,
	}

	writeJSON(w, http.StatusOK, detail)
}
