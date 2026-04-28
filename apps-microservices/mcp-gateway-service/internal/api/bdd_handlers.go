package api

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/hellopro/mcp-gateway/internal/auth"
	"github.com/hellopro/mcp-gateway/internal/bddcatalog"
	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/repository"
)

// bddPublicMaxRows / bddPublicMySQLTimeoutMs are the defaults emitted by
// the public config endpoint. They mirror the values used historically
// in the PHP MCP runner config.php so the runner gets identical limits
// without any extra wiring on its side.
const (
	bddPublicMaxRows         = 500
	bddPublicMySQLTimeoutMs  = 90000
	bddPublicDefaultDBKey    = "mysql"
)

// bddPublicDBKeyByID maps the registered database_id to the connection
// key the PHP runner expects in `table_database_map`. Tables on the
// default DB (BO = 1) are omitted from the map (the runner falls back
// to "mysql"). Unknown IDs default to "mysql" too — the runner cannot
// route them anyway, so silently grouping them under default is safer
// than emitting an unknown key.
var bddPublicDBKeyByID = map[int]string{
	1:  bddPublicDefaultDBKey,
	5:  "mysql_hpdata",
	10: "mysql_hellopro_ia",
}

// bddIdentRe matches table_name and field_name values: 1-128 chars,
// alphanumeric + underscore. Mirrors the upstream catalog's identifier
// shape to avoid round-trip surprises.
var bddIdentRe = regexp.MustCompile(`^[a-zA-Z0-9_]{1,128}$`)

// bddImportMaxBody caps the registry import JSON at 1 MiB. The same
// rationale as templates' 256 KB cap (DoS guard) but with more
// headroom because the registry can grow much larger than the seeded
// template catalog.
const bddImportMaxBody = 1 * 1024 * 1024

// bddBulkMaxItems caps the number of rows in a single bulk-create
// request. Beyond this the client should issue a follow-up batch.
const bddBulkMaxItems = 50

