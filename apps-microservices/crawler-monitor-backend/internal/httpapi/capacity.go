package httpapi

import (
	"net/http"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
)

func capacityGetHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		running, max, err := rs.GetCapacity(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to read capacity")
			return
		}
		WriteJSON(w, 200, map[string]any{
			"running": running,
			"max":     max,
			"full":    max > 0 && running >= max,
		})
	}
}
