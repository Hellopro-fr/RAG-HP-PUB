package httpapi

import (
	"context"
	"net/http"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/auth/password"
	"github.com/golang-jwt/jwt/v5"
)

type AuditAppender interface {
	Append(ctx context.Context, entry map[string]any) error
}

type loginReq struct {
	Password string `json:"password"`
}

func loginHandler(adminHash, jwtSecret string, audit AuditAppender) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req loginReq
		if err := DecodeJSON(r, &req); err != nil || req.Password == "" {
			if audit != nil {
				_ = audit.Append(r.Context(), map[string]any{
					"ts":     time.Now().UTC().Format(time.RFC3339Nano),
					"user":   "anonymous",
					"action": "login_attempt",
					"status": "error",
					"metadata": map[string]any{"reason": "missing_password"},
				})
			}
			WriteError(w, 400, "Password required")
			return
		}
		ok, _ := password.Verify(req.Password, adminHash)
		if !ok {
			if audit != nil {
				_ = audit.Append(r.Context(), map[string]any{
					"ts":     time.Now().UTC().Format(time.RFC3339Nano),
					"user":   "anonymous",
					"action": "login_failure",
					"status": "error",
				})
			}
			WriteError(w, 401, "Invalid password")
			return
		}
		tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
			"role": "admin",
			"exp":  time.Now().Add(24 * time.Hour).Unix(),
		})
		signed, err := tok.SignedString([]byte(jwtSecret))
		if err != nil {
			WriteError(w, 500, "Token signing failed")
			return
		}
		if audit != nil {
			_ = audit.Append(r.Context(), map[string]any{
				"ts":     time.Now().UTC().Format(time.RFC3339Nano),
				"user":   "admin",
				"action": "login_success",
				"status": "ok",
			})
		}
		WriteJSON(w, 200, map[string]string{"token": signed})
	}
}
