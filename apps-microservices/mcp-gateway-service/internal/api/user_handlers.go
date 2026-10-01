package api

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
)

// handleUsers handles GET /api/v1/users with optional ?role= query param.
func (h *Handler) handleUsers(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}

	role := r.URL.Query().Get("role")
	users, err := h.userRepo.ListAll(role)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to list users"})
		return
	}

	resp := make([]UserResponse, 0, len(users))
	for i := range users {
		resp = append(resp, toUserResponse(&users[i]))
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"users": resp, "total": len(resp)})
}

// handleUserByID handles GET/PUT/DELETE /api/v1/users/{id} and sub-routes.
func (h *Handler) handleUserByID(w http.ResponseWriter, r *http.Request) {
	rest := strings.TrimPrefix(r.URL.Path, "/api/v1/users/")
	rest = strings.TrimSuffix(rest, "/")

	// Check for sub-route: {id}/toggle-allowed
	parts := strings.SplitN(rest, "/", 2)
	idStr := parts[0]
	subRoute := ""
	if len(parts) > 1 {
		subRoute = parts[1]
	}

	id, err := strconv.ParseUint(idStr, 10, 64)
	if err != nil || id == 0 {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid user id"})
		return
	}

	if subRoute == "toggle-allowed" {
		h.handleToggleUserAllowed(w, r, id)
		return
	}

	switch r.Method {
	case http.MethodGet:
		h.handleGetUser(w, r, id)
	case http.MethodPut:
		h.handleUpdateUserRole(w, r, id)
	case http.MethodDelete:
		h.handleDeleteUser(w, r, id)
	default:
		w.Header().Set("Allow", "GET, PUT, DELETE")
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
	}
}

func (h *Handler) handleGetUser(w http.ResponseWriter, r *http.Request, id uint64) {
	user, err := h.userRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, ErrorResponse{Error: "user not found"})
		return
	}
	writeJSON(w, http.StatusOK, toUserResponse(user))
}

func (h *Handler) handleUpdateUserRole(w http.ResponseWriter, r *http.Request, id uint64) {
	var req UpdateUserRoleRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
		return
	}

	if req.Role != auth.RoleAdmin && req.Role != auth.RoleReadOnly && req.Role != auth.RoleConfigOnly {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "role must be admin, read-only, or config-only"})
		return
	}

	if err := h.userRepo.UpdateRole(id, req.Role); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to update user role"})
		return
	}

	user, err := h.userRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]string{"status": "updated"})
		return
	}
	writeJSON(w, http.StatusOK, toUserResponse(user))
}

func (h *Handler) handleToggleUserAllowed(w http.ResponseWriter, r *http.Request, id uint64) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{Error: "method not allowed"})
		return
	}

	var req UpdateUserAllowedRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON body"})
		return
	}

	// Prevent self-disable
	currentEmail := auth.UserEmailFromContext(r.Context())
	if currentEmail != "" && !req.IsAllowed {
		user, err := h.userRepo.GetByID(id)
		if err == nil && user != nil && user.Email == currentEmail {
			writeJSON(w, http.StatusForbidden, ErrorResponse{Error: "impossible de désactiver votre propre accès"})
			return
		}
	}

	if err := h.userRepo.UpdateAllowed(id, req.IsAllowed); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to update user access"})
		return
	}

	user, err := h.userRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]string{"status": "updated"})
		return
	}
	writeJSON(w, http.StatusOK, toUserResponse(user))
}

func (h *Handler) handleDeleteUser(w http.ResponseWriter, r *http.Request, id uint64) {
	// Prevent self-deletion
	currentEmail := auth.UserEmailFromContext(r.Context())
	if currentEmail != "" {
		user, err := h.userRepo.GetByID(id)
		if err == nil && user != nil && user.Email == currentEmail {
			writeJSON(w, http.StatusForbidden, ErrorResponse{Error: "cannot delete your own account"})
			return
		}
	}

	if err := h.userRepo.Delete(id); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "failed to delete user"})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// toUserResponse converts a db.GatewayUser to a UserResponse.
func toUserResponse(u *db.GatewayUser) UserResponse {
	resp := UserResponse{
		ID:          u.ID,
		Email:       u.Email,
		DisplayName: u.DisplayName,
		Role:        u.Role,
		IsAllowed:   u.IsAllowed,
		LoginCount:  u.LoginCount,
		CreatedAt:   u.CreatedAt.Format("2006-01-02T15:04:05Z07:00"),
	}
	if u.LastLoginAt != nil {
		s := u.LastLoginAt.Format("2006-01-02T15:04:05Z07:00")
		resp.LastLoginAt = &s
	}
	return resp
}
