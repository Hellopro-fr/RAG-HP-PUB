package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/hellopro/mcp-gateway/internal/auth"
	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/gateway"
	"github.com/hellopro/mcp-gateway/internal/repository"
	"gorm.io/gorm"
)

// ── /api/v1/llm-instructions ─────────────────────────────────────────────────

// handleLLMInstructions dispatches the collection-level routes:
//   GET  /api/v1/llm-instructions            — list (optional ?server_ids=csv)
//   POST /api/v1/llm-instructions            — create
func (h *Handler) handleLLMInstructions(w http.ResponseWriter, r *http.Request) {
	if h.instructionRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "llm instructions not configured"})
		return
	}
	switch r.Method {
	case http.MethodGet:
		h.listLLMInstructions(w, r)
	case http.MethodPost:
		h.createLLMInstruction(w, r)
	default:
		w.Header().Set("Allow", "GET, POST")
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
	}
}

// handleLLMInstructionByID dispatches per-row routes:
//   GET    /api/v1/llm-instructions/{id}
//   PUT    /api/v1/llm-instructions/{id}
//   DELETE /api/v1/llm-instructions/{id}
//   GET    /api/v1/llm-instructions/{id}/usage
func (h *Handler) handleLLMInstructionByID(w http.ResponseWriter, r *http.Request) {
	if h.instructionRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "llm instructions not configured"})
		return
	}
	path := strings.TrimPrefix(r.URL.Path, "/api/v1/llm-instructions/")
	parts := strings.SplitN(path, "/", 2)
	id := parts[0]
	if id == "" {
		http.NotFound(w, r)
		return
	}

	if len(parts) == 2 && parts[1] == "usage" {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
			return
		}
		h.getLLMInstructionUsage(w, r, id)
		return
	}

	if len(parts) == 2 && parts[1] == "rendered" {
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
			return
		}
		h.getLLMInstructionRendered(w, r, id)
		return
	}

	switch r.Method {
	case http.MethodGet:
		h.getLLMInstruction(w, r, id)
	case http.MethodPut:
		h.updateLLMInstruction(w, r, id)
	case http.MethodDelete:
		h.deleteLLMInstruction(w, r, id)
	default:
		w.Header().Set("Allow", "GET, PUT, DELETE")
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
	}
}

// ── handlers ─────────────────────────────────────────────────────────────────

func (h *Handler) listLLMInstructions(w http.ResponseWriter, r *http.Request) {
	// Scope both list paths to the current user so config-only sessions see
	// only their own pages — mirrors tokenRepo/OAuth2Repo behaviour.
	userEmail := auth.UserEmailFromContext(r.Context())
	serverIDsCSV := strings.TrimSpace(r.URL.Query().Get("server_ids"))
	var rows []LLMInstructionResponse
	if serverIDsCSV != "" {
		ids := splitCSVNonEmpty(serverIDsCSV)
		list, err := h.instructionRepo.ListByServerIDs(ids, userEmail)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
			return
		}
		rows = make([]LLMInstructionResponse, 0, len(list))
		for i := range list {
			rows = append(rows, toLLMInstructionResponse(&list[i]))
		}
	} else {
		list, err := h.instructionRepo.List(userEmail)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
			return
		}
		rows = make([]LLMInstructionResponse, 0, len(list))
		for i := range list {
			rows = append(rows, toLLMInstructionResponse(&list[i]))
		}
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"llm_instructions": rows})
}

func (h *Handler) createLLMInstruction(w http.ResponseWriter, r *http.Request) {
	var req CreateLLMInstructionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
		return
	}
	if strings.TrimSpace(req.Title) == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "title is required"})
		return
	}
	rows, errMsg := validateAndBuildRows(req.Rows)
	if errMsg != "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: errMsg})
		return
	}

	createdBy := auth.UserEmailFromContext(r.Context())
	ins, err := h.instructionRepo.Create(req.Title, req.Description, rows, createdBy)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	h.invalidateScopeCaches()
	writeJSON(w, http.StatusCreated, toLLMInstructionResponse(ins))
}

