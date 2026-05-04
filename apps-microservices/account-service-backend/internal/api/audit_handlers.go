package api

import (
	"encoding/json"
	"net/http"

	"github.com/hellopro/account-service/internal/db"
)

type AuditRepo interface {
	List(filters map[string]interface{}, limit, offset int) ([]db.AuditLog, int64, error)
}

type AuditDeps struct {
	Repo AuditRepo
}

func NewAuditHandler(d AuditDeps) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		filters := map[string]interface{}{}
		for _, k := range []string{"event", "actor_email", "client_id"} {
			if v := r.URL.Query().Get(k); v != "" {
				filters[k] = v
			}
		}
		limit := parseIntParam(r, "limit", 20, 100)
		offset := parseIntParam(r, "offset", 0, 100000)
		rows, total, err := d.Repo.List(filters, limit, offset)
		if err != nil {
			writeJSONErr(w, http.StatusInternalServerError, "server_error", err.Error())
			return
		}
		out := make([]map[string]interface{}, 0, len(rows))
		for _, row := range rows {
			out = append(out, map[string]interface{}{
				"id":           row.ID,
				"event":        row.Event,
				"actor_email":  row.ActorEmail,
				"target_email": row.TargetEmail,
				"client_id":    row.ClientID,
				"ip_addr":      row.IPAddr,
				"user_agent":   row.UserAgent,
				"metadata":     jsonRaw(row.Metadata),
				"created_at":   row.CreatedAt,
			})
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"items": out, "total": total, "limit": limit, "offset": offset,
		})
	})
}
