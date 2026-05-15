package api

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
	"mcp-gateway/internal/urlvalidation"
)

// handleZohoAdmin dispatches the three verbs on /api/v1/zoho-imports/admin.
// Admin-gating happens at the route layer (isAdminOnly match in handler.go).
func (h *Handler) handleZohoAdmin(w http.ResponseWriter, r *http.Request) {
	if h.zohoImportRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "zoho imports not configured"})
		return
	}
	switch r.Method {
	case http.MethodGet:
		h.handleZohoAdminGet(w, r)
	case http.MethodPost:
		h.handleZohoAdminPost(w, r)
	case http.MethodDelete:
		h.handleZohoAdminDelete(w, r)
	default:
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
	}
}

func (h *Handler) handleZohoAdminGet(w http.ResponseWriter, r *http.Request) {
	row, err := h.zohoImportRepo.GetAdmin()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if row == nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "no admin zoho row configured"})
		return
	}
	writeJSON(w, http.StatusOK, zohoAdminToResponse(row, h))
}

func (h *Handler) handleZohoAdminPost(w http.ResponseWriter, r *http.Request) {
	var req ZohoAdminCreateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}
	if req.URL == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "url is required"})
		return
	}
	if err := urlvalidation.ValidateServerURL(req.URL, h.allowInternalURLs); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
		return
	}

	var encrypted []byte
	if len(req.AuthHeaders) > 0 {
		raw, err := json.Marshal(req.AuthHeaders)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "encode auth_headers: " + err.Error()})
			return
		}
		if h.encryptor != nil {
			encrypted, err = h.encryptor.Encrypt(raw)
			if err != nil {
				writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "encrypt auth_headers: " + err.Error()})
				return
			}
		} else {
			encrypted = raw
		}
	}

	existing, err := h.zohoImportRepo.GetAdmin()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}

	in := &db.ZohoImport{
		Name:        req.Name,
		URL:         req.URL,
		AuthHeaders: encrypted,
	}
	row, err := h.zohoImportRepo.UpdateOrCreateAdmin(in)
	if err != nil {
		if errors.Is(err, repository.ErrAdminCreatedByMustBeEmpty) {
			writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
			return
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}

	go discoverZohoToolsForImport(context.Background(), h.zohoImportRepo, h.encryptor, row)

	status := http.StatusCreated
	if existing != nil {
		status = http.StatusOK
	}
	writeJSON(w, status, zohoAdminToResponse(row, h))
}

func (h *Handler) handleZohoAdminDelete(w http.ResponseWriter, r *http.Request) {
	if err := h.zohoImportRepo.DeleteAdmin(); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// handleZohoImports dispatches GET /api/v1/zoho-imports.
// Verb fan-out: PATCH/DELETE go to /api/v1/zoho-imports/{id} via
// handleZohoImportByID; this handler covers the collection path only.
func (h *Handler) handleZohoImports(w http.ResponseWriter, r *http.Request) {
	if h.zohoImportRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "zoho imports not configured"})
		return
	}
	switch r.Method {
	case http.MethodGet:
		h.handleZohoUserList(w, r)
		return
	case http.MethodPost:
		h.handleZohoUserCreate(w, r)
		return
	default:
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}
}

func (h *Handler) handleZohoUserList(w http.ResponseWriter, r *http.Request) {
	filter := repository.ZohoListFilter{
		Search:    r.URL.Query().Get("search"),
		CreatedBy: effectiveCreatorFilter(r.Context()),
	}
	if isAdminParam := r.URL.Query().Get("is_admin"); isAdminParam != "" {
		val := isAdminParam == "true" || isAdminParam == "1"
		filter.IsAdmin = &val
	}
	page := parsePositiveInt(r.URL.Query().Get("page"), 1)
	limit := parsePositiveInt(r.URL.Query().Get("limit"), 20)

	rows, total, err := h.zohoImportRepo.List(filter, page, limit)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}

	out := ZohoImportListResponse{
		Rows:  make([]ZohoImportRowDTO, 0, len(rows)),
		Total: total,
		Page:  page,
		Limit: limit,
	}
	for i := range rows {
		out.Rows = append(out.Rows, zohoImportToRowDTO(&rows[i], h))
	}
	writeJSON(w, http.StatusOK, out)
}

