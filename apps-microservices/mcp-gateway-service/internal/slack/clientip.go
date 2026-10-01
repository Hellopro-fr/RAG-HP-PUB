package slack

import (
	"net"
	"net/http"
	"strings"
)

// ClientIP returns the caller's IP for logging/alerting purposes. Prefers
// X-Forwarded-For (first entry, since we're behind nginx in prod) and falls
// back to RemoteAddr with the port stripped. IPv6-aware.
func ClientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		// "203.0.113.5, 10.0.0.1" → "203.0.113.5"
		if comma := strings.IndexByte(xff, ','); comma >= 0 {
			return strings.TrimSpace(xff[:comma])
		}
		return strings.TrimSpace(xff)
	}
	if host, _, err := net.SplitHostPort(r.RemoteAddr); err == nil {
		return host
	}
	return r.RemoteAddr
}
