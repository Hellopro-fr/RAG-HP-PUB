package api

import (
	"encoding/json"
	"net/http"

	"github.com/hellopro/account-service/internal/db"
)

type SessionRepo interface {
	ListByUser(email string) ([]db.OAuth2RefreshToken, error)
	ListBySID(sid string) ([]db.OAuth2RefreshToken, error)
	RevokeBySID(sid, reason string) error
}

type SessionsDeps struct {
	Repo SessionRepo
}

func NewSessionsHandler(d SessionsDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			email := r.PathValue("email")
			rows, err := d.Repo.ListByUser(email)
			if err != nil {
				writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
				return
			}
			out := make([]map[string]interface{}, 0, len(rows))
			for _, row := range rows {
				out = append(out, map[string]interface{}{
					"id":             row.ID,
					"sid":            row.SID,
					"client_id":      row.ClientID,
					"created_at":     row.CreatedAt,
					"last_used_at":   row.LastUsedAt,
					"expires_at":     row.ExpiresAt,
					"revoked":        row.Revoked,
					"revoked_reason": row.RevokedReason,
				})
			}
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"items": out, "total": len(out),
			})
		case http.MethodPost:
			sid := r.PathValue("sid")
			if err := d.Repo.RevokeBySID(sid, "admin_revoke"); err != nil {
				writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
				return
			}
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]string{"status": "revoked"})
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	})
}