// handleZohoUserCreate inserts a per-user row. CreatedBy must be non-empty
// and unique. Use POST /api/v1/zoho-imports/admin for the singleton admin row.
func (h *Handler) handleZohoUserCreate(w http.ResponseWriter, r *http.Request) {
	var req ZohoUserCreateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}

	req.Name = strings.TrimSpace(req.Name)
	req.URL = strings.TrimSpace(req.URL)
	req.CreatedBy = strings.TrimSpace(req.CreatedBy)
	req.TemplateSlug = strings.TrimSpace(req.TemplateSlug)

	if req.Name == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "name is required"})
		return
	}
	if req.URL == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "url is required"})
		return
	}
	if err := urlvalidation.ValidateServerURL(req.URL, h.allowInternalURLs); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: err.Error()})
		return
	}
	if req.CreatedBy == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "created_by is required"})
		return
	}
	if !strings.Contains(req.CreatedBy, "@") || strings.HasPrefix(req.CreatedBy, "@") || strings.HasSuffix(req.CreatedBy, "@") {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "created_by must look like an email"})
		return
	}
	if req.TemplateSlug == "" {
		req.TemplateSlug = "zoho"
	}

	existing, err := h.zohoImportRepo.FindUserImportByEmail(req.CreatedBy)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if existing != nil {
		writeJSON(w, http.StatusConflict, ErrorResponse{Error: "a zoho import already exists for this created_by"})
		return
	}

	var encrypted []byte
	if len(req.AuthHeaders) > 0 {
		raw, mErr := json.Marshal(req.AuthHeaders)
		if mErr != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "encode auth_headers: " + mErr.Error()})
			return
		}
		if h.encryptor != nil {
			encrypted, mErr = h.encryptor.Encrypt(raw)
			if mErr != nil {
				writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "encrypt auth_headers: " + mErr.Error()})
				return
			}
		} else {
			encrypted = raw
		}
	}

	isActive := true
	if req.IsActive != nil {
		isActive = *req.IsActive
	}

	row := &db.ZohoImport{
		Name:         req.Name,
		URL:          req.URL,
		CreatedBy:    req.CreatedBy,
		TemplateSlug: req.TemplateSlug,
		IsActive:     isActive,
		AuthHeaders:  encrypted,
	}
	if err := h.zohoImportRepo.CreateUserImport(row); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}

	go discoverZohoToolsForImport(context.Background(), h.zohoImportRepo, h.encryptor, row)

	writeJSON(w, http.StatusCreated, zohoImportToRowDTO(row, h))
}

// handleZohoImportByID dispatches GET/PATCH/DELETE on /api/v1/zoho-imports/{id}
// and POST on /api/v1/zoho-imports/{id}/test (delegated to handleZohoImportTest).
func (h *Handler) handleZohoImportByID(w http.ResponseWriter, r *http.Request) {
	if h.zohoImportRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "zoho imports not configured"})
		return
	}

	id, rest := splitZohoImportPath(r.URL.Path)
	if id == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "missing zoho import id"})
		return
	}

	if rest == "test" {
		h.handleZohoImportTest(w, r, id)
		return
	}
	if rest == "discover" {
		h.handleZohoImportDiscover(w, r, id)
		return
	}
	if rest == "tools" {
		h.handleZohoImportTools(w, r, id)
		return
	}
	if rest != "" {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "unknown subroute"})
		return
	}

	switch r.Method {
	case http.MethodGet:
		row, err := h.zohoImportRepo.GetByID(id)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
			return
		}
		if row == nil {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
			return
		}
		writeJSON(w, http.StatusOK, zohoImportToRowDTO(row, h))
	case http.MethodPatch:
		h.handleZohoImportPatch(w, r, id)
	case http.MethodDelete:
		h.handleZohoImportDelete(w, r, id)
	default:
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
	}
}