// defaultBDDListLimit / maxBDDListLimit bound the page size for
// GET /api/v1/bdd/used/tables. The default keeps payloads small for
// the common UI grid; the max protects the gateway from clients that
// try to pull the whole registry at once.
const (
	defaultBDDListLimit = 20
	maxBDDListLimit     = 100
)

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
	// Defence-in-depth: "bulk", "export" and "import" are reserved
	// sub-paths registered with exact handlers in handler.go. net/http
	// already routes them away from here because longer-literal match
	// wins, but if that ever regresses we don't want to parse those
	// strings as a UUID.
	if len(parts) == 1 && (id == "bulk" || id == "export" || id == "import" || id == "import-doc" || id == "doc") {
		http.NotFound(w, r)
		return
	}

	switch len(parts) {
	case 1:
		h.routeBDDTableByID(w, r, id)
	case 2:
		switch parts[1] {
		case "fields":
			if r.Method != http.MethodPost {
				w.Header().Set("Allow", "POST")
				writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
				return
			}
			h.addBDDUsedField(w, r, id)
		case "refresh-catalog":
			if r.Method != http.MethodPost {
				w.Header().Set("Allow", "POST")
				writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
				return
			}
			h.handleBDDUsedRefreshCatalog(w, r, id)
		default:
			http.NotFound(w, r)
		}
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
		// 0 is treated as "no filter" so a stale ?database_id=0 from a
		// frontend dropdown reset doesn't accidentally hide every row.
		if v != 0 {
			dbIDPtr = &v
		}
	}
	search := strings.TrimSpace(q.Get("search"))

	page := 1
	if raw := strings.TrimSpace(q.Get("page")); raw != "" {
		v, err := strconv.Atoi(raw)
		if err != nil || v < 1 {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "page must be a positive integer"})
			return
		}
		page = v
	}
	limit := defaultBDDListLimit
	if raw := strings.TrimSpace(q.Get("limit")); raw != "" {
		v, err := strconv.Atoi(raw)
		if err != nil || v < 1 {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "limit must be a positive integer"})
			return
		}
		if v > maxBDDListLimit {
			v = maxBDDListLimit
		}
		limit = v
	}

	rows, total, err := h.bddUsedRepo.ListTables(r.Context(), repository.ListTablesOptions{
		DatabaseID: dbIDPtr,
		Search:     search,
		Limit:      limit,
		Offset:     (page - 1) * limit,
	})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	out := make([]BDDUsedTableDTO, 0, len(rows))
	for _, t := range rows {
		out = append(out, toBDDUsedTableDTO(t))
	}
	writeJSON(w, http.StatusOK, BDDUsedListResponse{
		Tables: out,
		Total:  total,
		Page:   page,
		Limit:  limit,
	})
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
			FieldType:       f.FieldType,
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

	updates := map[string]interface{}{}
	if req.Description != nil {
		updates["description"] = *req.Description
	}
	if req.DefaultOrderBy != nil {
		updates["default_order_by"] = *req.DefaultOrderBy
	}
	if req.Relations != nil {
		// Empty array / object both encode "no relations". Persist verbatim
		// so round-trip with the doc payload stays bit-identical.
		updates["relations"] = []byte(req.Relations)
	}
	if req.Notes != nil {
		updates["notes"] = *req.Notes
	}

	if err := h.bddUsedRepo.UpdateTableMetadata(r.Context(), id, updates); err != nil {
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
		FieldType:       req.FieldType,
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

// ── Bulk create ──────────────────────────────────────────────────────────

// handleBDDUsedBulkCreate handles POST /api/v1/bdd/used/tables/bulk.
// Per-item validation failures are collected into the response's errors
// array so a single bad row does NOT abort an otherwise-valid batch.
// Status code semantics: 201 = every row created, 200 = mixed, 400 =
// every row failed (typically all-duplicate or all-invalid input).
func (h *Handler) handleBDDUsedBulkCreate(w http.ResponseWriter, r *http.Request) {
	if h.bddUsedRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "BDD registry is not configured"})
		return
	}
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}

	var req BulkCreateBDDUsedTablesRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON body"})
		return
	}
	if !validBDDDatabaseIDs[req.DatabaseID] {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "database_id must be one of 1, 5, 10"})
		return
	}
	if len(req.Items) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "items must not be empty"})
		return
	}
	if len(req.Items) > bddBulkMaxItems {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "items: too many entries (max " + strconv.Itoa(bddBulkMaxItems) + ")",
		})
		return
	}

	// First pass: validate names locally. Bad rows are collected into errors
	// and never reach the repo. Valid rows are forwarded preserving their
	// original order so the per-item result mapping is straightforward.
	errs := make([]BulkCreateBDDUsedTableError, 0)
	validItems := make([]repository.BulkCreateItem, 0, len(req.Items))
	for _, it := range req.Items {
		name := strings.TrimSpace(it.TableName)
		if !bddIdentRe.MatchString(name) {
			errs = append(errs, BulkCreateBDDUsedTableError{
				TableName: it.TableName,
				Error:     "table_name must match ^[a-zA-Z0-9_]{1,128}$",
			})
			continue
		}
		validItems = append(validItems, repository.BulkCreateItem{
			TableName:       name,
			Description:     it.Description,
			UpstreamTableID: it.UpstreamTableID,
		})
	}

	created := make([]BDDUsedTableDTO, 0, len(validItems))
	if len(validItems) > 0 {
		creator := auth.UserEmailFromContext(r.Context())
		results, err := h.bddUsedRepo.BulkCreate(r.Context(), req.DatabaseID, validItems, creator)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
		for _, res := range results {
			switch {
			case res.Err == nil && res.Table != nil:
				created = append(created, toBDDUsedTableDTO(*res.Table))
			case errors.Is(res.Err, repository.ErrBDDDuplicateTable):
				errs = append(errs, BulkCreateBDDUsedTableError{
					TableName: res.TableName,
					Error:     "table already registered for this database",
				})
			default:
				errs = append(errs, BulkCreateBDDUsedTableError{
					TableName: res.TableName,
					Error:     res.Err.Error(),
				})
			}
		}
	}

	resp := BulkCreateBDDUsedTablesResponse{Created: created, Errors: errs}
	switch {
	case len(created) == 0:
		writeJSON(w, http.StatusBadRequest, resp)
	case len(errs) == 0:
		writeJSON(w, http.StatusCreated, resp)
	default:
		writeJSON(w, http.StatusOK, resp)
	}
}

// ── Export ───────────────────────────────────────────────────────────────

// handleBDDUsedExport handles GET /api/v1/bdd/used/tables/export. The
// response is streamed as a JSON download attachment so admins can save
// the registry snapshot for replay on another environment.
func (h *Handler) handleBDDUsedExport(w http.ResponseWriter, r *http.Request) {
	if h.bddUsedRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "BDD registry is not configured"})
		return
	}
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}

	rows, err := h.bddUsedRepo.ListAll(r.Context())
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	out := BDDExportPayload{
		Version:    1,
		ExportedAt: time.Now().UTC(),
		Tables:     make([]BDDExportedTable, 0, len(rows)),
	}
	for _, t := range rows {
		fields := make([]BDDExportedField, 0, len(t.Fields))
		for _, f := range t.Fields {
			fields = append(fields, BDDExportedField{
				FieldName:       f.FieldName,
				FieldType:       f.FieldType,
				Description:     f.Description,
				UpstreamFieldID: f.UpstreamFieldID,
			})
		}
		out.Tables = append(out.Tables, BDDExportedTable{
			DatabaseID:      t.DatabaseID,
			TableName:       t.Name,
			Description:     t.Description,
			UpstreamTableID: t.UpstreamTableID,
			Rows:            t.Rows,
			PrimaryKey:      t.PrimaryKey,
			DefaultOrderBy:  t.DefaultOrderBy,
			Relations:       t.Relations,
			Notes:           t.Notes,
			Fields:          fields,
		})
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Content-Disposition", `attachment; filename="bdd-tables-export.json"`)
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(out)
}

