package api

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/hellopro/mcp-gateway/internal/bddcatalog"
)

// catalogDisabledMsg is returned by every catalog proxy route when the
// upstream client is nil or unconfigured. Mirrors the Leexi proxy shape.
const catalogDisabledMsg = "BDD catalog integration is not configured (set BDD_CATALOG_BASE_URL and BDD_CATALOG_TOKEN)"

// SetBDDCatalog wires the upstream Hellopro BDD catalog client. Pass nil
// to disable the proxy routes — the handlers themselves return 503 when
// the client is missing or not Enabled().
func (h *Handler) SetBDDCatalog(c *bddcatalog.Client) {
	h.bddCatalog = c
}

// handleBDDCatalogDatabases mirrors the upstream /databases endpoint.
//
//	GET /api/v1/bdd/catalog/databases
//	Response: { "databases": [...] }
func (h *Handler) handleBDDCatalogDatabases(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	if !h.bddCatalogReady() {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": catalogDisabledMsg})
		return
	}
	rows, err := h.bddCatalog.ListDatabases(r.Context())
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"databases": rows})
}

// handleBDDCatalogTablesAndFields routes the
// /api/v1/bdd/catalog/databases/{db}/tables[/{table_id}/fields] sub-tree.
func (h *Handler) handleBDDCatalogTablesAndFields(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	if !h.bddCatalogReady() {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": catalogDisabledMsg})
		return
	}

	// Path shape: databases/{db}/tables  OR  databases/{db}/tables/{tid}/fields
	rest := strings.TrimPrefix(r.URL.Path, "/api/v1/bdd/catalog/databases/")
	parts := strings.Split(rest, "/")
	if len(parts) < 2 || parts[1] != "tables" {
		http.NotFound(w, r)
		return
	}
	dbID, err := strconv.Atoi(parts[0])
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "database id must be an integer"})
		return
	}

	switch len(parts) {
	case 2:
		// /databases/{db}/tables
		search := strings.TrimSpace(r.URL.Query().Get("search"))
		rows, err := h.bddCatalog.ListTables(r.Context(), dbID, search)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]interface{}{"tables": rows})
	case 4:
		tableID, err := strconv.Atoi(parts[2])
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "table id must be an integer"})
			return
		}
		switch parts[3] {
		case "fields":
			resp, err := h.bddCatalog.ListFields(r.Context(), dbID, tableID)
			if err != nil {
				writeJSON(w, http.StatusBadGateway, map[string]string{"error": err.Error()})
				return
			}
			writeJSON(w, http.StatusOK, map[string]interface{}{
				"fields":  resp.Fields,
				"primary": resp.Primary,
			})
		case "count":
			n, err := h.bddCatalog.CountRows(r.Context(), dbID, tableID)
			if err != nil {
				writeJSON(w, http.StatusBadGateway, map[string]string{"error": err.Error()})
				return
			}
			writeJSON(w, http.StatusOK, map[string]interface{}{"count": n})
		default:
			http.NotFound(w, r)
		}
	default:
		http.NotFound(w, r)
	}
}

// bddCatalogReady reports whether the upstream client is wired and
// reports itself as Enabled (both env vars set). Safe on a nil client.
func (h *Handler) bddCatalogReady() bool {
	return h.bddCatalog != nil && h.bddCatalog.Enabled()
}
