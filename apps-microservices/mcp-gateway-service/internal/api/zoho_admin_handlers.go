package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
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
