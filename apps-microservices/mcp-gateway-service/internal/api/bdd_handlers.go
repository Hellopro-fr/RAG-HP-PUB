package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strconv"
	"strings"

	"github.com/hellopro/mcp-gateway/internal/auth"
	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/repository"
)

// bddIdentRe matches table_name and field_name values: 1-128 chars,
// alphanumeric + underscore. Mirrors the upstream catalog's identifier
// shape to avoid round-trip surprises.
var bddIdentRe = regexp.MustCompile(`^[a-zA-Z0-9_]{1,128}$`)

// validBDDDatabaseIDs is the closed set of database IDs the gateway
// accepts when registering a "used" table. Matches the production
// Hellopro database inventory at the time of writing.
var validBDDDatabaseIDs = map[int]bool{1: true, 5: true, 10: true}

// SetBDDUsedRepo wires the BDD registry repository.
func (h *Handler) SetBDDUsedRepo(repo *repository.BDDUsedRepo) {
	h.bddUsedRepo = repo
}

// scopeTokenBDDFilterToDTO renders a token's persisted BDD scope into the
// response DTO. Returns nil when the token has no BDD restriction so the
// JSON omits the field entirely (matches the Leexi filter convention).
func scopeTokenBDDFilterToDTO(t *db.ScopeToken) *BDDFilterDTO {
	if len(t.BDDTables) == 0 {
		return nil
	}
	ids := make([]string, 0, len(t.BDDTables))
	for _, b := range t.BDDTables {
		ids = append(ids, b.UsedTableID)
	}
	return &BDDFilterDTO{UsedTableIDs: ids}
}

// oauth2ClientBDDFilterToDTO is the OAuth2 equivalent of
// scopeTokenBDDFilterToDTO. Same shape, different join row type.
func oauth2ClientBDDFilterToDTO(c *db.OAuth2Client) *BDDFilterDTO {
	if len(c.BDDTables) == 0 {
		return nil
	}
	ids := make([]string, 0, len(c.BDDTables))
	for _, b := range c.BDDTables {
		ids = append(ids, b.UsedTableID)
	}
	return &BDDFilterDTO{UsedTableIDs: ids}
}

// handleBDDUsedTables routes /api/v1/bdd/used/tables (no id segment).
func (h *Handler) handleBDDUsedTables(w http.ResponseWriter, r *http.Request) {
	if h.bddUsedRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "BDD registry is not configured"})
		return
	}
	switch r.Method {
	case http.MethodGet:
		h.listBDDUsedTables(w, r)
	case http.MethodPost:
		h.createBDDUsedTable(w, r)
	default:
		w.Header().Set("Allow", "GET, POST")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
	}
}

// handleBDDUsedTableByID routes the /{id} and /{id}/fields[/{field_id}]
// sub-tree. Path parsing mirrors the Leexi/OAuth2 admin handlers — we
// don't pull in a router just for two segments.
func (h *Handler) handleBDDUsedTableByID(w http.ResponseWriter, r *http.Request) {
	if h.bddUsedRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "BDD registry is not configured"})
		return
	}

	rest := strings.TrimPrefix(r.URL.Path, "/api/v1/bdd/used/tables/")
	if rest == "" {
		http.NotFound(w, r)
		return
	}
	parts := strings.Split(rest, "/")
	id := parts[0]
	if id == "" {
		http.NotFound(w, r)
		return
	}

	switch len(parts) {
	case 1:
		h.routeBDDTableByID(w, r, id)
	case 2:
		// /{id}/fields — only POST allowed
		if parts[1] != "fields" {
			http.NotFound(w, r)
			return
		}
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
			return
		}
		h.addBDDUsedField(w, r, id)
	case 3:
		// /{id}/fields/{field_id}
		if parts[1] != "fields" {
			http.NotFound(w, r)
			return
		}
		fieldID := parts[2]
		if fieldID == "" {
			http.NotFound(w, r)
			return
		}
		h.routeBDDFieldByID(w, r, id, fieldID)
	default:
		http.NotFound(w, r)
	}
}

