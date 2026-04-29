package middleware

import (
	"net/http"
	"time"

	"github.com/go-chi/httprate"
)

func RateLimitByIP(max int, window time.Duration) func(http.Handler) http.Handler {
	return httprate.Limit(
		max,
		window,
		httprate.WithKeyFuncs(httprate.KeyByIP),
		httprate.WithLimitHandler(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			w.WriteHeader(429)
			_, _ = w.Write([]byte(`{"error":"Too many requests"}`))
		}),
	)
}
