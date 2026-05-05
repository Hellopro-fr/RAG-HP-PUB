package api

import (
	"encoding/json"
	"net/http"

	"account-service/internal/db"
)

type UserAdminRepo interface {
	List(limit, offset int) ([]db.User, int64, error)
	FindByEmail(email string) (*db.User, error)
	SetAdmin(email string, admin bool) error
	SetAllowed(email string, ok bool) error
}

type RevokeAll interface {
	RevokeAllForUser(email, reason string) error
}

type LogoutBroadcaster interface {
	BroadcastForUser(email string)
}

type AdminUserDeps struct {
	Repo        UserAdminRepo
	RevokeAll   RevokeAll
	Broadcaster LogoutBroadcaster
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