// ── Import ───────────────────────────────────────────────────────────────

// handleBDDUsedImport handles POST /api/v1/bdd/used/tables/import.
// Behaviour: per-row upsert keyed on (database_id, table_name). Existing
// rows have their description + upstream_table_id refreshed and their
// fields atomically replaced. Per-row failures are collected and the
// transaction is NOT aborted on the first bad row.
func (h *Handler) handleBDDUsedImport(w http.ResponseWriter, r *http.Request) {
	if h.bddUsedRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "BDD registry is not configured"})
		return
	}
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, bddImportMaxBody)
	body, err := io.ReadAll(r.Body)
	if err != nil {
		var mbe *http.MaxBytesError
		if errors.As(err, &mbe) {
			writeJSON(w, http.StatusRequestEntityTooLarge, map[string]string{"error": "payload too large (max 1 MiB)"})
			return
		}
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "read body: " + err.Error()})
		return
	}

	var payload BDDExportPayload
	if err := json.Unmarshal(body, &payload); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON: " + err.Error()})
		return
	}
	if payload.Tables == nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "missing tables: []"})
		return
	}

	rows := make([]db.BDDUsedTable, 0, len(payload.Tables))
	respErrs := make([]BDDImportError, 0)
	for idx, t := range payload.Tables {
		name := strings.TrimSpace(t.TableName)
		if !validBDDDatabaseIDs[t.DatabaseID] {
			respErrs = append(respErrs, BDDImportError{
				DatabaseID: t.DatabaseID,
				TableName:  t.TableName,
				Error:      "database_id must be one of 1, 5, 10",
			})
			continue
		}
		if !bddIdentRe.MatchString(name) {
			respErrs = append(respErrs, BDDImportError{
				DatabaseID: t.DatabaseID,
				TableName:  t.TableName,
				Error:      "tables[" + strconv.Itoa(idx) + "].table_name invalid",
			})
			continue
		}
		row := db.BDDUsedTable{
			DatabaseID:      t.DatabaseID,
			Name:            name,
			Description:     t.Description,
			UpstreamTableID: t.UpstreamTableID,
			Rows:            t.Rows,
			PrimaryKey:      t.PrimaryKey,
			DefaultOrderBy:  t.DefaultOrderBy,
			Relations:       t.Relations,
			Notes:           t.Notes,
		}
		for _, f := range t.Fields {
			fname := strings.TrimSpace(f.FieldName)
			if !bddIdentRe.MatchString(fname) {
				respErrs = append(respErrs, BDDImportError{
					DatabaseID: t.DatabaseID,
					TableName:  t.TableName,
					Error:      "field_name " + f.FieldName + " is invalid",
				})
				row = db.BDDUsedTable{} // mark skipped
				break
			}
			row.Fields = append(row.Fields, db.BDDUsedField{
				FieldName:       fname,
				FieldType:       f.FieldType,
				Description:     f.Description,
				UpstreamFieldID: f.UpstreamFieldID,
			})
		}
		// row.Name == "" means the inner-field validation flagged it; skip.
		if row.Name == "" {
			continue
		}
		rows = append(rows, row)
	}

	creator := auth.UserEmailFromContext(r.Context())
	inserted, updated, repoErrs, err := h.bddUsedRepo.Import(r.Context(), rows, creator)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	for _, e := range repoErrs {
		respErrs = append(respErrs, BDDImportError{
			DatabaseID: e.DatabaseID,
			TableName:  e.TableName,
			Error:      e.Err.Error(),
		})
	}

	// Cache invalidation mirrors the delete path: any cached scope-token /
	// OAuth2-client entry that referenced a now-replaced field set must
	// re-resolve to avoid serving stale data.
	if h.tokenCache != nil {
		h.tokenCache.InvalidateAll()
	}
	if h.oauth2Cache != nil {
		h.oauth2Cache.InvalidateAll()
	}

	writeJSON(w, http.StatusOK, BDDImportResponse{
		Inserted: inserted,
		Updated:  updated,
		Errors:   respErrs,
	})
}

// ── Meta ─────────────────────────────────────────────────────────────────

