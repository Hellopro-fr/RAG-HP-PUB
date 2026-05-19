package auth

import (
	"context"
	"net/http"
)

type ctxKey int

const sessionCtxKey ctxKey = 1

// AdminResolver answers (isAllowed, isAdmin) for a given email. Plug a UserRepo lookup at boot.
type AdminResolver func(email string) (bool, bool)

func RequireAuth(secret string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			data, err := GetSession(r, secret)
			if err != nil {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusUnauthorized)
				_, _ = w.Write([]byte(`{"error":"unauthorized"}`))
				return
			}
			ctx := context.WithValue(r.Context(), sessionCtxKey, data)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func RequireAdmin(secret string, resolve AdminResolver) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return RequireAuth(secret)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			data, _ := SessionFromContext(r.Context())
			allowed, isAdmin := resolve(data.Email)
			w.Header().Set("Content-Type", "application/json")
			if !allowed {
				w.WriteHeader(http.StatusForbidden)
				_, _ = w.Write([]byte(`{"error":"forbidden","error_description":"user blocked"}`))
				return
			}
			if !isAdmin {
				w.WriteHeader(http.StatusForbidden)
				_, _ = w.Write([]byte(`{"error":"forbidden","error_description":"admin only"}`))
				return
			}
			next.ServeHTTP(w, r)
		}))
	}
}

func SessionFromContext(ctx context.Context) (*SessionData, bool) {
	d, ok := ctx.Value(sessionCtxKey).(*SessionData)
	return d, ok
}
