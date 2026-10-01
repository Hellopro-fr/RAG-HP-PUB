package api

import (
	"encoding/json"
	"net/http"

	"account-service/internal/db"
	"account-service/internal/gatewaysync"
)

type UserAdminRepo interface {
	List(limit, offset int) ([]db.User, int64, error)
	FindByEmail(email string) (*db.User, error)
	SetAdmin(email string, admin bool) error
	SetAllowed(email string, ok bool) error
	ListAllowed() ([]db.User, error)
}

type RevokeAll interface {
	RevokeAllForUser(email, reason string) error
}

type LogoutBroadcaster interface {
	BroadcastForUser(email string)
}

// McpSyncer pushes users to the MCP gateway. Nil when
// MCP_GATEWAY_INTERNAL_URL is unset (sync routes return 503).
type McpSyncer interface {
	SyncUsers(users []gatewaysync.SyncUser) (*gatewaysync.Result, error)
}

type AdminUserDeps struct {
	Repo        UserAdminRepo
	RevokeAll   RevokeAll
	Broadcaster LogoutBroadcaster
	McpSync     McpSyncer
}

func NewAdminUserHandler(d AdminUserDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		op := r.PathValue("op")
		email := r.PathValue("email")
		switch r.Method {
		case http.MethodGet:
			handleListUsers(w, r, d.Repo)
			return
		case http.MethodPost:
			w.Header().Set("Content-Type", "application/json")
			switch op {
			case "promote":
				_ = d.Repo.SetAdmin(email, true)
			case "demote":
				_ = d.Repo.SetAdmin(email, false)
			case "block":
				_ = d.Repo.SetAllowed(email, false)
				_ = d.RevokeAll.RevokeAllForUser(email, "blocked")
				d.Broadcaster.BroadcastForUser(email)
			case "unblock":
				_ = d.Repo.SetAllowed(email, true)
			case "revoke":
				_ = d.RevokeAll.RevokeAllForUser(email, "admin_revoke")
				d.Broadcaster.BroadcastForUser(email)
				_ = json.NewEncoder(w).Encode(map[string]string{"status": "revoked"})
				return
			case "sync-mcp":
				if d.McpSync == nil {
					writeJSONErr(w, http.StatusServiceUnavailable, "mcp_sync_unconfigured", "MCP gateway sync not configured")
					return
				}
				u, err := d.Repo.FindByEmail(email)
				if err != nil {
					writeJSONErr(w, http.StatusNotFound, "not_found", "unknown user")
					return
				}
				res, err := d.McpSync.SyncUsers([]gatewaysync.SyncUser{{Email: u.Email, DisplayName: u.DisplayName}})
				if err != nil {
					writeJSONErr(w, http.StatusBadGateway, "mcp_sync_failed", "mcp gateway sync failed: "+err.Error())
					return
				}
				_ = json.NewEncoder(w).Encode(res)
				return
			default:
				writeJSONErr(w, http.StatusBadRequest, "invalid_request", "unknown op")
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})
}

// NewAdminUserMcpSyncAllHandler handles POST /api/v1/admin/users/sync-mcp.
// It fetches all is_allowed=true users and pushes them to the MCP gateway in
// one batch. Blocked users are intentionally excluded — they should not be
// pre-provisioned in the gateway. When there are no allowed users the gateway
// is not called and an empty result is returned immediately.
func NewAdminUserMcpSyncAllHandler(d AdminUserDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if d.McpSync == nil {
			writeJSONErr(w, http.StatusServiceUnavailable, "mcp_sync_unconfigured", "MCP gateway sync not configured")
			return
		}
		allowed, err := d.Repo.ListAllowed()
		if err != nil {
			writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
			return
		}
		if len(allowed) == 0 {
			_ = json.NewEncoder(w).Encode(&gatewaysync.Result{Created: []string{}, Skipped: []string{}})
			return
		}
		batch := make([]gatewaysync.SyncUser, 0, len(allowed))
		for _, u := range allowed {
			batch = append(batch, gatewaysync.SyncUser{Email: u.Email, DisplayName: u.DisplayName})
		}
		res, err := d.McpSync.SyncUsers(batch)
		if err != nil {
			writeJSONErr(w, http.StatusBadGateway, "mcp_sync_failed", "mcp gateway sync failed: "+err.Error())
			return
		}
		_ = json.NewEncoder(w).Encode(res)
	})
}

func handleListUsers(w http.ResponseWriter, r *http.Request, repo UserAdminRepo) {
	limit := parseIntParam(r, "limit", 20, 100)
	offset := parseIntParam(r, "offset", 0, 100000)
	users, total, err := repo.List(limit, offset)
	if err != nil {
		writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
		return
	}
	out := make([]map[string]interface{}, 0, len(users))
	for _, u := range users {
		out = append(out, map[string]interface{}{
			"email":         u.Email,
			"display_name":  u.DisplayName,
			"is_admin":      u.IsAdmin,
			"is_allowed":    u.IsAllowed,
			"last_login_at": u.LastLoginAt,
			"created_at":    u.CreatedAt,
		})
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"items": out, "total": total, "limit": limit, "offset": offset,
	})
}