// handleZohoImportDiscover synchronously re-fetches the tool catalog from
// the row's upstream URL with its decrypted headers and atomically swaps
// it into zoho_import_tools. Returns the count actually persisted so the
// operator can confirm at-a-glance.
func (h *Handler) handleZohoImportDiscover(w http.ResponseWriter, r *http.Request, id string) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}
	row, err := h.zohoImportRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if row == nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
		return
	}
	tools, fetchErr := fetchZohoTools(r.Context(), h.encryptor, row)
	if fetchErr != nil {
		writeJSON(w, http.StatusBadGateway, ErrorResponse{Error: fetchErr.Error()})
		return
	}
	count, perr := h.zohoImportRepo.ReplaceTools(row.ID, tools)
	if perr != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: perr.Error()})
		return
	}
	log.Printf("[zoho-discover] import=%s manual refresh tools=%d", row.ID, count)
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "tools": count})
}

// handleZohoImportTools returns the persisted tool catalog for one import row.
// Read-only — refresh via POST /api/v1/zoho-imports/{id}/discover.
func (h *Handler) handleZohoImportTools(w http.ResponseWriter, r *http.Request, id string) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}
	row, err := h.zohoImportRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if row == nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
		return
	}
	tools, err := h.zohoImportRepo.ListTools(id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	out := ZohoImportToolsResponse{
		Tools: make([]ZohoImportToolDTO, 0, len(tools)),
		Total: len(tools),
	}
	for i := range tools {
		out.Tools = append(out.Tools, zohoImportToolToDTO(&tools[i]))
	}
	writeJSON(w, http.StatusOK, out)
}

// splitZohoImportPath parses "/api/v1/zoho-imports/{id}" or
// "/api/v1/zoho-imports/{id}/test" and returns (id, subroute).
// Returns ("", "") when the path doesn't match.
func splitZohoImportPath(p string) (string, string) {
	const prefix = "/api/v1/zoho-imports/"
	if !strings.HasPrefix(p, prefix) {
		return "", ""
	}
	rest := strings.TrimPrefix(p, prefix)
	parts := strings.SplitN(rest, "/", 2)
	if len(parts) == 1 {
		return parts[0], ""
	}
	return parts[0], parts[1]
}

// parsePositiveInt returns def when the input is empty, unparseable, or < 1.
func parsePositiveInt(s string, def int) int {
	if s == "" {
		return def
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 1 {
		return def
	}
	return n
}

// zohoImportToRowDTO renders a row into the wire shape, decrypting auth_headers
// only to extract key names (values redacted).
func zohoImportToRowDTO(row *db.ZohoImport, h *Handler) ZohoImportRowDTO {
	keys := make([]string, 0)
	if len(row.AuthHeaders) > 0 && h.encryptor != nil {
		if pt, err := h.encryptor.Decrypt(row.AuthHeaders); err == nil {
			var m map[string]string
			if json.Unmarshal(pt, &m) == nil {
				for k := range m {
					keys = append(keys, k)
				}
			}
		}
	}
	return ZohoImportRowDTO{
		ID:             row.ID,
		Name:           row.Name,
		URL:            row.URL,
		IsAdmin:        row.IsAdmin,
		IsActive:       row.IsActive,
		CreatedBy:      row.CreatedBy,
		TemplateSlug:   row.TemplateSlug,
		AuthHeaderKeys: keys,
		CreatedAt:      row.CreatedAt.UTC().Format(time.RFC3339),
		UpdatedAt:      row.UpdatedAt.UTC().Format(time.RFC3339),
	}
}

func (h *Handler) handleZohoImportPatch(w http.ResponseWriter, r *http.Request, id string) {
	var req ZohoImportUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}
	if req.Name == nil && req.URL == nil && req.AuthHeaders == nil && req.IsActive == nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "no fields to update"})
		return
	}

	patch := repository.ZohoUpdatePatch{
		Name:     req.Name,
		URL:      req.URL,
		IsActive: req.IsActive,
	}
	if req.AuthHeaders != nil {
		var encrypted []byte
		if len(*req.AuthHeaders) > 0 {
			raw, err := json.Marshal(*req.AuthHeaders)
			if err != nil {
				writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "encode auth_headers: " + err.Error()})
				return
			}
			if h.encryptor != nil {
				encrypted, err = h.encryptor.Encrypt(raw)
				if err != nil {
					writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "encrypt: " + err.Error()})
					return
				}
			} else {
				encrypted = raw
			}
		} else {
			encrypted = []byte{}
		}
		patch.AuthHeaders = &encrypted
	}

	row, err := h.zohoImportRepo.Update(id, patch)
	if err != nil {
		if errors.Is(err, repository.ErrZohoImportNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, zohoImportToRowDTO(row, h))
}

