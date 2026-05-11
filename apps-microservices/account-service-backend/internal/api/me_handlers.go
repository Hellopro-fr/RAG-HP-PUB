package api

import (
	"context"
	"encoding/json"
	"net/http"

	"account-service/internal/auth"
)

type ctxKey int

// authSessionKey is a local context key used for tests. In production
// auth.SessionFromContext is the source of truth.
const authSessionKey ctxKey = 0

type UserInfo struct {
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
	IsAdmin     bool   `json:"is_admin"`
	IsAllowed   bool   `json:"is_allowed"`
}

type UserResolver interface {
	FindByEmail(email string) (UserInfo, error)
}

func NewMeHandler(repo UserResolver) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sess, ok := sessionFromAnyKey(r.Context())
		if !ok {
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}
		u, err := repo.FindByEmail(sess.Email)
		if err != nil {
			http.Error(w, `{"error":"server_error"}`, http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(u)
	})
}

func sessionFromAnyKey(ctx context.Context) (*auth.SessionData, bool) {
	if d, ok := auth.SessionFromContext(ctx); ok {
		return d, true
	}
	if d, ok := ctx.Value(authSessionKey).(*auth.SessionData); ok {
		return d, true
	}
	return nil, false
}
