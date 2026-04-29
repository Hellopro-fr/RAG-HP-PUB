package middleware

import (
	"context"
	"net/http"
	"time"
)

type AuditStore interface {
	Append(ctx context.Context, entry map[string]any) error
}

type AuditOptions struct {
	CaptureParams []string
	CaptureQuery  []string
	CaptureBody   []string
}

type statusCapture struct {
	http.ResponseWriter
	status int
}

func (s *statusCapture) WriteHeader(code int) {
	s.status = code
	s.ResponseWriter.WriteHeader(code)
}

func AuditMiddleware(store AuditStore, action string, opts AuditOptions) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			sc := &statusCapture{ResponseWriter: w, status: 200}
			next.ServeHTTP(sc, r)

			user := "anonymous"
			if u := UserFromContext(r.Context()); u != nil {
				if v, ok := u["role"].(string); ok {
					user = v
				}
			}
			st := "ok"
			if sc.status >= 400 {
				st = "error"
			}
			entry := map[string]any{
				"ts":     time.Now().UTC().Format(time.RFC3339Nano),
				"user":   user,
				"action": action,
				"status": st,
				"ip":     clientIP(r),
			}
			metadata := map[string]any{}
			for _, k := range opts.CaptureQuery {
				if v := r.URL.Query().Get(k); v != "" {
					metadata[k] = v
				}
			}
			if len(metadata) > 0 {
				entry["metadata"] = metadata
			}
			_ = store.Append(r.Context(), entry)
		})
	}
}

func clientIP(r *http.Request) string {
	if xf := r.Header.Get("X-Forwarded-For"); xf != "" {
		return xf
	}
	return r.RemoteAddr
}