// handleBDDUsedMeta routes GET / PUT /api/v1/bdd/used/meta. Used by the
// admin UI to edit the singleton header that decorates the doc payload's
// _meta block.
func (h *Handler) handleBDDUsedMeta(w http.ResponseWriter, r *http.Request) {
	if h.bddUsedRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "BDD registry is not configured"})
		return
	}
	switch r.Method {
	case http.MethodGet:
		row, err := h.bddUsedRepo.GetMeta(r.Context())
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, toBDDMetaDTO(*row))
	case http.MethodPut:
		var req UpdateBDDMetaRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON body"})
			return
		}
		updater := auth.UserEmailFromContext(r.Context())
		row, err := h.bddUsedRepo.UpsertMeta(r.Context(), req.Description, req.Usage, updater)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, toBDDMetaDTO(*row))
	default:
		w.Header().Set("Allow", "GET, PUT")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
	}
}

// ── Doc ──────────────────────────────────────────────────────────────────

// handleBDDUsedDoc handles GET /api/v1/bdd/used/tables/doc.
//
// Emits the documentation payload consumed by the bdd_get_table_doc tool:
// a top-level _meta header followed by one entry per registered table,
// keyed by table name. Field types are taken from the gateway's snapshot
// (bdd_used_fields.field_type) so the call is offline.
func (h *Handler) handleBDDUsedDoc(w http.ResponseWriter, r *http.Request) {
	if h.bddUsedRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "BDD registry is not configured"})
		return
	}
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}

	rows, err := h.bddUsedRepo.ListAll(r.Context())
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	meta, err := h.bddUsedRepo.GetMeta(r.Context())
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	latest, err := h.bddUsedRepo.LatestUpdatedAt(r.Context())
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	if latest.IsZero() && !meta.UpdatedAt.IsZero() {
		latest = meta.UpdatedAt
	}

	// Use an ordered marshalling pass so _meta lands first and tables
	// appear in registry order. json.Marshal of a struct keeps field
	// declaration order; using a struct + a typed map keeps it human-
	// readable while still matching the target shape.
	type orderedDoc struct {
		Meta   BDDDocMeta             `json:"_meta"`
		Tables map[string]BDDDocTable `json:"-"`
	}

	doc := orderedDoc{
		Meta: BDDDocMeta{
			Description: meta.Description,
			Usage:       meta.Usage,
			LastUpdated: formatBDDLastUpdated(latest),
		},
		Tables: make(map[string]BDDDocTable, len(rows)),
	}
	for _, t := range rows {
		cols := make(map[string]BDDDocColumn, len(t.Fields))
		for _, f := range t.Fields {
			cols[f.FieldName] = BDDDocColumn{
				Type: f.FieldType,
				Desc: f.Description,
			}
		}
		var pkPtr *string
		if t.PrimaryKey != "" {
			s := t.PrimaryKey
			pkPtr = &s
		}
		var orderPtr *string
		if t.DefaultOrderBy != "" {
			s := t.DefaultOrderBy
			orderPtr = &s
		}
		relations := t.Relations
		if len(relations) == 0 {
			relations = json.RawMessage(`[]`)
		}
		doc.Tables[t.Name] = BDDDocTable{
			Description:    t.Description,
			Rows:           t.Rows,
			PrimaryKey:     pkPtr,
			DefaultOrderBy: orderPtr,
			Columns:        cols,
			Relations:      relations,
			Notes:          t.Notes,
		}
	}

	// Hand-roll the outer object so _meta stays first while preserving the
	// table iteration order from the SQL query (created_at DESC, name ASC).
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	combined := map[string]interface{}{"_meta": doc.Meta}
	for _, t := range rows {
		combined[t.Name] = doc.Tables[t.Name]
	}
	_ = enc.Encode(combined)
}

// formatBDDLastUpdated renders the doc's last_updated timestamp as
// "YYYY-MM-DD HH:MM:SS" (UTC). Empty input → empty string so the meta
// block reads cleanly when the registry has never been written.
func formatBDDLastUpdated(t time.Time) string {
	if t.IsZero() {
		return ""
	}
	return t.UTC().Format("2006-01-02 15:04:05")
}

// ── Import (doc-format) ──────────────────────────────────────────────────