func (h *Handler) routeBDDTableByID(w http.ResponseWriter, r *http.Request, id string) {
	switch r.Method {
	case http.MethodGet:
		h.getBDDUsedTable(w, r, id)
	case http.MethodPatch:
		h.updateBDDUsedTable(w, r, id)
	case http.MethodDelete:
		h.deleteBDDUsedTable(w, r, id)
	default:
		w.Header().Set("Allow", "GET, PATCH, DELETE")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
	}
}

func (h *Handler) routeBDDFieldByID(w http.ResponseWriter, r *http.Request, tableID, fieldID string) {
	switch r.Method {
	case http.MethodPatch:
		h.updateBDDUsedField(w, r, tableID, fieldID)
	case http.MethodDelete:
		h.deleteBDDUsedField(w, r, fieldID)
	default:
		w.Header().Set("Allow", "PATCH, DELETE")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
	}
}

// ── List ──────────────────────────────────────────────────────────────────

func (h *Handler) listBDDUsedTables(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()

	var dbIDPtr *int
	if raw := strings.TrimSpace(q.Get("database_id")); raw != "" {
		v, err := strconv.Atoi(raw)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "database_id must be an integer"})
			return
		}
		dbIDPtr = &v
	}
	search := strings.TrimSpace(q.Get("search"))

	rows, err := h.bddUsedRepo.ListTables(r.Context(), dbIDPtr, search)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	out := make([]BDDUsedTableDTO, 0, len(rows))
	for _, t := range rows {
		out = append(out, toBDDUsedTableDTO(t))
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"tables": out})
}

// ── Create ────────────────────────────────────────────────────────────────

func (h *Handler) createBDDUsedTable(w http.ResponseWriter, r *http.Request) {
	var req CreateBDDUsedTableRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON body"})
		return
	}

	if !validBDDDatabaseIDs[req.DatabaseID] {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "database_id must be one of 1, 5, 10"})
		return
	}
	req.TableName = strings.TrimSpace(req.TableName)
	if !bddIdentRe.MatchString(req.TableName) {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "table_name must match ^[a-zA-Z0-9_]{1,128}$"})
		return
	}
	for i, f := range req.Fields {
		name := strings.TrimSpace(f.FieldName)
		if !bddIdentRe.MatchString(name) {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "fields[" + strconv.Itoa(i) + "].field_name must match ^[a-zA-Z0-9_]{1,128}$"})
			return
		}
		req.Fields[i].FieldName = name
	}

	creator := auth.UserEmailFromContext(r.Context())

	table := &db.BDDUsedTable{
		DatabaseID:      req.DatabaseID,
		Name:            req.TableName,
		Description:     req.Description,
		UpstreamTableID: req.UpstreamTableID,
		CreatedBy:       creator,
	}
	fields := make([]db.BDDUsedField, 0, len(req.Fields))
	for _, f := range req.Fields {
		fields = append(fields, db.BDDUsedField{
			FieldName:       f.FieldName,
			Description:     f.Description,
			UpstreamFieldID: f.UpstreamFieldID,
		})
	}

	created, err := h.bddUsedRepo.CreateTable(r.Context(), table, fields)
	if err != nil {
		switch {
		case errors.Is(err, repository.ErrBDDDuplicateTable):
			writeJSON(w, http.StatusConflict, map[string]string{"error": "table already registered for this database"})
		case errors.Is(err, repository.ErrBDDDuplicateField):
			writeJSON(w, http.StatusConflict, map[string]string{"error": "duplicate field name in payload"})
		default:
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		}
		return
	}

	writeJSON(w, http.StatusCreated, toBDDUsedTableDTO(*created))
}

// ── Get ───────────────────────────────────────────────────────────────────

