package health

import (
	"encoding/json"
	"net/http"
)

type Pinger interface {
	Ping() error
}

func NewHandler(version string, p Pinger) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		dbStatus := "ok"
		ok := true
		if err := p.Ping(); err != nil {
			dbStatus = "down: " + err.Error()
			ok = false
		}
		w.Header().Set("Content-Type", "application/json")
		if !ok {
			w.WriteHeader(http.StatusServiceUnavailable)
		}
		statusStr := "ok"
		if !ok {
			statusStr = "degraded"
		}
		_ = json.NewEncoder(w).Encode(map[string]string{
			"status":  statusStr,
			"db":      dbStatus,
			"version": version,
		})
	})
}