// handleBDDUsedImportDoc handles POST /api/v1/bdd/used/tables/import-doc.
//
// Accepts the doc payload shape (same one emitted by GET .../doc):
//
//	{
//	  "_meta":  { "description": "...", "usage": "..." },
//	  "<table_name>": { "database_id": <int>, "description": "...", "rows": <int|null>,
//	                    "primary_key": <str|null>,
//	                    "default_order_by": <str|null>,
//	                    "columns": { "<col>": { "type": "...", "desc": "..." } },
//	                    "relations": [...] | { ... },
//	                    "notes": "..." },
//	   ...
//	}
//
// `_meta` (when present) is upserted into the singleton meta row. Each
// non-meta key is treated as a (database_id, table_name) row. The
// per-table `database_id` selects the target Hellopro DB; missing values
// default to 1 (Hellopro BO).
//
// Per-row failures are collected; the transaction is NOT aborted on bad
// rows. Cap: 1 MiB body, same as /import.
func (h *Handler) handleBDDUsedImportDoc(w http.ResponseWriter, r *http.Request) {
	if h.bddUsedRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "BDD registry is not configured"})
		return
	}
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, bddImportMaxBody)
	body, err := io.ReadAll(r.Body)
	if err != nil {
		var mbe *http.MaxBytesError
		if errors.As(err, &mbe) {
			writeJSON(w, http.StatusRequestEntityTooLarge, map[string]string{"error": "payload too large (max 1 MiB)"})
			return
		}
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "read body: " + err.Error()})
		return
	}
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(body, &raw); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON: " + err.Error()})
		return
	}

	creator := auth.UserEmailFromContext(r.Context())
	respErrs := make([]BDDImportError, 0)

	// _meta (optional) → upsert the singleton metadata row.
	if metaRaw, ok := raw["_meta"]; ok {
		var meta struct {
			Description string `json:"description"`
			Usage       string `json:"usage"`
		}
		if err := json.Unmarshal(metaRaw, &meta); err == nil {
			if _, err := h.bddUsedRepo.UpsertMeta(r.Context(), meta.Description, meta.Usage, creator); err != nil {
				respErrs = append(respErrs, BDDImportError{
					TableName: "_meta",
					Error:     "meta upsert: " + err.Error(),
				})
			}
		}
	}

	// Each remaining top-level key is a table.
	type docColumn struct {
		Type string `json:"type"`
		Desc string `json:"desc"`
	}
	type docTable struct {
		DatabaseID     int                  `json:"database_id"`
		Description    string               `json:"description"`
		Rows           *int64               `json:"rows"`
		PrimaryKey     *string              `json:"primary_key"`
		DefaultOrderBy *string              `json:"default_order_by"`
		Columns        map[string]docColumn `json:"columns"`
		Relations      json.RawMessage      `json:"relations"`
		Notes          string               `json:"notes"`
	}

	// Per-(dbID, table_name) cache of upstream catalog metadata. Filled
	// lazily so missing catalog data doesn't hammer the upstream API on
	// every iteration. catalogReady = true means we resolved both the
	// upstream table_id and its column set; missing tables stay absent.
	type catalogEntry struct {
		upstreamID int
		fieldNames map[string]bool
	}
	catalogCache := map[string]catalogEntry{}
	resolveCatalog := func(dbID int, tableName string) (catalogEntry, bool) {
		if !h.bddCatalogReady() {
			return catalogEntry{}, false
		}
		key := strconv.Itoa(dbID) + ":" + tableName
		if e, ok := catalogCache[key]; ok {
			return e, e.upstreamID != 0
		}
		tables, terr := h.bddCatalog.ListTables(r.Context(), dbID, tableName)
		if terr != nil {
			catalogCache[key] = catalogEntry{}
			return catalogEntry{}, false
		}
		var match *bddcatalog.Table
		for i := range tables {
			if tables[i].TableName == tableName {
				match = &tables[i]
				break
			}
		}
		if match == nil {
			catalogCache[key] = catalogEntry{}
			return catalogEntry{}, false
		}
		fr, ferr := h.bddCatalog.ListFields(r.Context(), dbID, match.ID)
		if ferr != nil {
			// Resolved upstream id but couldn't list fields — keep id so
			// upstream_table_id is still snapshotted on the row.
			entry := catalogEntry{upstreamID: match.ID, fieldNames: nil}
			catalogCache[key] = entry
			return entry, true
		}
		fnames := make(map[string]bool, len(fr.Fields))
		for _, f := range fr.Fields {
			fnames[f.FieldName] = true
		}
		entry := catalogEntry{upstreamID: match.ID, fieldNames: fnames}
		catalogCache[key] = entry
		return entry, true
	}

	rows := make([]db.BDDUsedTable, 0, len(raw))
	for name, tRaw := range raw {
		if strings.HasPrefix(name, "_") {
			continue
		}
		if !bddIdentRe.MatchString(name) {
			respErrs = append(respErrs, BDDImportError{
				TableName: name,
				Error:     "table_name invalid",
			})
			continue
		}
		var t docTable
		if err := json.Unmarshal(tRaw, &t); err != nil {
			respErrs = append(respErrs, BDDImportError{
				TableName: name,
				Error:     "decode: " + err.Error(),
			})
			continue
		}

		// Default to 1 (Hellopro BO) when the table omits database_id.
		// Reject any value outside the closed Hellopro DB enum.
		dbID := t.DatabaseID
		if dbID == 0 {
			dbID = 1
		}
		if !validBDDDatabaseIDs[dbID] {
			respErrs = append(respErrs, BDDImportError{
				DatabaseID: dbID,
				TableName:  name,
				Error:      "database_id must be one of 1, 5, 10",
			})
			continue
		}

		row := db.BDDUsedTable{
			DatabaseID:  dbID,
			Name:        name,
			Description: t.Description,
			Rows:        t.Rows,
			Notes:       t.Notes,
		}
		if t.PrimaryKey != nil {
			row.PrimaryKey = *t.PrimaryKey
		}
		if t.DefaultOrderBy != nil {
			row.DefaultOrderBy = *t.DefaultOrderBy
		}
		if len(t.Relations) > 0 {
			row.Relations = t.Relations
		}

		// Resolve the upstream catalog entry once per (dbID, name) to
		// snapshot upstream_table_id and validate column names. When
		// catalog is unavailable or the table is unknown upstream, we
		// import the doc as-is — the admin can still hand-curate later.
		catEntry, catOK := resolveCatalog(dbID, name)
		if catOK {
			row.UpstreamTableID = catEntry.upstreamID
		}

		for fname, col := range t.Columns {
			fname = strings.TrimSpace(fname)
			if !bddIdentRe.MatchString(fname) {
				respErrs = append(respErrs, BDDImportError{
					DatabaseID: dbID,
					TableName:  name,
					Error:      "field_name " + fname + " is invalid",
				})
				continue
			}
			// Drop columns that don't exist in the upstream catalog so
			// we don't seed the registry with hallucinated fields the
			// LLM would later fail to query.
			if catOK && catEntry.fieldNames != nil && !catEntry.fieldNames[fname] {
				respErrs = append(respErrs, BDDImportError{
					DatabaseID: dbID,
					TableName:  name,
					Error:      "field " + fname + " not in upstream catalog (skipped)",
				})
				continue
			}
			row.Fields = append(row.Fields, db.BDDUsedField{
				FieldName:   fname,
				FieldType:   col.Type,
				Description: col.Desc,
			})
		}
		rows = append(rows, row)
	}

	inserted, updated, repoErrs, err := h.bddUsedRepo.Import(r.Context(), rows, creator)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	for _, e := range repoErrs {
		respErrs = append(respErrs, BDDImportError{
			DatabaseID: e.DatabaseID,
			TableName:  e.TableName,
			Error:      e.Err.Error(),
		})
	}

	if h.tokenCache != nil {
		h.tokenCache.InvalidateAll()
	}
	if h.oauth2Cache != nil {
		h.oauth2Cache.InvalidateAll()
	}

	writeJSON(w, http.StatusOK, BDDImportResponse{
		Inserted: inserted,
		Updated:  updated,
		Errors:   respErrs,
	})
}

