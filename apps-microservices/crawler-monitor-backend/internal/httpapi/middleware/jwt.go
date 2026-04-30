package middleware

import (
	"context"
	"net/http"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

type ctxKeyUser struct{}

func JWTAuth(secret string) func(http.Handler) http.Handler {
	keyFn := func(t *jwt.Token) (any, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, jwt.ErrTokenSignatureInvalid
		}
		return []byte(secret), nil
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			h := r.Header.Get("Authorization")
			if !strings.HasPrefix(h, "Bearer ") {
				writeJSONError(w, 401, "Authentication required")
				return
			}
			raw := strings.TrimPrefix(h, "Bearer ")
			tok, err := jwt.Parse(raw, keyFn)
			if err != nil || !tok.Valid {
				writeJSONError(w, 403, "Invalid token")
				return
			}
			claims, _ := tok.Claims.(jwt.MapClaims)
			ctx := context.WithValue(r.Context(), ctxKeyUser{}, map[string]any(claims))
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func UserFromContext(ctx context.Context) map[string]any {
	v, _ := ctx.Value(ctxKeyUser{}).(map[string]any)
	return v
}

func writeJSONError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_, _ = w.Write([]byte(`{"error":"` + msg + `"}`))
}