func (h *Handler) getBDDUsedTable(w http.ResponseWriter, r *http.Request, id string) {
	t, err := h.bddUsedRepo.GetTable(r.Context(), id)
	if err != nil {
		if errors.Is(err, repository.ErrBDDNotFound) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "table not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, toBDDUsedTableDTO(*t))
}

// ── Update table description ─────────────────────────────────────────────

func (h *Handler) updateBDDUsedTable(w http.ResponseWriter, r *http.Request, id string) {
	var req UpdateBDDUsedTableRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON body"})
		return
	}

	if err := h.bddUsedRepo.UpdateTableDescription(r.Context(), id, req.Description); err != nil {
		if errors.Is(err, repository.ErrBDDNotFound) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "table not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	t, err := h.bddUsedRepo.GetTable(r.Context(), id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, toBDDUsedTableDTO(*t))
}

// ── Delete table ─────────────────────────────────────────────────────────

func (h *Handler) deleteBDDUsedTable(w http.ResponseWriter, r *http.Request, id string) {
	if err := h.bddUsedRepo.DeleteTable(r.Context(), id); err != nil {
		if errors.Is(err, repository.ErrBDDNotFound) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "table not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	// Invalidate scope-token and OAuth2-client caches so any live entries
	// referencing the deleted used-table re-resolve their BDD scope on the
	// next request. Without this, a cached entry could still emit the
	// dangling ID until its TTL expires. Mirrors the Leexi-table pattern
	// used by token / OAuth2 mutation handlers.
	if h.tokenCache != nil {
		h.tokenCache.InvalidateAll()
	}
	if h.oauth2Cache != nil {
		h.oauth2Cache.InvalidateAll()
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── Add field ────────────────────────────────────────────────────────────

func (h *Handler) addBDDUsedField(w http.ResponseWriter, r *http.Request, tableID string) {
	var req AddBDDUsedFieldRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON body"})
		return
	}
	req.FieldName = strings.TrimSpace(req.FieldName)
	if !bddIdentRe.MatchString(req.FieldName) {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "field_name must match ^[a-zA-Z0-9_]{1,128}$"})
		return
	}

	field := &db.BDDUsedField{
		FieldName:       req.FieldName,
		Description:     req.Description,
		UpstreamFieldID: req.UpstreamFieldID,
	}
	created, err := h.bddUsedRepo.AddField(r.Context(), tableID, field)
	if err != nil {
		switch {
		case errors.Is(err, repository.ErrBDDNotFound):
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "table not found"})
		case errors.Is(err, repository.ErrBDDDuplicateField):
			writeJSON(w, http.StatusConflict, map[string]string{"error": "field already registered for this table"})
		default:
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		}
		return
	}
	writeJSON(w, http.StatusCreated, toBDDFieldDTO(*created))
}

// ── Update field description ─────────────────────────────────────────────

func (h *Handler) updateBDDUsedField(w http.ResponseWriter, r *http.Request, tableID, fieldID string) {
	var req UpdateBDDUsedFieldRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON body"})
		return
	}
	if err := h.bddUsedRepo.UpdateFieldDescription(r.Context(), fieldID, req.Description); err != nil {
		if errors.Is(err, repository.ErrBDDNotFound) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "field not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	// Re-fetch the parent table (with fields preloaded) and pick the matching
	// field so the response carries the full refreshed row, not just the
	// patched columns. Avoids extending the repo with a dedicated GetField.
	parent, err := h.bddUsedRepo.GetTable(r.Context(), tableID)
	if err != nil {
		if errors.Is(err, repository.ErrBDDNotFound) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "table not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	for _, f := range parent.Fields {
		if f.ID == fieldID {
			writeJSON(w, http.StatusOK, toBDDFieldDTO(f))
			return
		}
	}
	writeJSON(w, http.StatusNotFound, map[string]string{"error": "field not found"})
}

// ── Delete field ─────────────────────────────────────────────────────────

func (h *Handler) deleteBDDUsedField(w http.ResponseWriter, r *http.Request, fieldID string) {
	if err := h.bddUsedRepo.DeleteField(r.Context(), fieldID); err != nil {
		if errors.Is(err, repository.ErrBDDNotFound) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "field not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