// ── Bulk update / delete ─────────────────────────────────────────────────

// handleBDDUsedBulkUpdateOrDelete dispatches PATCH / DELETE on
// /api/v1/bdd/used/tables/bulk. PATCH applies (database_id, is_active)
// to a list of ids; DELETE removes the listed ids and cascades the
// scope-token / OAuth2 join rows.
func (h *Handler) handleBDDUsedBulkUpdateOrDelete(w http.ResponseWriter, r *http.Request) {
	if h.bddUsedRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "BDD registry is not configured"})
		return
	}
	switch r.Method {
	case http.MethodPatch:
		h.bulkUpdateBDDUsedTables(w, r)
	case http.MethodDelete:
		h.bulkDeleteBDDUsedTables(w, r)
	default:
		w.Header().Set("Allow", "PATCH, DELETE")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
	}
}

func (h *Handler) bulkUpdateBDDUsedTables(w http.ResponseWriter, r *http.Request) {
	var req BulkUpdateBDDUsedTablesRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON body"})
		return
	}
	if len(req.IDs) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "ids must not be empty"})
		return
	}
	if len(req.IDs) > bddBulkMaxItems {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "ids: too many entries (max " + strconv.Itoa(bddBulkMaxItems) + ")",
		})
		return
	}
	if req.DatabaseID == nil && req.IsActive == nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "at least one of database_id or is_active must be provided",
		})
		return
	}

	updates := map[string]interface{}{}
	if req.DatabaseID != nil {
		if !validBDDDatabaseIDs[*req.DatabaseID] {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "database_id must be one of 1, 5, 10",
			})
			return
		}
		updates["database_id"] = *req.DatabaseID
	}
	if req.IsActive != nil {
		updates["is_active"] = *req.IsActive
	}

	affected, err := h.bddUsedRepo.BulkUpdate(r.Context(), req.IDs, updates)
	if err != nil {
		// Surface unique-key conflicts as 409 — moving multiple tables to
		// the same target DB can collide on (database_id, table_name).
		if isDuplicateKeyErr(err) {
			writeJSON(w, http.StatusConflict, map[string]string{
				"error": "table name already registered in target database",
			})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	if h.tokenCache != nil {
		h.tokenCache.InvalidateAll()
	}
	if h.oauth2Cache != nil {
		h.oauth2Cache.InvalidateAll()
	}

	writeJSON(w, http.StatusOK, BulkOpResponse{Affected: affected})
}

// isDuplicateKeyErr is duplicated locally because the repo helper is
// unexported. Same logic — MySQL 1062 / SQLite "UNIQUE constraint failed".
func isDuplicateKeyErr(err error) bool {
	if err == nil {
		return false
	}
	if strings.Contains(err.Error(), "UNIQUE constraint failed") {
		return true
	}
	if strings.Contains(err.Error(), "1062") {
		return true
	}
	return false
}

func (h *Handler) bulkDeleteBDDUsedTables(w http.ResponseWriter, r *http.Request) {
	var req BulkDeleteBDDUsedTablesRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON body"})
		return
	}
	if len(req.IDs) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "ids must not be empty"})
		return
	}
	if len(req.IDs) > bddBulkMaxItems {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "ids: too many entries (max " + strconv.Itoa(bddBulkMaxItems) + ")",
		})
		return
	}

	affected, err := h.bddUsedRepo.BulkDelete(r.Context(), req.IDs)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	if h.tokenCache != nil {
		h.tokenCache.InvalidateAll()
	}
	if h.oauth2Cache != nil {
		h.oauth2Cache.InvalidateAll()
	}

	writeJSON(w, http.StatusOK, BulkOpResponse{Affected: affected})
}