func (h *Handler) handleZohoImportDelete(w http.ResponseWriter, _ *http.Request, id string) {
	row, err := h.zohoImportRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if row == nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
		return
	}
	if row.IsAdmin {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "use /api/v1/zoho-imports/admin to delete the admin row"})
		return
	}

	if err := h.zohoImportRepo.DeleteByID(id); err != nil {
		if errors.Is(err, repository.ErrZohoImportNotFound) {
			writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *Handler) handleZohoImportTest(w http.ResponseWriter, r *http.Request, id string) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}

	row, err := h.zohoImportRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: err.Error()})
		return
	}
	if row == nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "not found"})
		return
	}

	headers := map[string]string{}
	if len(row.AuthHeaders) > 0 && h.encryptor != nil {
		if pt, derr := h.encryptor.Decrypt(row.AuthHeaders); derr == nil {
			_ = json.Unmarshal(pt, &headers)
		}
	}

	const probeBody = `{"jsonrpc":"2.0","method":"tools/list","id":1}`
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	probeReq, rerr := http.NewRequestWithContext(ctx, http.MethodPost, row.URL, strings.NewReader(probeBody))
	if rerr != nil {
		writeJSON(w, http.StatusOK, ZohoImportTestResponse{OK: false, Error: rerr.Error()})
		return
	}
	probeReq.Header.Set("Content-Type", "application/json")
	for k, v := range headers {
		probeReq.Header.Set(k, v)
	}

	log.Printf("[zoho-imports] test row id=%s by admin", row.ID)

	start := time.Now()
	resp, perr := http.DefaultClient.Do(probeReq)
	latency := time.Since(start).Milliseconds()
	out := ZohoImportTestResponse{LatencyMs: latency}
	if perr != nil {
		out.OK = false
		if errors.Is(perr, context.DeadlineExceeded) {
			out.Error = "timeout"
		} else {
			out.Error = perr.Error()
		}
		writeJSON(w, http.StatusOK, out)
		return
	}
	defer resp.Body.Close()

	out.StatusCode = resp.StatusCode
	out.OK = resp.StatusCode >= 200 && resp.StatusCode < 400
	if out.OK {
		// Reuse the same probe to refresh the persisted catalog for this row.
		// Fire-and-forget so a downstream decode failure never flips the test
		// result the operator sees.
		go discoverZohoToolsForImport(context.Background(), h.zohoImportRepo, h.encryptor, row)
	}
	writeJSON(w, http.StatusOK, out)
}

// zohoAdminToResponse renders a row into the wire shape, decrypting
// auth_headers only to extract key names (values stay redacted).
func zohoAdminToResponse(row *db.ZohoImport, h *Handler) ZohoAdminResponse {
	keys := make([]string, 0)
	if len(row.AuthHeaders) > 0 {
		var rawHeaders []byte
		if h.encryptor != nil {
			if pt, err := h.encryptor.Decrypt(row.AuthHeaders); err == nil {
				rawHeaders = pt
			}
		} else {
			rawHeaders = row.AuthHeaders
		}
		if rawHeaders != nil {
			var m map[string]string
			if json.Unmarshal(rawHeaders, &m) == nil {
				for k := range m {
					keys = append(keys, k)
				}
			}
		}
	}
	return ZohoAdminResponse{
		ID:             row.ID,
		Name:           row.Name,
		URL:            row.URL,
		IsActive:       row.IsActive,
		AuthHeaderKeys: keys,
		CreatedAt:      row.CreatedAt.UTC().Format(time.RFC3339),
		UpdatedAt:      row.UpdatedAt.UTC().Format(time.RFC3339),
	}
}