func (h *Handler) getLLMInstruction(w http.ResponseWriter, r *http.Request, id string) {
	ins, err := h.instructionRepo.GetByID(id)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instruction not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if !isInstructionOwner(r, ins) {
		writeJSON(w, http.StatusForbidden, ErrorResponse{Error: "not your instruction"})
		return
	}
	writeJSON(w, http.StatusOK, toLLMInstructionResponse(ins))
}

func (h *Handler) updateLLMInstruction(w http.ResponseWriter, r *http.Request, id string) {
	existing, err := h.instructionRepo.GetByID(id)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instruction not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if !isInstructionOwner(r, existing) {
		writeJSON(w, http.StatusForbidden, ErrorResponse{Error: "not your instruction"})
		return
	}

	// Two-pass decode so we can tell whether `rows` was explicitly provided
	// (= replace) vs omitted (= leave alone).
	raw := map[string]json.RawMessage{}
	if err := json.NewDecoder(r.Body).Decode(&raw); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
		return
	}
	var req UpdateLLMInstructionRequest
	if err := remarshal(raw, &req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
		return
	}
	_, req.RowsProvided = raw["rows"]

	title := existing.Title
	description := existing.Description
	if req.Title != nil {
		if strings.TrimSpace(*req.Title) == "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "title cannot be empty"})
			return
		}
		title = *req.Title
	}
	if req.Description != nil {
		description = *req.Description
	}

	// When rows weren't provided in the PUT body, rebuild them from the
	// existing record so Update's replace-all semantics don't wipe them.
	var rowsForRepo []repository.RowInput
	if req.RowsProvided {
		built, errMsg := validateAndBuildRows(req.Rows)
		if errMsg != "" {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: errMsg})
			return
		}
		rowsForRepo = built
	} else {
		rowsForRepo = make([]repository.RowInput, 0, len(existing.Rows))
		for _, r := range existing.Rows {
			serverIDs := make([]string, 0, len(r.Servers))
			for _, s := range r.Servers {
				serverIDs = append(serverIDs, s.ServerID)
			}
			rowsForRepo = append(rowsForRepo, repository.RowInput{
				ID: r.ID, Title: r.Title, Body: r.Body, ServerIDs: serverIDs,
			})
		}
	}

	if err := h.instructionRepo.Update(id, title, description, rowsForRepo); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	h.invalidateScopeCaches()

	updated, err := h.instructionRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, toLLMInstructionResponse(updated))
}

func (h *Handler) deleteLLMInstruction(w http.ResponseWriter, r *http.Request, id string) {
	existing, err := h.instructionRepo.GetByID(id)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instruction not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if !isInstructionOwner(r, existing) {
		writeJSON(w, http.StatusForbidden, ErrorResponse{Error: "not your instruction"})
		return
	}
	if err := h.instructionRepo.Delete(id); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	h.invalidateScopeCaches()
	w.WriteHeader(http.StatusNoContent)
}

// getLLMInstructionRendered returns the Markdown string the gateway would
// inject into the MCP `initialize.instructions` field if a session with every
// row's server scope connected. It uses the same gateway.ComposeInstructions
// function as the runtime path, so what the admin sees is exactly what an
// agent receives (modulo scope filtering that happens at request time).
func (h *Handler) getLLMInstructionRendered(w http.ResponseWriter, r *http.Request, id string) {
	ins, err := h.instructionRepo.GetByID(id)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instruction not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if !isInstructionOwner(r, ins) {
		writeJSON(w, http.StatusForbidden, ErrorResponse{Error: "not your instruction"})
		return
	}
	views := make([]gateway.InstructionView, 0, len(ins.Rows))
	for _, r := range ins.Rows {
		views = append(views, gateway.InstructionView{
			ID:    r.ID,
			Title: r.Title,
			Body:  r.Body,
		})
	}
	rendered := gateway.ComposeInstructions(views, "preview:"+id)
	writeJSON(w, http.StatusOK, LLMInstructionRenderedResponse{Markdown: rendered})
}

