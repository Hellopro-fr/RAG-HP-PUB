package api

import (
	"net/http"
	"strconv"

	"github.com/hellopro/mcp-gateway/internal/repository"
)

// handleAuditLogs handles GET /api/v1/audit-logs with query params:
// user_email, action, resource_type, date_from, date_to, page, per_page.
func (h *Handler) handleAuditLogs(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}

	q := r.URL.Query()

	page, _ := strconv.Atoi(q.Get("page"))
	perPage, _ := strconv.Atoi(q.Get("per_page"))

	filter := repository.AuditFilter{
		UserEmail:    q.Get("user_email"),
		Action:       q.Get("action"),
		ResourceType: q.Get("resource_type"),
		DateFrom:     q.Get("date_from"),
		DateTo:       q.Get("date_to"),
		Page:         page,
		PerPage:      perPage,
	}

	result, err := h.auditRepo.List(filter)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to list audit logs"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"logs":     result.Logs,
		"total":    result.Total,
		"page":     result.Page,
		"pages":    result.Pages,
		"per_page": filter.PerPage,
	})
}