// ── Refresh from upstream catalog ────────────────────────────────────────

// handleBDDUsedRefreshCatalog handles
// POST /api/v1/bdd/used/tables/{id}/refresh-catalog.
//
// Pulls the upstream `primary` (from /databases/{db}/tables/{tid}/fields)
// and `count` (from /databases/{db}/tables/{tid}/count) for the given
// registered table and persists them to bdd_used_tables. Returns the
// refreshed row.
//
// Returns 503 when the upstream client is unconfigured, 502 when the
// upstream call fails, 422 when the table has no upstream link
// (UpstreamTableID == 0).
func (h *Handler) handleBDDUsedRefreshCatalog(w http.ResponseWriter, r *http.Request, id string) {
	if h.bddUsedRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "BDD registry is not configured"})
		return
	}
	if !h.bddCatalogReady() {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": catalogDisabledMsg})
		return
	}

	table, err := h.bddUsedRepo.GetTable(r.Context(), id)
	if err != nil {
		if errors.Is(err, repository.ErrBDDNotFound) {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "table not found"})
			return
		}
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	if table.UpstreamTableID == 0 {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]string{
			"error": "table has no upstream catalog link (upstream_table_id missing)",
		})
		return
	}

	fieldsResp, ferr := h.bddCatalog.ListFields(r.Context(), table.DatabaseID, table.UpstreamTableID)
	if ferr != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": ferr.Error()})
		return
	}
	count, cerr := h.bddCatalog.CountRows(r.Context(), table.DatabaseID, table.UpstreamTableID)
	if cerr != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": cerr.Error()})
		return
	}

	if err := h.bddUsedRepo.UpdateTableMetadata(r.Context(), id, map[string]interface{}{
		"primary_key": fieldsResp.Primary,
		"rows":        count,
	}); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	out, err := h.bddUsedRepo.GetTable(r.Context(), id)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, toBDDUsedTableDTO(*out))
}

// ── Public (shared-secret) read endpoints ───────────────────────────────
//
// External servers (e.g. the PHP MCP runner that ships schema_doc.json
// and config.php) pull the BDD registry over HTTP instead of
// committing static files. Auth: X-Admin-Token must match the
// BDD_PUBLIC_API_TOKEN env var. JWT/cookie auth is bypassed via the
// /api/v1/public/ exemption in auth/middleware.go.
//
// Both handlers return 503 when the token is unconfigured (registry
// disabled), 401 when the header is missing or wrong, and 405 on
// non-GET methods.

// bddPublicAuth checks the shared-secret header in constant time.
// Empty configured token = endpoint disabled (503). Matches the
// X-Admin-Token convention used by the runner-sync route.
func (h *Handler) bddPublicAuth(w http.ResponseWriter, r *http.Request) bool {
	if h.config == nil || h.config.BDDPublicAPIToken == "" {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"error": "public BDD API is not configured (BDD_PUBLIC_API_TOKEN unset)",
		})
		return false
	}
	got := r.Header.Get("X-Admin-Token")
	if got == "" || subtle.ConstantTimeCompare([]byte(got), []byte(h.config.BDDPublicAPIToken)) != 1 {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid or missing X-Admin-Token"})
		return false
	}
	return true
}

