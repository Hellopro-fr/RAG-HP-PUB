// Package transport hosts the HTTP handler for POST /mcp and its middleware chain.
package transport

import (
	"log"
	"net/http"
	"runtime/debug"
	"time"
)

// loggingMiddleware emits a one-line log per request: method + path + status + duration.
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rw := &statusRecorder{ResponseWriter: w, status: 200}
		next.ServeHTTP(rw, r)
		log.Printf("[mcp-zoho-service] %s %s %d %s", r.Method, r.URL.Path, rw.status, time.Since(start))
	})
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (s *statusRecorder) WriteHeader(code int) {
	s.status = code
	s.ResponseWriter.WriteHeader(code)
}

// recoveryMiddleware catches panics in downstream handlers, logs the stack
// and emits a 500.
func recoveryMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if rec := recover(); rec != nil {
				log.Printf("[mcp-zoho-service] panic: %v\n%s", rec, debug.Stack())
				http.Error(w, `{"error":"internal_error"}`, http.StatusInternalServerError)
			}
		}()
		next.ServeHTTP(w, r)
	})
}

// adminTokenMiddleware rejects requests whose X-Admin-Token doesn't match.
// Health probes (GET /health) are exempt and reach the next handler unchanged.
func adminTokenMiddleware(expected string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/health" {
				next.ServeHTTP(w, r)
				return
			}
			if got := r.Header.Get("X-Admin-Token"); got != expected || expected == "" {
				http.Error(w, `{"error":"invalid_admin_token"}`, http.StatusUnauthorized)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}