func (h *Handler) getLLMInstructionUsage(w http.ResponseWriter, r *http.Request, id string) {
	existing, err := h.instructionRepo.GetByID(id)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "instruction not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if !isInstructionOwner(r, existing) {
		writeJSON(w, http.StatusForbidden, ErrorResponse{Error: "not your instruction"})
		return
	}
	usage, err := h.instructionRepo.GetUsage(id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if usage.TokenIDs == nil {
		usage.TokenIDs = []string{}
	}
	if usage.OAuth2ClientIDs == nil {
		usage.OAuth2ClientIDs = []string{}
	}
	writeJSON(w, http.StatusOK, LLMInstructionUsageResponse{
		TokenIDs:        usage.TokenIDs,
		OAuth2ClientIDs: usage.OAuth2ClientIDs,
	})
}

// ── helpers ───────────────────────────────────────────────────────────────────

// enforceSingleInstructionPick rejects payloads that try to attach more than
// one instruction page to a scope token or OAuth2 client. The feature is
// single-select by design; catching this on the API keeps the contract honest
// even if the UI is bypassed. Returns an empty string when the payload is OK.
func enforceSingleInstructionPick(ids []string) string {
	if len(ids) > 1 {
		return "only one instruction page may be attached (got " + strconv.Itoa(len(ids)) + ")"
	}
	return ""
}

// isInstructionOwner reports whether the current session's user email matches
// the page's created_by. Legacy pages with no owner remain accessible to
// everyone (matches tokenRepo / OAuth2Repo semantics). Admins are NOT granted
// a back-door — we deliberately keep the same strict model as tokens so the
// "owns their own config" promise holds across every role.
func isInstructionOwner(r *http.Request, ins *db.LLMInstruction) bool {
	if ins.CreatedBy == "" {
		return true
	}
	return auth.UserEmailFromContext(r.Context()) == ins.CreatedBy
}

// validateAndBuildRows normalises and validates a rows payload. A page must
// contain at least one row; each row must have a non-empty body. Per-server
// rows must additionally declare at least one server link; general rows
// render unconditionally and their server_ids (if any) are dropped.
// Returns (rows, "") on success, (nil, msg) on failure.
func validateAndBuildRows(in []LLMInstructionRowRequest) ([]repository.RowInput, string) {
	if len(in) == 0 {
		return nil, "at least one row is required"
	}
	out := make([]repository.RowInput, 0, len(in))
	for _, r := range in {
		if strings.TrimSpace(r.Body) == "" {
			return nil, "row body cannot be empty"
		}
		kind := r.Kind
		if kind == "" {
			kind = db.LLMInstructionRowKindPerServer
		}
		if kind != db.LLMInstructionRowKindPerServer && kind != db.LLMInstructionRowKindGeneral {
			return nil, "invalid row kind: " + kind
		}
		serverIDs := r.ServerIDs
		if kind == db.LLMInstructionRowKindPerServer && len(serverIDs) == 0 {
			return nil, "per-server rows must target at least one server (use kind=general to apply unconditionally)"
		}
		if kind == db.LLMInstructionRowKindGeneral {
			// General rows disregard any server scope. Clear the list so
			// the DB never carries stale links.
			serverIDs = nil
		}
		out = append(out, repository.RowInput{
			ID:        r.ID,
			Kind:      kind,
			Title:     r.Title,
			Body:      r.Body,
			ServerIDs: serverIDs,
		})
	}
	return out, ""
}

// invalidateScopeCaches forces the next MCP request to refetch its scope from
// the DB, so instruction edits take effect immediately instead of waiting for
// the 60-second token/client cache TTL.
func (h *Handler) invalidateScopeCaches() {
	if h.tokenCache != nil {
		h.tokenCache.InvalidateAll()
	}
	if h.oauth2Cache != nil {
		h.oauth2Cache.InvalidateAll()
	}
}

func splitCSVNonEmpty(s string) []string {
	raw := strings.Split(s, ",")
	out := make([]string, 0, len(raw))
	for _, r := range raw {
		if v := strings.TrimSpace(r); v != "" {
			out = append(out, v)
		}
	}
	return out
}

// remarshal round-trips a decoded map back into a typed struct.
func remarshal(src map[string]json.RawMessage, dst interface{}) error {
	b, err := json.Marshal(src)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, dst)
}