// activeBDDTables loads the registry and drops inactive rows. Used by
// both public endpoints — inactive tables must never leak to external
// runners or the PHP layer would expose tables the gateway has paused.
func (h *Handler) activeBDDTables(r *http.Request) ([]db.BDDUsedTable, error) {
	rows, err := h.bddUsedRepo.ListAll(r.Context())
	if err != nil {
		return nil, err
	}
	out := rows[:0]
	for _, t := range rows {
		if t.IsActive {
			out = append(out, t)
		}
	}
	return out, nil
}

// handleBDDPublicSchemaDoc handles GET /api/v1/public/bdd/schema-doc.
// Returns the same shape as /api/v1/bdd/used/tables/doc but only for
// active tables and behind the shared-secret header.
func (h *Handler) handleBDDPublicSchemaDoc(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	if !h.bddPublicAuth(w, r) {
		return
	}
	if h.bddUsedRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "BDD registry is not configured"})
		return
	}

	rows, err := h.activeBDDTables(r)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	meta, err := h.bddUsedRepo.GetMeta(r.Context())
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	latest, err := h.bddUsedRepo.LatestUpdatedAt(r.Context())
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	if latest.IsZero() && !meta.UpdatedAt.IsZero() {
		latest = meta.UpdatedAt
	}

	tables := make(map[string]BDDDocTable, len(rows))
	for _, t := range rows {
		cols := make(map[string]BDDDocColumn, len(t.Fields))
		for _, f := range t.Fields {
			cols[f.FieldName] = BDDDocColumn{Type: f.FieldType, Desc: f.Description}
		}
		var pkPtr *string
		if t.PrimaryKey != "" {
			s := t.PrimaryKey
			pkPtr = &s
		}
		var orderPtr *string
		if t.DefaultOrderBy != "" {
			s := t.DefaultOrderBy
			orderPtr = &s
		}
		relations := t.Relations
		if len(relations) == 0 {
			relations = json.RawMessage(`[]`)
		}
		tables[t.Name] = BDDDocTable{
			Description:    t.Description,
			Rows:           t.Rows,
			PrimaryKey:     pkPtr,
			DefaultOrderBy: orderPtr,
			Columns:        cols,
			Relations:      relations,
			Notes:          t.Notes,
		}
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	combined := map[string]interface{}{
		"_meta": BDDDocMeta{
			Description: meta.Description,
			Usage:       meta.Usage,
			LastUpdated: formatBDDLastUpdated(latest),
		},
	}
	for _, t := range rows {
		combined[t.Name] = tables[t.Name]
	}
	_ = enc.Encode(combined)
}

// BDDPublicConfigResponse is the shape consumed by the PHP MCP runner's
// config.php. `allowed_tables` matches the runner's per-table
// whitelist convention (`include` = explicit column list); empty
// `include` = no columns exposed. `table_database_map` only carries
// non-default DB tables — the runner falls back to "mysql" for
// anything missing.
type BDDPublicConfigResponse struct {
	AllowedTables    map[string]BDDPublicAllowedTable `json:"allowed_tables"`
	TableDatabaseMap map[string]string                `json:"table_database_map"`
	MaxRows          int                              `json:"max_rows"`
	MySQLTimeoutMs   int                              `json:"mysql_timeout_ms"`
}

// BDDPublicAllowedTable is one row of the `allowed_tables` map. Only
// the `include` form is emitted today; `exclude` / `max_rows` are
// reserved for future per-table overrides.
type BDDPublicAllowedTable struct {
	Include []string `json:"include"`
}

// handleBDDPublicConfig handles GET /api/v1/public/bdd/config.
// Builds the runtime config block consumed by the PHP MCP runner from
// the active rows of bdd_used_tables / bdd_used_fields.
func (h *Handler) handleBDDPublicConfig(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	if !h.bddPublicAuth(w, r) {
		return
	}
	if h.bddUsedRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "BDD registry is not configured"})
		return
	}

	rows, err := h.activeBDDTables(r)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	allowed := make(map[string]BDDPublicAllowedTable, len(rows))
	dbMap := make(map[string]string)
	for _, t := range rows {
		cols := make([]string, 0, len(t.Fields))
		for _, f := range t.Fields {
			cols = append(cols, f.FieldName)
		}
		allowed[t.Name] = BDDPublicAllowedTable{Include: cols}

		if key, ok := bddPublicDBKeyByID[t.DatabaseID]; ok && key != bddPublicDefaultDBKey {
			dbMap[t.Name] = key
		}
	}

	writeJSON(w, http.StatusOK, BDDPublicConfigResponse{
		AllowedTables:    allowed,
		TableDatabaseMap: dbMap,
		MaxRows:          bddPublicMaxRows,
		MySQLTimeoutMs:   bddPublicMySQLTimeoutMs,
	})
}
